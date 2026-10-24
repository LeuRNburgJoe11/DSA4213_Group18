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

from agentdojo_budget.identity_task import CONDITIONS, CONDITION_SETS, PROMPT, ENVIRONMENT_VERSION, PROMPT_VERSION, build_environment, make_suite, score_episode
from agentdojo_budget.inbox_exposure import RequiredInboxExposure
from agentdojo_budget.provider_compat import ReasoningMetadata, completion_failure

HERE = Path(__file__).resolve().parent
MODEL = "google/gemini-2.5-flash"
REASONING_FLASH_MODELS = {"google/gemini-3.5-flash", "google/gemini-3.8-flash"}


def execution_limits(task):
    """Initial model call plus one model continuation per execution round."""
    rounds = 20 if task in ("25", "33-discovery") else 10
    return rounds, rounds + 1


def reasoning_settings(model):
    return {"effort": "low"} if model in REASONING_FLASH_MODELS else {"enabled": False}


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
    global CONDITIONS, CONDITION_SETS, PROMPT, build_environment, make_suite, score_episode
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", choices=("33", "25", "33-discovery"), default="33")
    parser.add_argument("--model", choices=(MODEL, *sorted(REASONING_FLASH_MODELS)), default=MODEL)
    parser.add_argument("--inbox-exposure", choices=("required", "agent-selected"), default="required",
                        help="Allow autonomous evidence retrieval in recipient-discovery conditions.")
    parser.add_argument("--conditions", nargs="+", help="Run only these members of the selected condition set (fresh output directory).")
    parser.add_argument("--controlled-inbox", action="store_true",
                        help="Use 1-2 emails and get_received_emails as the only mail-reading tool")
    parser.add_argument("--condition-set", choices=(*CONDITION_SETS, "discovery-five"), default=None,
                        help="Defaults: compact-six for task33, core-seven for task25, discovery-five for recipient discovery")
    args = parser.parse_args()
    model = args.model
    max_iters, max_calls = execution_limits(args.task)
    environment_version, prompt_version = ENVIRONMENT_VERSION, PROMPT_VERSION
    if args.condition_set is None:
        args.condition_set = {"33": "compact-six", "25": "core-seven", "33-discovery": "discovery-five"}[args.task]
    if args.task == "33-discovery":
        from agentdojo_budget import identity_task33_discovery as discovery
        if args.condition_set != "discovery-five" or not args.controlled_inbox:
            parser.error("Recipient discovery requires --condition-set discovery-five --controlled-inbox.")
        CONDITIONS, CONDITION_SETS, PROMPT = discovery.CONDITIONS, discovery.CONDITION_SETS, discovery.PROMPT
        build_environment, make_suite, score_episode = discovery.build_environment, discovery.make_suite, discovery.score_episode
        environment_version, prompt_version = discovery.ENVIRONMENT_VERSION, discovery.PROMPT_VERSION
    if args.task == "25":
        from agentdojo_budget import identity_task25 as task25
        environment_version = task25.ENVIRONMENT_VERSION
        prompt_version = task25.PROMPT_VERSION
        if args.condition_set != "core-seven" or not args.controlled_inbox:
            parser.error("Task25 requires --condition-set core-seven --controlled-inbox.")
        CONDITIONS, CONDITION_SETS, PROMPT = task25.CONDITIONS, task25.CONDITION_SETS, task25.PROMPT
        build_environment, make_suite, score_episode = task25.build_environment, task25.make_suite, task25.score_episode
    if args.condition_set not in CONDITION_SETS:
        parser.error("Selected condition set is not available for this task.")
    selected = CONDITION_SETS[args.condition_set]
    if args.conditions:
        if len(set(args.conditions)) != len(args.conditions) or any(n not in selected for n in args.conditions):
            parser.error("--conditions must be distinct members of the selected condition set.")
        selected = tuple(args.conditions)
    if args.inbox_exposure == "agent-selected" and args.task != "33-discovery":
        parser.error("Agent-selected inbox exposure is restricted to the recipient-discovery variant.")
    if any(CONDITIONS[n].evidence == "document_only" for n in selected) and not args.controlled_inbox:
        parser.error("Document-only comparisons require --controlled-inbox for all conditions.")
    load_dotenv(HERE.parent / ".env")
    load_dotenv(HERE / ".env")
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        raise SystemExit("OPENROUTER_API_KEY missing; no requests made.")
    response = httpx.get("https://openrouter.ai/api/v1/models", timeout=30)
    response.raise_for_status()
    prices = next(m["pricing"] for m in response.json()["data"] if m["id"] == model)
    pi, po = float(prices["prompt"]), float(prices["completion"])
    price_limits = {"prompt": 2, "completion": 10} if model == "google/gemini-3.5-flash" else {"prompt": 1, "completion": 5}
    if pi > price_limits["prompt"] * 1e-6 or po > price_limits["completion"] * 1e-6 or float(prices.get("request", 0) or 0):
        raise SystemExit("Price outside configured limits; no paid requests made.")
    required_inbox = args.controlled_inbox and args.inbox_exposure == "required"
    mode = ("required_inbox_first" if required_inbox else
            "controlled_agent_selected" if args.controlled_inbox else "natural_retrieval")
    task_prefix = {"33": "identity_pilot_", "25": "identity_task25_pilot_",
                   "33-discovery": "identity_task33_discovery_pilot_"}[args.task]
    out = HERE / "runs" / (task_prefix + mode + "_" + args.condition_set + "_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    out.mkdir(parents=True)
    state = {"model": model, "cap_usd": 1.0, "accounted_usd": 0.0,
             "reported_usd": 0.0, "calls": 0, "condition": None}
    (out / "config.json").write_text(json.dumps({"model": model, "task": args.task, "prompt": PROMPT,
        "conditions": list(selected), "condition_set": args.condition_set,
        "condition_specs": [asdict(CONDITIONS[n]) for n in selected],
        "prices": prices, "trials": 1,
        "provider_max_price_per_million": price_limits,
        "max_iters": max_iters, "max_api_calls_per_condition": max_calls,
        "environment_version": environment_version,
        "prompt_version": prompt_version,
        "max_output_tokens": 4096, "defense": "none",
        "reasoning": reasoning_settings(model),
        "reasoning_metadata_preserved": model in REASONING_FLASH_MODELS,
        "provider_error_handling": "classify_incomplete_without_retry_v1",
        "retrieval_mode": mode,
        "required_initial_tool": "get_received_emails" if required_inbox else None,
        "initial_tool_scheduled_by": "harness" if required_inbox else None}, indent=2))
    real = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=key,
                  max_retries=0, timeout=60)
    halted = False
    per_condition_calls = 0
    reasoning_metadata = ReasoningMetadata()
    provider_failure = None

    def create(**kwargs):
        nonlocal halted, per_condition_calls, provider_failure
        if halted:
            raise RuntimeError("Network requests halted after an error/budget stop.")
        if model in REASONING_FLASH_MODELS:
            kwargs["messages"] = reasoning_metadata.restore(kwargs["messages"])
        payload = {k: v for k, v in kwargs.items() if k in ("messages", "tools")}
        # Conservative text-token allowance plus full output reservation. Failed
        # requests retain the reservation. Account successful calls at the larger
        # of list-token estimate and reported cost (no cache discount assumed).
        size = len(json.dumps(payload, ensure_ascii=False).encode())
        reserve = (size * 2 + 16384) * pi + 4096 * po
        if state["accounted_usd"] + reserve > 0.95 or per_condition_calls >= max_calls:
            halted = True
            raise RuntimeError("Pilot budget/call limit reached.")
        state["accounted_usd"] += reserve
        state["calls"] += 1
        per_condition_calls += 1
        (out / "budget.json").write_text(json.dumps(state, indent=2))
        kwargs["max_tokens"] = 4096
        kwargs.pop("reasoning_effort", None)
        kwargs["extra_body"] = {"reasoning": reasoning_settings(model), "usage": {"include": True},
            "provider": {"order": ["Google AI Studio"], "allow_fallbacks": False,
                         "max_price": price_limits}}
        try:
            result = real.chat.completions.create(**kwargs)
        except Exception as exc:
            halted = True
            # Preserve the first provider failure before AgentDojo's retry
            # wrapper encounters the halted flag. Do not record credentials.
            detail = str(exc).replace(key, "[REDACTED]")
            with (out / "api_errors.jsonl").open("a") as f:
                f.write(json.dumps({"condition": state["condition"],
                                    "error_type": type(exc).__name__, "error": detail}) + "\n")
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
        raw_response = result.model_dump(mode="json")
        reasoning_metadata.remember(raw_response)
        provider_failure = completion_failure(raw_response)
        if provider_failure:
            # Raw response was saved above. End this episode without executing
            # any partial/error tool calls, while retaining earlier trace/actions.
            safe = result.model_copy(deep=True)
            if safe.choices:
                safe.choices[0].message.content = None
                safe.choices[0].message.tool_calls = None
            else:
                halted = True
                raise RuntimeError("Provider returned no completion choices.")
            return safe
        return result

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    print("OUTPUT", out, flush=True)
    for name in selected:
        if halted:
            break
        state["condition"] = name
        per_condition_calls = 0
        reasoning_metadata = ReasoningMetadata()
        provider_failure = None
        env = build_environment(name, controlled_inbox=args.controlled_inbox)
        pre = env.model_copy(deep=True)
        (out / f"{name}_pre.json").write_text(pre.model_dump_json(indent=2))
        suite = make_suite(name, controlled_inbox=args.controlled_inbox)
        pipeline = AgentPipeline.from_config(PipelineConfig(
            llm=OpenAILLM(client, model, temperature=0.0), model_id=None,
            defense=None, system_message_name=None, system_message=None))
        if required_inbox:
            pipeline.elements = [*pipeline.elements[:2], RequiredInboxExposure(), *pipeline.elements[2:]]
        for element in pipeline.elements:
            if isinstance(element, ToolsExecutionLoop):
                element.max_iters = max_iters
        messages, error, termination = [], None, "completed"
        try:
            with OutputLogger(str(out / name)):
                _, _, env, messages, _ = pipeline.query(PROMPT, FunctionsRuntime(suite.tools), env)
            if not messages or messages[-1]["role"] != "assistant" or messages[-1].get("tool_calls"):
                termination = "max_iters"
        except Exception as exc:
            error, termination = f"{type(exc).__name__}: {exc}", "error"
        if provider_failure:
            termination = provider_failure["failure_reason"]
            error = "Provider completion ended with " + str(provider_failure["native_finish_reason"] or provider_failure["finish_reason"])
        text = "\n".join(b.get("content", "") for b in
                         (messages[-1].get("content") or []) if b.get("type") == "text") if messages else ""
        result = score_episode(name, pre, env, text, observed_email_ids=observed_ids(messages),
                               termination=termination)
        result.update({"model": model, "trial": 0, "retrieval_mode": mode,
                       "final_text": text, "error": error,
                       "provider_failure": provider_failure,
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
