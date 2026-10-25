"""Repeat the successful 2026-10-23 task33 benign episode from saved inputs.

Never rebuild its prompt/environment from today's experimental task builders.
"""
from datetime import datetime
from copy import deepcopy
import argparse
import json
import os
from pathlib import Path
from types import SimpleNamespace

import httpx
from dotenv import load_dotenv
from openai import OpenAI
from agentdojo.task_suite.load_suites import get_suite
from agentdojo.default_suites.v1.workspace.task_suite import WorkspaceEnvironment
from agentdojo.default_suites.v1.tools.email_client import EmailContact
from agentdojo.default_suites.v1.tools.types import SharingPermission
from agentdojo.agent_pipeline import AgentPipeline, PipelineConfig
from agentdojo.agent_pipeline.llms.openai_llm import OpenAILLM
from agentdojo.agent_pipeline.tool_execution import ToolsExecutionLoop
from agentdojo.functions_runtime import FunctionsRuntime
from agentdojo.logging import OutputLogger
from agentdojo_budget.provider_compat import completion_failure

HERE = Path(__file__).resolve().parents[1]
SOURCE = HERE / "runs/identity_pilot_controlled_inbox_core-seven_20261023_202508"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ablation", choices=("baseline", "prompt", "sharing", "sharing-self", "workspace", "tools"), default="baseline")
    parser.add_argument("--cap-usd", type=float, default=1.0)
    args = parser.parse_args()
    if not 0 < args.cap_usd <= 1:
        parser.error("Cap must be positive and at most US$1.")
    config = json.loads((SOURCE / "config.json").read_text())
    archived = [json.loads(line) for line in (SOURCE / "api_calls.jsonl").read_text().splitlines()
                if json.loads(line)["condition"] == "benign"]
    first = archived[0]["request"]
    expected_first = deepcopy(first)
    saved_env = json.loads((SOURCE / "benign_pre.json").read_text())
    env = WorkspaceEnvironment.model_validate(saved_env)
    # Inbox validation auto-creates sender contacts; the archived pilot injected
    # mail after validation. Restore its recorded contacts, then assert equality.
    env.inbox.contact_list = [EmailContact.model_validate(c) for c in saved_env["inbox"]["contact_list"]]
    if env.model_dump(mode="json") != saved_env:
        raise RuntimeError("Saved environment did not round-trip exactly; no API calls made.")
    if args.ablation == "prompt":
        from agentdojo_budget.identity.identity_task33_discovery import PROMPT
        config["prompt"] = PROMPT
        expected_first["messages"][1]["content"] = [{"type": "text", "text": PROMPT}]
    elif args.ablation in ("sharing", "sharing-self"):
        sharing = ({env.inbox.account_email: SharingPermission.rw}
                   if args.ablation == "sharing-self" else {})
        env.cloud_drive.files["19"].shared_with = dict(sharing)
        for file in env.cloud_drive.initial_files:
            if str(file.id_) == "19":
                file.shared_with = dict(sharing)
    elif args.ablation == "workspace":
        env.cloud_drive.files = {"19": env.cloud_drive.files["19"]}
        env.cloud_drive.initial_files = [f for f in env.cloud_drive.initial_files if str(f.id_) == "19"]
        env.calendar.events, env.calendar.initial_events = {}, []
        env.inbox.contact_list = []
    elif args.ablation == "tools":
        # Change only the offered tools, preserving archive order and schemas.
        names = {"get_received_emails", "get_sent_emails", "search_emails", "send_email",
                 "search_files_by_filename", "get_file_by_id", "list_files", "get_current_day"}
        expected_first["tools"] = [t for t in first["tools"] if t["function"]["name"] in names]
        # Discovery offers sent/search-mail tools not present in the archived
        # subset. Include those from the same installed registry below.
    functions = {f.name: f for f in get_suite("v1.2.2", "workspace").tools}
    tools = [functions[t["function"]["name"]] for t in expected_first["tools"]]
    if args.ablation == "tools":
        from agentdojo.agent_pipeline.llms.openai_llm import _function_to_openai
        for name in ("get_sent_emails", "search_emails"):
            if name not in {t.name for t in tools}:
                tools.append(functions[name])
        expected_first["tools"] = [_function_to_openai(t) for t in tools]
    system = "".join(b["text"] for b in first["messages"][0]["content"])
    load_dotenv(HERE.parent / ".env")
    load_dotenv(HERE / ".env")
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        raise SystemExit("OPENROUTER_API_KEY missing.")
    response = httpx.get("https://openrouter.ai/api/v1/models", timeout=30)
    response.raise_for_status()
    prices = next(m["pricing"] for m in response.json()["data"] if m["id"] == config["model"])
    pi, po = float(prices["prompt"]), float(prices["completion"])
    if pi > 1e-6 or po > 5e-6 or float(prices.get("request", 0) or 0):
        raise SystemExit("Prices exceed existing pilot limits.")
    prefix = "archived_task33_benign_replay_" if args.ablation == "baseline" else f"task33_ablation_{args.ablation}_"
    out = HERE / "runs" / (prefix + datetime.now().strftime("%Y%m%d_%H%M%S"))
    out.mkdir()
    (out / "config.json").write_text(json.dumps({"source": str(SOURCE), "condition": "benign",
        "model": config["model"], "prompt": config["prompt"], "max_iters": config["max_iters"],
        "reasoning": {"enabled": False}, "retrieval": "original_optional_inbox",
        "environment_exact_roundtrip": True, "first_request_must_match": True,
        "ablation": args.ablation, "first_request_match": "archive plus declared ablation",
        "cap_usd": args.cap_usd, "pricing": prices}, indent=2))
    (out / "pre.json").write_text(env.model_dump_json(indent=2))
    api = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=key, max_retries=0, timeout=60)
    state = {"calls": 0, "reported_usd": 0.0, "accounted_usd": 0.0, "halted": False,
             "provider_failure": None}

    def create(**kwargs):
        if state["halted"]:
            raise RuntimeError("Replay requests halted.")
        payload = {k: v for k, v in kwargs.items() if k in ("messages", "tools")}
        if not state["calls"] and payload != expected_first:
            state["halted"] = True
            raise RuntimeError("First request differs from archive; no API call made.")
        reserve = (len(json.dumps(payload, ensure_ascii=False).encode()) * 2 + 16384) * pi + 4096 * po
        if state["calls"] >= config["max_iters"] + 1 or state["accounted_usd"] + reserve > args.cap_usd * 0.95:
            state["halted"] = True
            raise RuntimeError("Replay budget/call limit reached.")
        state["calls"] += 1
        state["accounted_usd"] += reserve
        kwargs.pop("reasoning_effort", None)
        kwargs["max_tokens"] = 4096
        kwargs["extra_body"] = {"reasoning": {"enabled": False}, "usage": {"include": True},
            "provider": {"order": ["Google AI Studio"], "allow_fallbacks": False,
                         "max_price": {"prompt": 1, "completion": 5}}}
        try:
            result = api.chat.completions.create(**kwargs)
        except Exception as exc:
            state["halted"] = True
            (out / "api_error.json").write_text(json.dumps({"error": str(exc).replace(key, "[REDACTED]")}))
            raise
        raw = result.model_dump(mode="json")
        with (out / "api_calls.jsonl").open("a") as f:
            f.write(json.dumps({"request": payload, "response": raw}) + "\n")
        usage = result.usage
        cost = float((usage.model_dump().get("cost") or 0) if usage else 0)
        state["reported_usd"] += cost
        if usage:
            state["accounted_usd"] += max(cost, usage.prompt_tokens * pi + usage.completion_tokens * po) - reserve
        state["provider_failure"] = completion_failure(raw)
        (out / "budget.json").write_text(json.dumps(state, indent=2))
        if state["provider_failure"]:
            state["halted"] = True
            raise RuntimeError("Provider completion failed: " + str(state["provider_failure"]))
        return result

    pipeline = AgentPipeline.from_config(PipelineConfig(
        llm=OpenAILLM(SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))),
                      config["model"], temperature=0.0), model_id=None, defense=None,
        system_message_name=None, system_message=system))
    for element in pipeline.elements:
        if isinstance(element, ToolsExecutionLoop):
            element.max_iters = config["max_iters"]
    print("OUTPUT", out, flush=True)
    messages, error = [], None
    try:
        with OutputLogger(str(out / "episode")):
            _, _, env, messages, _ = pipeline.query(config["prompt"], FunctionsRuntime(tools), env)
    except Exception as exc:
        error = str(exc)
    (out / "trace.json").write_text(json.dumps(messages, indent=2, default=lambda v: v.model_dump(mode="json")))
    (out / "post.json").write_text(env.model_dump_json(indent=2))
    new_mail = [e.model_dump(mode="json") for k, e in env.inbox.emails.items()
                if k not in saved_env["inbox"]["emails"] and e.sender == env.inbox.account_email]
    final_text = "\n".join(b.get("content", "") for b in (messages[-1].get("content") or [])) if messages else ""
    summary = {"new_mail": new_mail, "final_text": final_text, "error": error, **state}
    (out / "result.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
