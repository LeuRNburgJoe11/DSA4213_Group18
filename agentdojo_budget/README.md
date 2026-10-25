# RQ2: recipient identity experiments

This folder has exactly three active task variants. Run commands from the
repository root (the directory containing agentdojo_budget).

| Variant | CLI selector | Default conditions | Default received-mail exposure |
| --- | --- | --- | --- |
| Task33 recipient discovery | 33-discovery | discovery-seven (7) | Agent selects retrieval |
| Task25 multi-recipient discovery | 25 | discovery-seven (7) | Agent selects retrieval |
| Task33 address changes | 33-change | change-eight (8: four evidence conditions × two address assignments) | Required before the first model decision |

Sent-mail retrieval is autonomous for all three. General mail search can return
sent records too. Exposure is measured from actual tool results, not merely from
the presence of a message in the environment. The RQ3 gate (defenses/recipient_gate.py) is switched on with `--defense origin+readers` or `--defense origin+identity` (default `none` = no gate; `origin` holds every send in these tasks, so it is reported analytically rather than run). Each condition's gate decisions are saved in results.jsonl as `gate_decisions` and `gate_held`, and gated runs write to a `_gate-<mode>` folder.

## Active files

```text
identity/identity_task33_discovery.py   John: discover recipient from correspondence
identity/identity_task25_discovery.py   David: discover recipient; complete Linda/Mark work
identity/identity_task33_change.py      Retain or replace an established recipient address
identity/identity_common.py             Shared constants, clarification and delivery checks
defenses/recipient_gate.py              RQ3: evidence-based recipient verification gate
run_identity_pilot.py                   One trial per selected condition; shared US$1 cap
inbox_exposure.py                       Required inbox read, where selected
provider_compat.py                      Gemini reasoning metadata and provider-error labels
tests/test_*.py                         Offline tests for the active setup and the gate
IDENTITY_TASK*_DISCOVERY.md             Detailed discovery protocols
IDENTITY_TASK33_CHANGE.md               Detailed change protocol
archive/                                Earlier tasks, diagnostics and benchmark scripts
runs/                                   All existing raw results, preserved in place
```


## Setup and offline checks

Install agentdojo_budget/requirements.txt into the project virtual environment.
OPENROUTER_API_KEY is read from the repository or agentdojo_budget .env file.
Do not commit credentials. Offline tests need no API key or network:

```sh
.venv/bin/python -m unittest discover -s agentdojo_budget -p 'test_*.py'
.venv/bin/python -m agentdojo_budget.run_identity_pilot --help
```

The archive deliberately is not an offline-test discovery package; old tests
and command examples are historical rather than the current CLI contract.

## Paid pilots: run only when intended

These commands each start a separate paid run, not one combined run:

```sh
.venv/bin/python -m agentdojo_budget.run_identity_pilot --task 33-discovery --controlled-inbox --model google/gemini-3.5-flash
.venv/bin/python -m agentdojo_budget.run_identity_pilot --task 25 --controlled-inbox --model google/gemini-3.5-flash
.venv/bin/python -m agentdojo_budget.run_identity_pilot --task 33-change --controlled-inbox --model google/gemini-3.5-flash
```

The CLI defaults to 33-discovery and Gemini 2.5 Flash if selectors are omitted.
Gemini 3.5/3.8 Flash use low reasoning effort with opaque reasoning metadata
preserved; 2.5 uses reasoning disabled. There are 20 execution rounds / 21 API
calls per condition. The US$1 cap covers one invocation, NOT cumulative spending
across separate runs. Prices/provider checks may stop a run before that cap.
Provider errors are recorded separately; no automatic recovery is performed.

Both discovery variants also accept discovery-five, history-vs-context and
history-vs-contradiction. Address change accepts change-four and change-reversed.
Use --conditions to run individual members of a chosen set. Use
--inbox-exposure required or agent-selected to override a protocol explicitly;
compare different exposure modes separately. All setups require --controlled-inbox.

## Detailed protocols

- IDENTITY_TASK33_DISCOVERY.md: discovery evidence, history and context probes.
- IDENTITY_TASK25_DISCOVERY.md: same seven conditions plus unaffected-work metrics.
- IDENTITY_TASK33_CHANGE.md: unsupported, familiar and authorised address updates.

Always distinguish actual misdelivery from a missed preferred action. Context
accuracy is not authenticated identity; history preferences assume the original
relationship is genuine. Clarification heuristics require manual review, and
semantic summary/assignment quality is not fully automatically evaluated.

Earlier compact-six/core-seven tasks, the initial benchmark driver and transport
diagnostics are retained under archive/. Old --task 33 and legacy condition sets
are no longer offered by the active runner. All previous results remain under
runs/ with their original configuration, prompts, fixtures and labels.
