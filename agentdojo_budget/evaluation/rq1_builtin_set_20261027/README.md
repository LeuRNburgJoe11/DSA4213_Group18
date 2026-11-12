# RQ1 built-in defense evidence set

This directory holds the episode evidence for the AgentDojo built-in defenses run on the RQ2 identity tasks in `manifest.json`: 132 episodes (22 conditions x 3 models x 2 settings), across 18 original run directories (`spotlighting_with_delimiting` and `repeat_user_prompt`).

## Layout

```text
rq1_builtin_set_20261027/
├── manifest.json             # Original run selection, settings, provenance and costs
├── episodes.csv              # Episode outcomes (automatic labels, plus gate columns)
├── SUMMARY.md                # Summary table and reading of the columns
├── evidence_index.csv        # Relative trace/pre/post paths for each episode
├── run_map.csv               # Short evidence folder name -> original run directory
├── evidence_sha256.txt       # SHA-256 hashes of the 432 copied evidence files
├── README.md
└── evidence/
    └── <model>_<task>_<defense>/
        ├── config.json
        ├── results.jsonl
        ├── <condition>_trace.json
        ├── <condition>_pre.json
        └── <condition>_post.json
```

There are 132 trace files, 132 pre-state snapshots, 132 post-state snapshots, 18 configurations and 18 result files (432 files). Files were copied byte-for-byte from `agentdojo_budget/runs/`; the originals were not modified. Evidence folders use short names (`<model>_<task>_<defense>`, for example `gemini_t33-disc_identity`) so that paths stay under Windows' 260-character limit. The original run-directory names are kept in `manifest.json` and `episodes.csv`, and `run_map.csv` maps each short name to its original run directory. Use `evidence_index.csv` to find a given model/task/condition directly.

## Interpreting the evidence

- Traces record the visible messages, tool calls and observations; they do not establish hidden model reasoning.
- Pre/post snapshots support checking identity evidence and the actual environment changes, independently of an agent's completion claim.
- `results.jsonl` preserves automatic scoring. Clarification labels in this set are automatic and were not manually reviewed.
- This set contains single trials, not stable model-wide failure-rate estimates.
- Absolute/local paths inside original configurations are provenance, not portable paths. Provenance (commit, `dirty` flag) is in `manifest.json`.

## Integrity verification

From this directory:

```sh
sha256sum -c evidence_sha256.txt
```

`api_calls.jsonl`, budget logs and unrelated runs were intentionally not copied.
