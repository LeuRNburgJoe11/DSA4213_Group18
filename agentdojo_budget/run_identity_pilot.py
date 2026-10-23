"""Selected identity conditions, one trial each, with a shared USD 1 budget.

Run from repo root: .venv/bin/python -m agentdojo_budget.run_identity_pilot
Uses Gemini 2.5 Flash, the existing benign pilot's model. No automatic reruns.
"""
import argparse
from dataclasses import asdict
import json
import os
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import httpx
import yaml
from dotenv import load_dotenv
from openai import OpenAI
from agentdojo.task_suite.load_suites import get_suite  # initialise registry first
from agentdojo.agent_pipeline import AgentPipeline, PipelineConfig
from agentdojo.agent_pipeline.llms.openai_llm import OpenAILLM
from agentdojo.agent_pipeline.tool_execution import ToolsExecutionLoop
from agentdojo.functions_runtime import FunctionsRuntime
from agentdojo.logging import OutputLogger

from agentdojo_budget.identity_task import CONDITIONS, CONDITION_SETS, PROMPT, build_environment, make_suite, score_episode

HERE = Path(__file__).resolve().parent
MODEL = "google/gemini-2.5-flash"


def plain(value):
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return str(value)


def observed_ids(messages):
    ids = set()
    def visit(value):
        if isinstance(value, dict):
            if "id_" in value and "sender" in value and "body" in value:
                ids.add(str(value["id_"]))
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)
    for msg in messages:
        if msg["role"] != "tool" or msg.get("error"):
            continue
        for block in msg.get("content") or []:
            try:
                visit(yaml.safe_load(block.get("content", "")))
            except yaml.YAMLError:
                pass
    return sorted(ids)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--controlled-inbox", action="store_true",
                        help="Use 1-2 emails and get_received_emails as the only mail-reading tool")
    parser.add_argument("--condition-set", choices=CONDITION_SETS, default="original",
                        help="Select original, meeting-detail, document-only, evidence-comparison, or all")
    args = parser.parse_args()
    selected = CONDITION_SETS[args.condition_set]
    if any(CONDITIONS[n].evidence == "document_only" for n in selected) and not args.controlled_inbox:
        parser.error("Document-only comparisons require --controlled-inbox for all conditions.")
    load_dotenv(HERE.parent / ".env")
    load_dotenv(HERE / ".env")
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        raise SystemExit("OPENROUTER_API_KEY missing; no requests made.")
    response = httpx.get("https://openrouter.ai/api/v1/models", timeout=30)
    response.raise_for_status()
    prices = next(m["pricing"] for m in response.json()["data"] if m["id"] == MODEL)
    pi, po = float(prices["prompt"]), float(prices["completion"])
    if pi > 1e-6 or po > 5e-6 or float(prices.get("request", 0) or 0):
        raise SystemExit("Price outside configured limits; no paid requests made.")
    mode = "controlled_inbox" if args.controlled_inbox else "natural_retrieval"
    out = HERE / "runs" / ("identity_pilot_" + mode + "_" + args.condition_set + "_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    out.mkdir(parents=True)
    state = {"model": MODEL, "cap_usd": 1.0, "accounted_usd": 0.0,
             "reported_usd": 0.0, "calls": 0, "condition": None}
    (out / "config.json").write_text(json.dumps({"model": MODEL, "prompt": PROMPT,
        "conditions": list(selected), "condition_set": args.condition_set,
        "condition_specs": [asdict(CONDITIONS[n]) for n in selected],
        "prices": prices, "trials": 1,
        "max_iters": 10, "max_output_tokens": 4096, "defense": "none",
        "retrieval_mode": mode}, indent=2))
    real = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=key,
                  max_retries=0, timeout=60)
    halted = False
    per_condition_calls = 0

    def create(**kwargs):
        nonlocal halted, per_condition_calls
        if halted:
            raise RuntimeError("Network requests halted after an error/budget stop.")
        payload = {k: v for k, v in kwargs.items() if k in ("messages", "tools")}
        # Conservative text-token allowance plus full output reservation. Failed
        # requests retain the reservation. Account successful calls at the larger
        # of list-token estimate and reported cost (no cache discount assumed).
        size = len(json.dumps(payload, ensure_ascii=False).encode())
        reserve = (size * 2 + 16384) * pi + 4096 * po
        if state["accounted_usd"] + reserve > 0.95 or per_condition_calls >= 11:
            halted = True
            raise RuntimeError("Pilot budget/call limit reached.")
        state["accounted_usd"] += reserve
        state["calls"] += 1
        per_condition_calls += 1
        (out / "budget.json").write_text(json.dumps(state, indent=2))
        kwargs["max_tokens"] = 4096
        kwargs.pop("reasoning_effort", None)
        kwargs["extra_body"] = {"reasoning": {"enabled": False}, "usage": {"include": True},
            "provider": {"order": ["Google AI Studio"], "allow_fallbacks": False,
                         "max_price": {"prompt": 1, "completion": 5}}}
        try:
            result = real.chat.completions.create(**kwargs)
        except Exception:
            halted = True
            raise
        usage = result.usage.model_dump() if result.usage else {}
        reported = float(usage.get("cost") or 0)
        state["reported_usd"] += reported
        if result.usage:
            estimate = (result.usage.prompt_tokens or 0) * pi + (result.usage.completion_tokens or 0) * po
            state["accounted_usd"] += max(estimate, reported) - reserve
        with (out / "api_calls.jsonl").open("a") as f:
            f.write(json.dumps({"condition": state["condition"], "request": payload,
                                "response": result.model_dump(mode="json")}, default=plain) + "\n")
        (out / "budget.json").write_text(json.dumps(state, indent=2))
        return result

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    print("OUTPUT", out, flush=True)
    for name in selected:
        if halted:
            break
        state["condition"] = name
        per_condition_calls = 0
        env = build_environment(name, controlled_inbox=args.controlled_inbox)
        pre = env.model_copy(deep=True)
        (out / f"{name}_pre.json").write_text(pre.model_dump_json(indent=2))
        suite = make_suite(name, controlled_inbox=args.controlled_inbox)
        pipeline = AgentPipeline.from_config(PipelineConfig(
            llm=OpenAILLM(client, MODEL, temperature=0.0), model_id=None,
            defense=None, system_message_name=None, system_message=None))
        for element in pipeline.elements:
            if isinstance(element, ToolsExecutionLoop):
                element.max_iters = 10
        messages, error, termination = [], None, "completed"
        try:
            with OutputLogger(str(out / name)):
                _, _, env, messages, _ = pipeline.query(PROMPT, FunctionsRuntime(suite.tools), env)
            if not messages or messages[-1]["role"] != "assistant" or messages[-1].get("tool_calls"):
                termination = "max_iters"
        except Exception as exc:
            error, termination = f"{type(exc).__name__}: {exc}", "error"
        text = "\n".join(b.get("content", "") for b in
                         (messages[-1].get("content") or []) if b.get("type") == "text") if messages else ""
        result = score_episode(name, pre, env, text, observed_email_ids=observed_ids(messages),
                               termination=termination)
        result.update({"model": MODEL, "trial": 0, "retrieval_mode": mode,
                       "final_text": text, "error": error,
                       "api_calls": per_condition_calls})
        (out / f"{name}_trace.json").write_text(json.dumps(messages, indent=2, default=plain))
        (out / f"{name}_post.json").write_text(env.model_dump_json(indent=2))
        with (out / "results.jsonl").open("a") as f:
            f.write(json.dumps(result) + "\n")
        print(name, result["outcome"], "exposed=", result["attack_exposed"],
              "reported_usd=", round(state["reported_usd"], 5), flush=True)
    print("COMPLETE", json.dumps(state), flush=True)


if __name__ == "__main__":
    main()
