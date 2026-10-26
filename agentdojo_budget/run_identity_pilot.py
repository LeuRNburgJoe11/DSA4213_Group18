"""Selected identity conditions, one trial each, with a USD 1 budget per invocation.

Run from repo root: .venv/bin/python -m agentdojo_budget.run_identity_pilot
Defaults to Gemini 2.5 Flash, the existing benign pilot's model; --model also accepts Gemini 3.5/3.8
Flash, Claude Sonnet 5.5 and GPT-6 Sol (see MODELS). No automatic reruns.
"""
import argparse
from dataclasses import asdict
import json
import os
import subprocess
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
from agentdojo.agent_pipeline.tool_execution import ToolsExecutionLoop, ToolsExecutor
from agentdojo.functions_runtime import FunctionsRuntime
from agentdojo.logging import OutputLogger

from agentdojo_budget.defenses.recipient_gate import MODES as GATE_MODES, RecipientGate
from agentdojo_budget.identity import identity_task25_discovery, identity_task33_discovery, identity_task33_change
from agentdojo_budget.inbox_exposure import RequiredInboxExposure
from agentdojo_budget.provider_compat import (
    ReasoningMetadata, completion_failure, explicit_attachment_tools, ATTACHMENT_SCHEMA_VERSION,
)

HERE = Path(__file__).resolve().parent
MODEL = "google/gemini-2.5-flash"
REASONING_FLASH_MODELS = {"google/gemini-3.5-flash", "google/gemini-3.8-flash"}

# One entry per model the runner may use: the OpenRouter provider its requests are pinned to (no
# fallbacks, so runs stay comparable), the per-million-token price ceiling the run refuses to exceed
# (about 25% above the listed price), and the `reasoning` setting to send, or None to send none.
# Sonnet and GPT-6 send none: that matches the RQ1 runner, which ran them without a reasoning setting.
MODELS = {
    "google/gemini-2.5-flash": {"provider": "Google AI Studio", "reasoning": {"enabled": False},
                                "price_limits": {"prompt": 1, "completion": 5}},
    "google/gemini-3.5-flash": {"provider": "Google AI Studio", "reasoning": {"effort": "low"},
                                "price_limits": {"prompt": 2, "completion": 10}},
    "google/gemini-3.8-flash": {"provider": "Google AI Studio", "reasoning": {"effort": "low"},
                                "price_limits": {"prompt": 1, "completion": 5}},
    "anthropic/claude-sonnet-5.5": {"provider": "Anthropic", "reasoning": None,
                                    "price_limits": {"prompt": 2.5, "completion": 12.5}},
    "openai/gpt-6-sol": {"provider": "OpenAI", "reasoning": None,
                         "price_limits": {"prompt": 2.5, "completion": 12.5}},
}
TASKS = {"25": identity_task25_discovery, "33-discovery": identity_task33_discovery,
         "33-change": identity_task33_change}


def execution_limits(task):
    """Initial model call plus one model continuation per execution round."""
    if task not in TASKS:
        raise ValueError(f"Unknown active task: {task}")
    return 20, 21


def model_spec(model):
    if model not in MODELS:
        raise ValueError(f"Unknown model {model!r}; choose from {sorted(MODELS)}")
    return MODELS[model]


def reasoning_settings(model):
    """The `reasoning` request setting for this model, or None when none should be sent."""
    return model_spec(model)["reasoning"]


def provider_settings(model):
    spec = model_spec(model)
    return {"order": [spec["provider"]], "allow_fallbacks": False, "max_price": spec["price_limits"]}


def request_extra_body(model):
    """Everything sent to OpenRouter beyond the standard chat arguments."""
    body = {"usage": {"include": True}, "provider": provider_settings(model)}
    if reasoning_settings(model) is not None:
        body["reasoning"] = reasoning_settings(model)
    return body


def price_within_limits(model, prices):
    """True if OpenRouter's listed per-token prices are within this model's ceiling and it has no per-request fee."""
    limits = model_spec(model)["price_limits"]
    return not (float(prices["prompt"]) > limits["prompt"] * 1e-6
                or float(prices["completion"]) > limits["completion"] * 1e-6
                or float(prices.get("request", 0) or 0))


def git_provenance():
    """Commit and uncommitted-changes flag of the code behind a run, so runs from different machines can be matched."""
    try:
        run = lambda *args: subprocess.run(["git", *args], cwd=HERE, capture_output=True, text=True, check=True).stdout
        return {"commit": run("rev-parse", "HEAD").strip(), "dirty": bool(run("status", "--porcelain").strip())}
    except (OSError, subprocess.SubprocessError):
        return {"commit": None, "dirty": None}


def default_condition_set(task):
    if task == "33-change":
        return "change-eight"
    if task not in TASKS:
        raise ValueError(f"Unknown active task: {task}")
    return "discovery-seven"


def default_inbox_exposure(task, condition_set):
    if task not in TASKS:
        raise ValueError(f"Unknown active task: {task}")
    return "required" if task == "33-change" else "agent-selected"


BUILTIN_DEFENSES = ("spotlighting_with_delimiting", "repeat_user_prompt")  # AgentDojo's own, as in RQ1
DEFENSES = ("none", *BUILTIN_DEFENSES, *GATE_MODES)


def defense_tag(defense):
    """Output-folder suffix saying which kind of defence ran."""
    if defense == "none":
        return ""
    return ("_gate-" if defense in GATE_MODES else "_defense-") + defense.replace("+", "-")


def install_gate(pipeline, mode, env):
    """Wrap the pipeline's ToolsExecutor in a RecipientGate and snapshot send history from `env`.

    `env` must be the environment as it is before the agent acts: the gate treats mail the
    user had already sent as history, and the agent's own sends must not count.
    """
    gate = None
    for element in pipeline.elements:
        if isinstance(element, ToolsExecutionLoop):
            wrapped = []
            for inner in element.elements:
                if isinstance(inner, ToolsExecutor):
                    gate = RecipientGate(mode, executor=inner)
                    inner = gate
                wrapped.append(inner)
            element.elements = wrapped
    if gate is None:
        raise ValueError("pipeline has no ToolsExecutor to wrap")
    gate.snapshot(env)
    return gate


def build_pipeline(client, model, *, max_iters, required_inbox, defense="none", env=None):
    """The episode pipeline used by main(): model, optional forced inbox read, optional gate.

    `defense` is "none", one of AgentDojo's built-in defences, or a gate mode.
    Returns (pipeline, gate); gate is None unless `defense` is a gate mode.
    """
    if defense not in DEFENSES:
        raise ValueError(f"defense must be one of {DEFENSES}")
    if defense in GATE_MODES and env is None:
        raise ValueError("a gate defense needs the pre-episode environment")
    pipeline = AgentPipeline.from_config(PipelineConfig(
        llm=OpenAILLM(client, model, temperature=0.0), model_id=None,
        defense=defense if defense in BUILTIN_DEFENSES else None, system_message_name=None, system_message=None))
    if required_inbox:
        pipeline.elements = [*pipeline.elements[:2], RequiredInboxExposure(), *pipeline.elements[2:]]
    for element in pipeline.elements:
        if isinstance(element, ToolsExecutionLoop):
            element.max_iters = max_iters
    gate = install_gate(pipeline, defense, env) if defense in GATE_MODES else None
    return pipeline, gate


def gate_summary(defense, gate):
    """Result fields describing what the gate decided during one episode."""
    decisions = [d.as_dict() for d in gate.decisions] if gate else []
    return {"defense": defense, "gate_decisions": decisions,
            "gate_held": sum(d["verdict"] != "allow" for d in decisions)}


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
    parser.add_argument("--task", choices=TASKS, default="33-discovery")
    parser.add_argument("--model", choices=tuple(MODELS), default=MODEL)
    parser.add_argument("--defense", choices=DEFENSES, default="none",
                        help="none, one of AgentDojo's built-in defences, or an RQ3 recipient gate mode "
                             "(origin holds every send in RQ2, so it is normally reported analytically instead of run).")
    parser.add_argument("--inbox-exposure", choices=("required", "agent-selected"), default=None,
                        help="Allow autonomous evidence retrieval in recipient-discovery conditions.")
    parser.add_argument("--conditions", nargs="+", help="Run only these members of the selected condition set (fresh output directory).")
    parser.add_argument("--controlled-inbox", action="store_true",
                        help="Use the selected task's controlled mail fixture")
    parser.add_argument("--condition-set", choices=sorted({name for module in TASKS.values() for name in module.CONDITION_SETS}), default=None,
                        help="Defaults: discovery-seven for discovery; change-eight for 33-change")
    args = parser.parse_args()
    model = args.model
    max_iters, max_calls = execution_limits(args.task)
    if args.condition_set is None:
        args.condition_set = default_condition_set(args.task)
    module = TASKS[args.task]
    if not args.controlled_inbox:
        parser.error("RQ2 experiments require --controlled-inbox.")
    CONDITIONS, CONDITION_SETS, PROMPT = module.CONDITIONS, module.CONDITION_SETS, module.PROMPT
    build_environment, make_suite, score_episode = module.build_environment, module.make_suite, module.score_episode
    environment_version, prompt_version = module.ENVIRONMENT_VERSION, module.PROMPT_VERSION
    if args.condition_set not in CONDITION_SETS:
        parser.error("Selected condition set is not available for this task.")
    selected = CONDITION_SETS[args.condition_set]
    if args.conditions:
        if len(set(args.conditions)) != len(args.conditions) or any(n not in selected for n in args.conditions):
            parser.error("--conditions must be distinct members of the selected condition set.")
        selected = tuple(args.conditions)
    if args.inbox_exposure is None:
        args.inbox_exposure = default_inbox_exposure(args.task, args.condition_set)
    load_dotenv(HERE.parent / ".env")
    load_dotenv(HERE / ".env")
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        raise SystemExit("OPENROUTER_API_KEY missing; no requests made.")
    response = httpx.get("https://openrouter.ai/api/v1/models", timeout=30)
    response.raise_for_status()
    prices = next(m["pricing"] for m in response.json()["data"] if m["id"] == model)
    pi, po = float(prices["prompt"]), float(prices["completion"])
    price_limits = MODELS[model]["price_limits"]
    if not price_within_limits(model, prices):
        raise SystemExit("Price outside configured limits; no paid requests made.")
    required_inbox = args.controlled_inbox and args.inbox_exposure == "required"
    mode = ("required_inbox_first" if required_inbox else
            "controlled_agent_selected" if args.controlled_inbox else "natural_retrieval")
    task_prefix = {"25": "identity_task25_pilot_",
                   "33-discovery": "identity_task33_discovery_pilot_",
                   "33-change": "identity_task33_change_pilot_"}[args.task]
    out = HERE / "runs" / (task_prefix + mode + defense_tag(args.defense) + "_" + args.condition_set + "_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
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
        "max_output_tokens": 4096, "defense": args.defense, "git": git_provenance(),
        "provider": MODELS[model]["provider"],
        "reasoning": reasoning_settings(model),
        "reasoning_metadata_preserved": model in REASONING_FLASH_MODELS,
        "provider_error_handling": "classify_incomplete_without_retry_v1",
        "attachment_schema_version": ATTACHMENT_SCHEMA_VERSION,
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
        if kwargs.get("tools"):
            kwargs["tools"] = explicit_attachment_tools(kwargs["tools"])
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
        kwargs["extra_body"] = request_extra_body(model)
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
        pipeline, gate = build_pipeline(client, model, max_iters=max_iters, required_inbox=required_inbox,
                                        defense=args.defense, env=env)
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
                       "attachment_schema_version": ATTACHMENT_SCHEMA_VERSION,
                       "final_text": text, "error": error,
                       "provider_failure": provider_failure,
                       "api_calls": per_condition_calls, **gate_summary(args.defense, gate)})
        (out / f"{name}_trace.json").write_text(json.dumps(messages, indent=2, default=plain))
        (out / f"{name}_post.json").write_text(env.model_dump_json(indent=2))
        with (out / "results.jsonl").open("a") as f:
            f.write(json.dumps(result) + "\n")
        print(name, result["outcome"], "exposed=", result["attack_exposed"],
              "reported_usd=", round(state["reported_usd"], 5), flush=True)
    print("COMPLETE", json.dumps(state), flush=True)


if __name__ == "__main__":
    main()
