"""
dojo_budget.py — run a SAMPLE of AgentDojo's workspace suite through OpenRouter,
with a hard spending cap.

Commands
--------
  plan    Estimate how many episodes fit in the budget (no API calls needed
          except the public price list).
  pilot   Run a tiny sample (default: 2 user tasks x 1 injection task, no
          defense) per model to MEASURE real cost per episode.
  run     Run the sampled grid: models x defenses x repeats x
          (benign user tasks + user/injection pairs).
  report  Summarise results already on disk into results.csv + a printed table.
  spend   Show money spent so far (from the local ledger).

Key ideas
---------
* Every API call goes through BudgetedClient, which records the cost of each
  call in spend_ledger.jsonl and refuses new calls once the cap is reached.
  The ledger persists across runs, so the cap covers ALL runs from this
  folder, not just one.
* Results are saved by AgentDojo as one JSON trace per episode under runs/.
  Re-running the same command skips episodes that already finished, so a run
  that stops at the budget cap (or crashes) can be resumed.
* Sampling is seeded, so every teammate gets the same task sample.

The API key is read from the OPENROUTER_API_KEY environment variable
(or a .env file next to this script). Never hard-code it.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
LEDGER = HERE / "spend_ledger.jsonl"
RUNS = HERE / "runs"
BENCHMARK_VERSION = "v1.2.2"
SUITE_NAME = "workspace"
ATTACK_NAME = "important_instructions"  # AgentDojo's strongest baseline attack

# ---------------------------------------------------------------------------
# Models. Check the exact IDs with:  python dojo_budget.py plan --list-models
# `prose` is how the attack addresses the model ("This is a message to you, X").
# `provider` pins OpenRouter to one provider so runs are comparable; set it to
# None to let OpenRouter choose. Provider names must match OpenRouter's
# provider list for that model (see the model's page on openrouter.ai).
# ---------------------------------------------------------------------------
MODELS = {
    "sonnet": {"id": "anthropic/claude-sonnet-5.5", "prose": "Claude", "provider": "Anthropic"},
    "gpt6": {"id": "openai/gpt-6-sol", "prose": "GPT-6", "provider": "OpenAI"},
    "gemini": {"id": "google/gemini-3.8-flash", "prose": "Gemini", "provider": "Google AI Studio"},
}

# AgentDojo built-in defenses that need no extra downloads.
# (Add "transformers_pi_detector" if you install `agentdojo[transformers]`.)
DEFENSES = ["none", "spotlighting_with_delimiting", "repeat_user_prompt", "tool_filter"]

# Used by `plan` only when no pilot measurements exist yet. These are ROUGH
# placeholders, not measurements; run `pilot` to replace them.
FALLBACK_TOKENS_PER_EPISODE = {"input": 30_000, "output": 1_500}

SAFETY_MARGIN_USD = 0.25  # stop new calls this far below the cap


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
def load_dotenv() -> None:
    env = HERE / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def safe_name(model_id: str) -> str:
    return model_id.replace("/", "_").replace(":", "_")


def fetch_prices() -> dict[str, dict[str, float]]:
    """USD per token for each OpenRouter model (public endpoint, no key needed)."""
    import httpx

    r = httpx.get("https://openrouter.ai/api/v1/models", timeout=30)
    r.raise_for_status()
    prices = {}
    for m in r.json().get("data", []):
        p = m.get("pricing") or {}
        try:
            prices[m["id"]] = {"input": float(p.get("prompt", 0)), "output": float(p.get("completion", 0))}
        except (TypeError, ValueError):
            continue
    return prices


def read_ledger() -> list[dict]:
    if not LEDGER.exists():
        return []
    with LEDGER.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def total_spent() -> float:
    return sum(e["cost"] for e in read_ledger())


# ---------------------------------------------------------------------------
# Budget-enforcing OpenAI-compatible client
# ---------------------------------------------------------------------------
class BudgetExceeded(RuntimeError):
    pass


class BudgetedClient:
    """Looks like openai.OpenAI to AgentDojo, but meters every call."""

    def __init__(self, real_client, cap_usd: float, prices: dict, provider: str | None):
        self._real = real_client
        self.cap = cap_usd
        self.prices = prices
        self.provider = provider
        self.spent = total_spent()
        self.episode_tag: dict = {}
        self.chat = self._Chat(self)

    class _Chat:
        def __init__(self, outer):
            self.completions = BudgetedClient._Completions(outer)

    class _Completions:
        def __init__(self, outer):
            self.o = outer

        def create(self, **kwargs):
            o = self.o
            if o.spent >= o.cap - SAFETY_MARGIN_USD:
                raise BudgetExceeded(f"Budget cap reached: spent ${o.spent:.2f} of ${o.cap:.2f}")

            extra = dict(kwargs.pop("extra_body", None) or {})
            extra["usage"] = {"include": True}  # ask OpenRouter to report cost
            if o.provider:
                extra["provider"] = {"order": [o.provider], "allow_fallbacks": False, "require_parameters": True}
            kwargs["extra_body"] = extra

            completion = o._real.chat.completions.create(**kwargs)
            o._record(kwargs["model"], completion)
            return completion

    def _record(self, model: str, completion) -> None:
        usage = getattr(completion, "usage", None)
        p_in = getattr(usage, "prompt_tokens", 0) or 0
        p_out = getattr(usage, "completion_tokens", 0) or 0
        cost = getattr(usage, "cost", None)
        if cost is None and usage is not None:
            cost = (getattr(usage, "model_extra", None) or {}).get("cost")
        source = "openrouter"
        if cost is None:  # fall back to list prices
            pr = self.prices.get(model, {"input": 0.0, "output": 0.0})
            cost = p_in * pr["input"] + p_out * pr["output"]
            source = "list_price"
        cost = float(cost)
        self.spent += cost
        entry = {
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "model": model,
            "provider_served": getattr(completion, "provider", None)
            or (getattr(completion, "model_extra", None) or {}).get("provider"),
            "input_tokens": p_in,
            "output_tokens": p_out,
            "cost": cost,
            "cost_source": source,
            **self.episode_tag,
        }
        with LEDGER.open("a") as f:
            f.write(json.dumps(entry) + "\n")


# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------
@dataclass
class Sample:
    user_tasks: list[str]
    injection_tasks: list[str]

    @property
    def episodes_per_config(self) -> int:
        # benign run of each user task + every user x injection pair
        return len(self.user_tasks) + len(self.user_tasks) * len(self.injection_tasks)


def make_sample(n_user: int, n_inj: int, seed: int) -> Sample:
    from agentdojo.task_suite.load_suites import get_suite

    suite = get_suite(BENCHMARK_VERSION, SUITE_NAME)
    rng = random.Random(seed)
    users = sorted(suite.user_tasks, key=lambda s: int(s.split("_")[-1]))
    injs = sorted(suite.injection_tasks, key=lambda s: int(s.split("_")[-1]))
    if n_user > len(users) or n_inj > len(injs):
        sys.exit(f"Suite has {len(users)} user tasks and {len(injs)} injection tasks.")
    pick_u = sorted(rng.sample(users, n_user), key=lambda s: int(s.split("_")[-1]))
    pick_i = sorted(rng.sample(injs, n_inj), key=lambda s: int(s.split("_")[-1]))
    return Sample(pick_u, pick_i)


# ---------------------------------------------------------------------------
# Pipeline construction
# ---------------------------------------------------------------------------
def build_pipeline(model_key: str, defense: str, client: BudgetedClient, max_iters: int):
    from agentdojo.agent_pipeline import AgentPipeline, PipelineConfig
    from agentdojo.agent_pipeline.llms.openai_llm import OpenAILLM
    from agentdojo.agent_pipeline.tool_execution import ToolsExecutionLoop
    from agentdojo.models import MODEL_NAMES

    spec = MODELS[model_key]
    llm = OpenAILLM(client, spec["id"], temperature=0.0)
    llm.name = spec["id"]  # tool_filter sends this name to the API, so keep the real ID here

    pipeline = AgentPipeline.from_config(
        PipelineConfig(
            llm=llm,
            model_id=None,
            defense=None if defense == "none" else defense,
            system_message_name=None,
            system_message=None,
        )
    )
    # A filesystem-safe name so AgentDojo can save AND reload traces (resume).
    pipeline.name = f"{safe_name(spec['id'])}-{defense}"
    # Let the "important message" attack address the model by name.
    MODEL_NAMES[safe_name(spec["id"])] = spec["prose"]

    # Cap the tool-call loop (proposal: N <= 10). Fewer iterations = lower worst-case cost.
    for el in pipeline.elements:
        if isinstance(el, ToolsExecutionLoop):
            el.max_iters = max_iters
    return pipeline


def make_client(model_key: str, cap: float, prices: dict) -> BudgetedClient:
    import openai

    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        sys.exit("Set OPENROUTER_API_KEY in your environment or in a .env file next to this script.")
    real = openai.OpenAI(base_url="https://openrouter.ai/api/v1", api_key=key, max_retries=2)
    return BudgetedClient(real, cap, prices, MODELS[model_key]["provider"])


# ---------------------------------------------------------------------------
# Running episodes
# ---------------------------------------------------------------------------
def run_grid(models, defenses, repeats, sample: Sample, cap: float, max_iters: int, phase: str) -> None:
    from agentdojo.attacks.attack_registry import load_attack
    from agentdojo.benchmark import run_task_with_injection_tasks, run_task_without_injection_tasks
    from agentdojo.logging import OutputLogger
    from agentdojo.task_suite.load_suites import get_suite

    suite = get_suite(BENCHMARK_VERSION, SUITE_NAME)
    prices = fetch_prices()
    for m in models:
        if MODELS[m]["id"] not in prices:
            print(f"WARNING: {MODELS[m]['id']} not found in OpenRouter's model list. Check the ID.")

    total = len(models) * len(defenses) * repeats * sample.episodes_per_config
    print(f"Sample: {len(sample.user_tasks)} user tasks {sample.user_tasks}")
    print(f"        {len(sample.injection_tasks)} injection tasks {sample.injection_tasks}")
    print(f"Episodes planned: {total}  |  spent so far ${total_spent():.2f} of ${cap:.2f}\n")

    done = 0
    try:
        for r in range(repeats):
            logdir = RUNS / f"repeat_{r}"
            with OutputLogger(str(logdir)):
                for m in models:
                    client = make_client(m, cap, prices)
                    for d in defenses:
                        pipeline = build_pipeline(m, d, client, max_iters)
                        attack = load_attack(ATTACK_NAME, suite, pipeline)
                        for ut_id in sample.user_tasks:
                            ut = suite.get_user_task_by_id(ut_id)
                            tag = {"phase": phase, "repeat": r, "model_key": m, "defense": d, "user_task": ut_id}

                            client.episode_tag = {**tag, "injection_task": "none"}
                            run_task_without_injection_tasks(
                                suite, pipeline, ut, logdir, force_rerun=False, benchmark_version=BENCHMARK_VERSION
                            )
                            done += 1
                            for inj_id in sample.injection_tasks:
                                client.episode_tag = {**tag, "injection_task": inj_id}
                                run_task_with_injection_tasks(
                                    suite, pipeline, ut, attack, logdir, force_rerun=False,
                                    injection_tasks=[inj_id], benchmark_version=BENCHMARK_VERSION,
                                )
                                done += 1
                            print(f"  [{done}/{total}] {m} | {d} | rep {r} | {ut_id}  "
                                  f"(spent ${client.spent:.2f})")
    except BudgetExceeded as e:
        print(f"\nSTOPPED: {e}\nCompleted episodes are saved. Raise --budget or shrink the sample to continue.")
    print(f"\nFinished {done}/{total} episodes. Total spent: ${total_spent():.2f}")


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def collect_results(models, defenses, repeats, sample: Sample) -> list[dict]:
    from agentdojo.benchmark import load_task_results

    rows = []
    for r in range(repeats):
        logdir = RUNS / f"repeat_{r}"
        for m in models:
            for d in defenses:
                pname = f"{safe_name(MODELS[m]['id'])}-{d}"
                for ut in sample.user_tasks:
                    pairs = [("none", "none")] + [(ATTACK_NAME, i) for i in sample.injection_tasks]
                    for attack_name, inj in pairs:
                        try:
                            res = load_task_results(pname, SUITE_NAME, ut, attack_name, inj, logdir)
                        except Exception:
                            continue  # not run yet / incomplete trace
                        rows.append({
                            "repeat": r, "model": m, "defense": d, "user_task": ut,
                            "injection_task": inj, "utility": int(res.utility),
                            # AgentDojo's `security` is True when the ATTACKER succeeded.
                            "attack_success": int(res.security) if inj != "none" else "",
                        })
    return rows


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / den
    return (max(0.0, centre - half), min(1.0, centre + half))


def summarise(rows: list[dict]) -> None:
    groups = defaultdict(lambda: {"benign": [], "ua": [], "asr": []})
    for row in rows:
        g = groups[(row["model"], row["defense"])]
        if row["injection_task"] == "none":
            g["benign"].append(row["utility"])
        else:
            g["ua"].append(row["utility"])
            g["asr"].append(row["attack_success"])

    def fmt(xs):
        if not xs:
            return "   —   "
        lo, hi = wilson(sum(xs), len(xs))
        return f"{100*sum(xs)/len(xs):5.1f}% [{100*lo:.0f}-{100*hi:.0f}] n={len(xs)}"

    print(f"{'model':8} {'defense':30} {'benign utility':24} {'utility under attack':24} {'targeted ASR':24}")
    for (m, d), g in sorted(groups.items()):
        print(f"{m:8} {d:30} {fmt(g['benign']):24} {fmt(g['ua']):24} {fmt(g['asr']):24}")
    print("\nBrackets are 95% Wilson intervals. Small n means wide intervals — report them.")


# ---------------------------------------------------------------------------
# Budget planning
# ---------------------------------------------------------------------------
def measured_cost_per_episode() -> dict[tuple[str, str], float]:
    """Average $ per COMPLETED episode from the ledger, keyed by (model_key, defense).
    Episodes cut off by the budget stop are ignored so they don't skew the estimate."""
    from agentdojo.benchmark import load_task_results

    per_episode = defaultdict(float)
    for e in read_ledger():
        if "model_key" not in e:
            continue
        key = (e["model_key"], e["defense"], e["repeat"], e["user_task"], e["injection_task"])
        per_episode[key] += e["cost"]
    sums, counts = defaultdict(float), defaultdict(int)
    for (m, d, r, ut, inj), c in per_episode.items():
        attack_name = "none" if inj == "none" else ATTACK_NAME
        pname = f"{safe_name(MODELS[m]['id'])}-{d}" if m in MODELS else None
        try:
            load_task_results(pname, SUITE_NAME, ut, attack_name, inj, RUNS / f"repeat_{r}")
        except Exception:
            continue
        m_d = (m, d)
        sums[m_d] += c
        counts[m_d] += 1
    return {k: sums[k] / counts[k] for k in sums}


def plan(models, defenses, repeats, sample: Sample, cap: float) -> None:
    prices = fetch_prices()
    measured = measured_cost_per_episode()
    remaining = cap - total_spent()
    print(f"Budget ${cap:.2f}, already spent ${total_spent():.2f}, remaining ${remaining:.2f}\n")
    print(f"Episodes per (model, defense, repeat): {sample.episodes_per_config} "
          f"= {len(sample.user_tasks)} benign + {len(sample.user_tasks)}x{len(sample.injection_tasks)} attacked\n")

    grand = 0.0
    print(f"{'model':8} {'defense':30} {'$/episode':>10} {'source':28} {'subtotal':>10}")
    for m in models:
        mid = MODELS[m]["id"]
        base = measured.get((m, "none"))
        for d in defenses:
            if (m, d) in measured:
                cpe, src = measured[(m, d)], "measured (pilot/run)"
            elif base is not None:
                cpe, src = base, "measured, no-defense value"
            elif mid in prices:
                pr = prices[mid]
                cpe = FALLBACK_TOKENS_PER_EPISODE["input"] * pr["input"] + FALLBACK_TOKENS_PER_EPISODE["output"] * pr["output"]
                src = "GUESS from list price"
            else:
                cpe, src = float("nan"), "unknown model ID"
            sub = cpe * sample.episodes_per_config * repeats
            grand += sub
            print(f"{m:8} {d:30} {cpe:>10.4f} {src:28} {sub:>10.2f}")
    print(f"\nEstimated total: ${grand:.2f}  vs remaining ${remaining:.2f}  ->  "
          f"{'FITS' if grand <= remaining else 'OVER BUDGET'}")
    if not measured:
        print("Note: no pilot data yet, so per-episode costs are guesses. Run `pilot` first (costs cents).")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    load_dotenv()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["plan", "pilot", "run", "report", "spend"])
    ap.add_argument("--models", nargs="+", default=list(MODELS), choices=list(MODELS))
    ap.add_argument("--defenses", nargs="+", default=["none"], choices=DEFENSES)
    ap.add_argument("--n-user", type=int, default=5, help="user tasks sampled from 40")
    ap.add_argument("--n-inj", type=int, default=3, help="injection tasks sampled from 14")
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--seed", type=int, default=4213)
    ap.add_argument("--budget", type=float, default=15.0, help="hard cap in USD across ALL runs in this folder")
    ap.add_argument("--max-iters", type=int, default=10, help="max agent loop iterations per episode")
    ap.add_argument("--list-models", action="store_true", help="with `plan`: show matching OpenRouter IDs")
    a = ap.parse_args()

    if a.command == "spend":
        rows = read_ledger()
        by_model = defaultdict(float)
        for e in rows:
            by_model[e["model"]] += e["cost"]
        for k, v in sorted(by_model.items()):
            print(f"{k:40} ${v:.4f}")
        print(f"{'TOTAL':40} ${total_spent():.4f}  ({len(rows)} API calls)")
        return

    if a.command == "plan" and a.list_models:
        prices = fetch_prices()
        for word in ("claude-sonnet", "gpt-6", "gemini"):
            for mid, pr in sorted(prices.items()):
                if word in mid:
                    print(f"{mid:45} in ${pr['input']*1e6:7.3f}/M  out ${pr['output']*1e6:7.3f}/M")
        return

    if a.command == "pilot":
        sample = make_sample(2, 1, a.seed)
        run_grid(a.models, ["none"], 1, sample, a.budget, a.max_iters, phase="pilot")
        print("\nPilot cost per episode:")
        for (m, d), c in sorted(measured_cost_per_episode().items()):
            print(f"  {m:8} {d:30} ${c:.4f}")
        return

    sample = make_sample(a.n_user, a.n_inj, a.seed)
    if a.command == "plan":
        plan(a.models, a.defenses, a.repeats, sample, a.budget)
    elif a.command == "run":
        run_grid(a.models, a.defenses, a.repeats, sample, a.budget, a.max_iters, phase="run")
        rows = collect_results(a.models, a.defenses, a.repeats, sample)
        if rows:
            summarise(rows)
    elif a.command == "report":
        rows = collect_results(a.models, a.defenses, a.repeats, sample)
        if not rows:
            sys.exit("No finished episodes found for this sample.")
        with (HERE / "results.csv").open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        summarise(rows)
        print(f"\nPer-episode rows written to {HERE / 'results.csv'}")


if __name__ == "__main__":
    main()
