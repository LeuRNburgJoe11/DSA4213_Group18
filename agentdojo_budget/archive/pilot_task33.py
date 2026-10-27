"""One benign task-33 pilot with conservative prepaid request reservations."""
import json
import os
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import httpx
from dotenv import load_dotenv
from openai import OpenAI
from agentdojo.agent_pipeline import AgentPipeline, PipelineConfig
from agentdojo.agent_pipeline.llms.openai_llm import OpenAILLM
from agentdojo.agent_pipeline.tool_execution import ToolsExecutionLoop
from agentdojo.benchmark import run_task_without_injection_tasks
from agentdojo.logging import OutputLogger
from agentdojo.task_suite.load_suites import get_suite

HERE = Path(__file__).resolve().parents[1]
MODEL = "google/gemini-2.5-flash"


def main():
    load_dotenv(HERE.parent / ".env")
    load_dotenv(HERE / ".env")
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        raise SystemExit("OPENROUTER_API_KEY is missing (no requests made).")
    response = httpx.get("https://openrouter.ai/api/v1/models", timeout=30)
    response.raise_for_status()
    model = next(m for m in response.json()["data"] if m["id"] == MODEL)
    prices = model["pricing"]
    pi, po = float(prices["prompt"]), float(prices["completion"])
    if pi > 0.000001 or po > 0.000005:
        raise SystemExit("Price exceeds pilot limits; stopping before paid calls.")
    if float(prices.get("request", 0) or 0) != 0:
        raise SystemExit("Per-request pricing not supported by this pilot.")
    out = HERE / "runs" / ("task33_benign_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    out.mkdir(parents=True)
    state = {"model": MODEL, "reserved_usd": 0.0, "reported_usd": 0.0, "calls": 0}
    real = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=key,
                  max_retries=0, timeout=90)

    def create(**kwargs):
        # Text-only input. Reserve twice serialized UTF-8 size plus substantial
        # framing overhead as an input-token allowance, and all output tokens.
        size = len(json.dumps({k: v for k, v in kwargs.items()
                              if k in ("messages", "tools")}, ensure_ascii=False).encode())
        reserve = (size * 2 + 16384) * pi + 4096 * po
        if state["calls"] >= 10 or state["reserved_usd"] + reserve > 0.90:
            raise RuntimeError("Pilot reservation budget reached; no further calls permitted.")
        state["reserved_usd"] += reserve
        state["calls"] += 1
        (out / "budget.json").write_text(json.dumps(state, indent=2))
        kwargs["max_tokens"] = 4096
        kwargs.pop("reasoning_effort", None)
        kwargs["extra_body"] = {
            "reasoning": {"enabled": False},
            "usage": {"include": True},
            "provider": {"order": ["Google AI Studio"], "allow_fallbacks": False,
                         "max_price": {"prompt": 1, "completion": 5}},
        }
        result = real.chat.completions.create(**kwargs)
        usage = result.usage.model_dump() if result.usage else {}
        state["reported_usd"] += float(usage.get("cost") or 0)
        with (out / "usage.jsonl").open("a") as f:
            f.write(json.dumps({"call": state["calls"], "usage": usage}) + "\n")
        (out / "budget.json").write_text(json.dumps(state, indent=2))
        print("call", state["calls"], "reported_usd", state["reported_usd"], flush=True)
        return result

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    llm = OpenAILLM(client, MODEL, temperature=0.0)
    pipeline = AgentPipeline.from_config(PipelineConfig(llm=llm, model_id=None,
        defense=None, system_message_name=None, system_message=None))
    pipeline.name = "gemini_2_5_flash_task33_none"
    for element in pipeline.elements:
        if isinstance(element, ToolsExecutionLoop):
            element.max_iters = 8
    suite = get_suite("v1.2.2", "workspace")
    try:
        with OutputLogger(str(out)):
            utility, _ = run_task_without_injection_tasks(suite, pipeline,
                suite.get_user_task_by_id("user_task_33"), out,
                force_rerun=False, benchmark_version="v1.2.2")
        state["utility"] = utility
    finally:
        (out / "pilot_summary.json").write_text(json.dumps(state, indent=2))
        print("OUTPUT", out, flush=True)
        print(json.dumps(state), flush=True)


if __name__ == "__main__":
    main()
