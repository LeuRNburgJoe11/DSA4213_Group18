# Historical pilots and diagnostics

These files are archived, not deleted. They are outside the active three-variant
RQ2 runner. Existing result directories remain in ../runs/ and have not moved.

- identity_task.py / IDENTITY_TASK.md: earlier task33 established-address pilots.
- identity_task25.py / IDENTITY_TASK25.md: earlier task25 core-seven pilots.
- test_identity_task*.py: corresponding historical checks.
- pilot_task33.py: initial unmodified AgentDojo task33 benign pilot.
- diagnose_tool_content.py: array/string request diagnostic.
- replay_archived_benign.py: historical replay and single-factor diagnostics.
- dojo_budget.py / README_forbudget.md: original generic AgentDojo benchmark driver.

Imports and script base directories were adjusted for relocation. Archived
scripts retain the original agentdojo_budget/runs output/source location and .env
lookup locations. Do not run them unintentionally: some launch paid requests.
Historical documentation may show obsolete module paths or active-runner flags;
use module paths under agentdojo_budget.archive for archived scripts.

The active runner no longer offers --task 33, compact-six or core-seven. Read
../README.md for the three supported variants. Archived tests that refer to the
former CLI are historical; active offline tests do not recurse into this folder.
