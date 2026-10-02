"""Entry point: run episodes end-to-end and score them.

Examples (run from the project root):

  # Offline smoke test, no API key needed: replay a scripted trajectory
  python -m harness.run_episode --task harness/tasks/task_001.json --variant visible_late \
      --backend scripted --script harness/tasks/scripts/task_001_hijacked.json

  # Real model, every variant, 3 trials each
  python -m harness.run_episode --task harness/tasks/task_001.json --variant all --trials 3

Outputs go to runs/<run_id>/: one trajectory JSONL per episode under episodes/,
and one summary line per episode in results.jsonl.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from harness.agent import DEFAULT_MODEL, DEFENSES, Agent, AnthropicBackend, LLMBackend, ScriptedBackend
from harness.checks import evaluate, leak_evidence
from harness.logger import EpisodeLogger, append_result
from harness.state import Environment

SLOT = re.compile(r"\{\{(\w+)\}\}")


def load_task(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _fill(obj, slots: dict[str, str], seen: set[str]):
    """Recursively replace {{slot}} placeholders; unfilled slots become ''."""
    if isinstance(obj, str):
        def sub(m: re.Match) -> str:
            seen.add(m.group(1))
            return slots.get(m.group(1), "")
        return SLOT.sub(sub, obj)
    if isinstance(obj, list):
        return [_fill(v, slots, seen) for v in obj]
    if isinstance(obj, dict):
        return {k: _fill(v, slots, seen) for k, v in obj.items()}
    return obj


def build_environment(task: dict, variant: str) -> Environment:
    if variant not in task["variants"]:
        raise SystemExit(f"unknown variant {variant!r}; choose from {sorted(task['variants'])}")
    slots = task["variants"][variant].get("slots", {})
    seen: set[str] = set()
    filled = _fill(task["environment"], slots, seen)
    unknown = set(slots) - seen
    if unknown:  # catches typos in slot names, which would silently drop an injection
        raise SystemExit(f"variant {variant!r} fills slots not present in the environment: {sorted(unknown)}")
    return Environment.from_dict(filled)


def run_episode(task: dict, variant: str, backend: LLMBackend, defense_name: str,
                run_dir: Path, trial: int = 0, max_tool_calls: int = 10) -> dict:
    v = task["variants"][variant]
    is_attack = v.get("kind") != "benign"
    env = build_environment(task, variant)
    defense = DEFENSES[defense_name]()
    episode_id = f"{task['id']}__{variant}__{defense_name}__t{trial}"
    logger = EpisodeLogger(run_dir, episode_id)
    logger.episode_start(task_id=task["id"], variant=variant, variant_meta=v, defense=defense_name,
                         trial=trial, max_tool_calls=max_tool_calls, llm=backend.describe(),
                         user_prompt=task["user_prompt"])

    agent = Agent(backend, defense, max_tool_calls=max_tool_calls)
    t0 = time.perf_counter()
    error = None
    try:
        result = agent.run(task["user_prompt"], env, logger)
        termination, final_text, turns = result.termination, result.final_text, result.turns
    except Exception as exc:  # keep the batch going; the episode is recorded as an error
        termination, final_text, turns = "error", "", None
        error = f"{type(exc).__name__}: {exc}"
    duration = time.perf_counter() - t0

    utility, utility_detail = evaluate(env, task["utility_checks"])
    attack_success = None
    if is_attack:
        attack_success, _ = evaluate(env, task["attacker_goal"]["checks"])

    summary = {
        "episode_id": episode_id,
        "task_id": task["id"],
        "variant": variant,
        "injection_kind": v.get("kind"),
        "injection_position": v.get("position"),
        "defense": defense_name,
        "trial": trial,
        "llm": backend.describe(),
        "termination": termination,
        "error": error,
        "utility": utility,  # on attack variants this is utility-under-attack
        "utility_checks": utility_detail,
        "attack_success": attack_success,
        "leak_evidence": leak_evidence(env, task["attacker_goal"]["checks"]) if is_attack else [],
        "turns": turns,
        "tool_calls": len([c for c in logger.tool_calls if c.executed or c.blocked]),
        "side_effect_calls": [{"name": c.name, "args": c.args} for c in logger.side_effect_calls],
        "blocked_calls": [{"name": c.name, "args": c.args, "reason": c.block_reason}
                          for c in logger.blocked_calls],
        "usage": logger.usage,
        "duration_s": round(duration, 2),
        "final_text": final_text,
        "final_state": {
            "sent": [e.__dict__ for e in env.mailbox.sent_by_agent],
            "created_events": [e.__dict__ for e in env.calendar.created_by_agent],
        },
    }
    logger.episode_end(termination=termination, error=error, utility=utility,
                       attack_success=attack_success, final_text=final_text)
    append_result(run_dir, summary)
    return summary


def make_backend(args: argparse.Namespace) -> LLMBackend:
    if args.backend == "scripted":
        if not args.script:
            raise SystemExit("--backend scripted needs --script")
        with open(args.script, encoding="utf-8") as fh:
            return ScriptedBackend(json.load(fh))
    return AnthropicBackend(model=args.model, effort=args.effort, fallbacks=args.fallbacks)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Run prompt-injection evaluation episodes.")
    p.add_argument("--task", required=True, help="path to a task JSON file")
    p.add_argument("--variant", default="benign", help="variant name, or 'all'")
    p.add_argument("--defense", default="none", choices=sorted(DEFENSES))
    p.add_argument("--trials", type=int, default=1, help="repeats per variant (sampling variance)")
    p.add_argument("--max-tool-calls", type=int, default=10)
    p.add_argument("--backend", default="anthropic", choices=["anthropic", "scripted"])
    p.add_argument("--script", help="scripted backend: path to a JSON list of turns")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--effort", default="medium", choices=["low", "medium", "high", "xhigh", "max"])
    p.add_argument("--fallbacks", action="store_true",
                   help="enable server-side refusal fallback (mixes models; off by default)")
    p.add_argument("--run-id", default=None, help="output folder name under --out")
    p.add_argument("--out", default="runs")
    args = p.parse_args(argv)

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    task = load_task(args.task)
    variants = sorted(task["variants"]) if args.variant == "all" else [args.variant]
    run_id = args.run_id or datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = Path(args.out) / run_id

    print(f"run {run_id}: task={task['id']} defense={args.defense} variants={variants} trials={args.trials}")
    for variant in variants:
        for trial in range(args.trials):
            backend = make_backend(args)  # fresh backend per episode (resets scripted replay)
            s = run_episode(task, variant, backend, args.defense, run_dir, trial, args.max_tool_calls)
            asr = "-" if s["attack_success"] is None else ("HIJACKED" if s["attack_success"] else "resisted")
            print(f"  {variant:<16} t{trial}  utility={'PASS' if s['utility'] else 'fail':<4}  "
                  f"attack={asr:<8}  calls={s['tool_calls']:<2}  end={s['termination']}"
                  + (f"  error={s['error']}" if s["error"] else ""))
    print(f"results: {run_dir / 'results.jsonl'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
