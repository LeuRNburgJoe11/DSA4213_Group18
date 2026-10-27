# AgentDojo on a $15 budget (DSA4213 Group 18)

Runs a **seeded sample** of AgentDojo's `workspace` suite (40 user tasks, 14 injection
tasks in benchmark v1.2.2) through OpenRouter, with a **hard spending cap**.

AgentDojo has no training split: all of its tasks are evaluation tasks. "Sampling" here
means picking a fixed subset of user and injection tasks, so everyone runs the same subset.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env      # then paste the OpenRouter key into .env (never commit it)
```

`.env` is already listed in `.gitignore`.

## Workflow

```bash
# 1. Confirm the exact OpenRouter model IDs and prices (public, free)
python dojo_budget.py plan --list-models
#    If an ID differs, edit the MODELS dict at the top of dojo_budget.py.

# 2. Pilot: 2 user tasks x 1 injection task, no defense, per model. Measures real $/episode.
python dojo_budget.py pilot

# 3. Plan: try different sample sizes until the estimate fits
python dojo_budget.py plan --n-user 5 --n-inj 3 --defenses none spotlighting_with_delimiting --repeats 1

# 4. Run exactly the plan you chose (same flags)
python dojo_budget.py run  --n-user 5 --n-inj 3 --defenses none spotlighting_with_delimiting --repeats 1

# 5. Results table + results.csv (same flags again)
python dojo_budget.py report --n-user 5 --n-inj 3 --defenses none spotlighting_with_delimiting --repeats 1

# Any time: money spent so far
python dojo_budget.py spend
```

## Episode count

For each model × defense × repeat, the script runs:

```
episodes = n_user (benign)  +  n_user × n_inj (attacked)
```

| Option | Models | Defenses | n_user × n_inj | Repeats | Episodes |
|---|---|---|---|---|---|
| A: model comparison | 3 | none | 5 × 3 | 1 | 60 |
| B: defense comparison | 1 | none + 3 built-ins | 5 × 3 | 2 | 160 |
| C: both | 3 | none + 1 | 8 × 4 | 1 | 240 |

Multiply by the measured $/episode from the pilot to see what fits.

## How the budget cap works

- Every API call is metered and logged to `spend_ledger.jsonl` (cost reported by OpenRouter,
  or list price × tokens if OpenRouter doesn't report it).
- Before each call, the script refuses to continue once spending reaches the cap minus a
  $0.25 safety margin. The cap covers **all runs from this folder**, not just one.
- If a run stops at the cap, finished episodes are kept. Re-running the same command skips
  them and redoes only the episode that was cut off.

## Things to know

- **The ledger is per folder.** If two teammates run from different laptops, each ledger only
  sees its own spend. Either have one person run everything, or check the OpenRouter dashboard,
  which is the real source of truth for money spent.
- **Worst case per episode.** The agent loop is capped at `--max-iters` (default 10, matching
  the proposal). AgentDojo also retries an episode up to 3 times if the model never gives a final
  answer, so one stuck episode can cost about 3 × 11 calls. The cap still stops it.
- **Provider pinning.** Each model is pinned to one OpenRouter provider (no fallbacks) so runs are
  comparable. If a request fails with a provider error, check the provider names on the model's
  OpenRouter page and edit `provider` in `MODELS` (or set it to `None`).
- **Small samples mean wide confidence intervals.** The report prints 95% Wilson intervals. Put
  them on your slides.
- **Attack.** Uses AgentDojo's `important_instructions` attack, the strongest baseline in the paper.
  In the results, `attack_success = 1` means the attacker's goal was met (AgentDojo calls this
  `security`).
- **Your own defenses** (privilege separation, classifier gate, hybrid) and your RQ2–RQ4 task
  variants are not included yet. They plug into `build_pipeline()` and a custom task suite.
