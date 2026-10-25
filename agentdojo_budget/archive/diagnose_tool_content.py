"""Two paid diagnostic requests; never execute returned tool calls.

Replay the saved failing continuation with array/string tool-result content.
All other request settings and message/tool fields are held fixed.
"""
from copy import deepcopy
from datetime import datetime
import json
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv
from openai import OpenAI

HERE = Path(__file__).resolve().parents[1]
SOURCE = HERE / "runs/identity_task33_discovery_pilot_controlled_agent_selected_discovery-five_20261024_122651/api_calls.jsonl"
MODEL = "google/gemini-2.5-flash"


def main():
    load_dotenv(HERE.parent / ".env")
    load_dotenv(HERE / ".env")
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        raise SystemExit("OPENROUTER_API_KEY missing.")
    records = [json.loads(line) for line in SOURCE.read_text().splitlines()]
    original = records[1]["request"]
    prices = httpx.get("https://openrouter.ai/api/v1/models", timeout=30)
    prices.raise_for_status()
    pricing = next(m["pricing"] for m in prices.json()["data"] if m["id"] == MODEL)
    pi, po = float(pricing["prompt"]), float(pricing["completion"])
    if pi > 1e-6 or po > 5e-6 or float(pricing.get("request", 0) or 0):
        raise SystemExit("Prices exceed existing pilot limits.")
    out = HERE / "runs" / ("tool_content_diagnostic_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    out.mkdir()
    config = {"source": str(SOURCE), "source_call_index": 1, "model": MODEL,
              "variants": ["array", "string"], "trials_each": 1,
              "cap_usd": 1.0, "tool_execution": False, "pricing": pricing,
              "temperature": "omitted, as in original adapter request"}
    (out / "config.json").write_text(json.dumps(config, indent=2))
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=key,
                    max_retries=0, timeout=60)
    spent, reported = 0.0, 0.0
    print("OUTPUT", out, flush=True)
    for variant in ("array", "string"):
        payload = deepcopy(original)
        if variant == "string":
            for message in payload["messages"]:
                if message["role"] != "tool" or not isinstance(message.get("content"), list):
                    continue
                blocks = message["content"]
                if not all(b.get("type") == "text" and isinstance(b.get("text"), str) for b in blocks):
                    raise ValueError("Unexpected non-text tool result.")
                message["content"] = "\n".join(b["text"] for b in blocks)
        reserve = (len(json.dumps(payload).encode()) * 2 + 16384) * pi + 4096 * po
        if spent + reserve > 0.95:
            raise RuntimeError("Diagnostic spending cap reached.")
        spent += reserve
        request = {**payload, "model": MODEL, "tool_choice": "auto", "max_tokens": 4096,
                   "extra_body": {"reasoning": {"enabled": False}, "usage": {"include": True},
                                  "provider": {"order": ["Google AI Studio"], "allow_fallbacks": False,
                                               "max_price": {"prompt": 1, "completion": 5}}}}
        (out / f"{variant}_request.json").write_text(json.dumps(request, indent=2))
        try:
            response = client.chat.completions.create(**request)
        except Exception as exc:
            (out / f"{variant}_error.json").write_text(json.dumps({"type": type(exc).__name__,
                                                                     "error": str(exc).replace(key, "[REDACTED]")}))
            raise
        raw = response.model_dump(mode="json")
        (out / f"{variant}_response.json").write_text(json.dumps(raw, indent=2))
        usage = response.usage
        cost = float((usage.model_dump().get("cost") or 0) if usage else 0)
        reported += cost
        if usage:
            spent += max(cost, usage.prompt_tokens * pi + usage.completion_tokens * po) - reserve
        (out / "budget.json").write_text(json.dumps({"accounted_usd": spent, "reported_usd": reported}))
        choice = raw["choices"][0]
        print(json.dumps({"variant": variant, "finish_reason": choice.get("finish_reason"),
                          "message": choice["message"].get("content"),
                          "tool_calls": choice["message"].get("tool_calls"),
                          "prompt_tokens": usage.prompt_tokens if usage else None,
                          "cost_usd": cost}), flush=True)
    print("COMPLETE reported_usd", reported, flush=True)


if __name__ == "__main__":
    main()
