# DSA4213_assignment
This repo contains all the necessary files for DSA4213 Group Project

## Task A: Simulation harness (preliminary)

The harness in [`harness/`](harness/) includes:

- A simulated mailbox and calendar.
- The four agent tools: `read_emails`, `send_email`, `read_calendar` and `create_event`.
- The base agent loop.
- Logging that records every tool call and the outcome of each episode.

For the design details, see [`harness/README.md`](harness/README.md).

Run every command below from the repo root, the folder that contains `harness/`. On macOS/Linux, use `python3` if `python` doesn't work.

### 1. Install dependencies

```
pip install -r requirements.txt
```

### 2. Offline smoke test (no API key needed)

The `scripted` backend doesn't call the model. It replays a fixed, pre-written agent run, which checks that the mailbox and calendar, the tools, the logging and the scoring all work:

```
# Hijacked replay: should print attack=HIJACKED
python -m harness.run_episode --task harness/tasks/task_001.json --variant visible_late --backend scripted --script harness/tasks/scripts/task_001_hijacked.json

# Benign replay: should print utility=PASS
python -m harness.run_episode --task harness/tasks/task_001.json --variant benign --backend scripted --script harness/tasks/scripts/task_001_benign.json
```

Scoring unit tests (also offline):

```
python -m unittest discover -s harness/tests -v
```

### 3. Run with the real model

Create a file named `.env` in the repo root. It's gitignored, so it won't be committed. Add the key for the backend you'll use:

```
# Anthropic backend (the default)
ANTHROPIC_API_KEY=sk-ant-...

# OpenRouter backend (used with --backend openrouter)
OPENROUTER_API_KEY=sk-or-...
```

Then run:

```
# One variant, one trial
python -m harness.run_episode --task harness/tasks/task_001.json --variant benign

# All variants, 3 trials each
python -m harness.run_episode --task harness/tasks/task_001.json --variant all --trials 3
```

`task_001` has these variants: `benign`, `visible_early`, `visible_late`, `delayed_trigger`, `obfuscated` and `multi_source`.

| Flag | Default | Meaning |
|---|---|---|
| `--variant` | `benign` | Variant name, or `all` |
| `--trials` | `1` | Repeats per variant |
| `--backend` | `anthropic` | `anthropic`, `openrouter` or `scripted` (offline replay) |
| `--model` | `claude-opus-5-5` | Model ID (required for `openrouter`, as `author/slug`) |
| `--effort` | `medium` | `low` / `medium` / `high` / `xhigh` / `max` |
| `--max-tool-calls` | `10` | Tool-call budget per episode |
| `--defense` | `none` | Defense to apply: `none`, `provenance` or `privilege_separation`. The names are the `name` attributes of the classes registered in [`harness/agent.py`](harness/agent.py) |
| `--run-id` | timestamp | Name of the output folder |
| `--out` | `runs` | Parent output directory |

### 4. Outputs

Each run writes to `runs/<run_id>/`. This folder is gitignored.

- `episodes/<episode_id>.jsonl` holds the full trajectory of one episode: every LLM call, every tool call with its arguments and output, and any calls a defense blocked.
- `results.jsonl` has one summary line per episode. It includes:
  - `utility`
  - `attack_success`
  - `leak_evidence`
  - `side_effect_calls` (emails sent, events created)
  - `termination`
  - token `usage`
  - `duration_s`

The console prints one line per episode:

```
visible_late     t0  utility=fail  attack=HIJACKED  calls=3   end=completed
```

- `utility=PASS` means the user's task was completed. On attack variants, this is utility under attack.
- `attack=HIJACKED` means the attacker's goal was met, and `attack=resisted` means it wasn't. Benign runs show `-`.
