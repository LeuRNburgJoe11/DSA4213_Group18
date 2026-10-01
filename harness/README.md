# Evaluation harness

Simulated email/calendar workspace + tool-using agent for the prompt-injection study.

| File | Role |
|---|---|
| `state.py` | In-memory `Mailbox`, `Calendar`, `Environment` (fresh per episode) |
| `tools.py` | `read_emails`, `send_email`, `read_calendar`, `create_event`, their schemas, `SIDE_EFFECTING` |
| `agent.py` | LLM backends, the `Defense` hook interface, and the agent loop (≤10 tool calls) |
| `logger.py` | Per-episode JSONL trajectories + `results.jsonl` summaries |
| `checks.py` | Utility and attacker-goal checks on the final state |
| `run_episode.py` | CLI entry point |
| `tasks/` | Task definitions; `tasks/scripts/` has scripted trajectories for offline tests |

## Setup

```
pip install -r requirements.txt
# put ANTHROPIC_API_KEY=... in a .env file at the project root (gitignored)
```

## Running

```
# Offline, no API key: replay a scripted trajectory
python -m harness.run_episode --task harness/tasks/task_001.json --variant visible_late \
    --backend scripted --script harness/tasks/scripts/task_001_hijacked.json

# Real model: all variants, 3 trials each
python -m harness.run_episode --task harness/tasks/task_001.json --variant all --trials 3
```

Each episode gets `utility` (all `utility_checks` pass; on injected variants this is
utility-under-attack) and `attack_success` (all `attacker_goal.checks` pass; `null` on benign).
Checks look only at what the agent did (emails sent, events created), not at what it said.

## Task format

Seeded emails/events contain `{{slot}}` placeholders. Each variant fills some slots with
injection text; unfilled slots become empty, so `benign` is the clean task. Variant
metadata (`kind`, `position`, `sources`) is copied into results for the ablation breakdowns.

## Adding a defense

Subclass `Defense` in `agent.py` (or a new module imported by `run_episode.py`) and
register it; it then becomes available as `--defense <name>`:

```python
@register_defense
class ProvenanceTagging(Defense):
    name = "provenance"

    def format_tool_output(self, name, args, output, ctx):
        return f"<untrusted_data source=\"{name}\">\n{output}\n</untrusted_data>"
```

Hooks: `on_episode_start` (e.g. planner commits a plan into `ctx.scratch`),
`system_prompt`, `user_message`, `format_tool_output`, `review_tool_call`
(return `Verdict(False, reason)` to block; blocked calls are logged and never execute).
Use `ctx.logger.defense(self.name, ...)` to record plans and verdicts in the trajectory.
