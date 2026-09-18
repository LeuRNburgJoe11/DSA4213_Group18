# DSA4213 Assignment 1 — Project Plan

**Due:** October 16, 2026, 11:59pm SGT
**Today:** September 9, 2026 (~5.5 weeks available)

---

## 1. Repository / Code Structure

```
dsa4213-a1/
├── README.md                  # setup, data access, commands, seeds
├── requirements.txt / env.yml
├── data/
│   ├── raw/                   # original corpus (or download script)
│   ├── processed/             # tokenized, split train/val/test
│   └── prepare_data.py
├── src/
│   ├── tokenizer.py            # shared vocab/tokenizer for Parts I & II
│   ├── models/
│   │   ├── ngram.py
│   │   ├── rnn_lm.py
│   │   ├── lstm_lm.py
│   │   └── transformer_lm.py
│   ├── embeddings/
│   │   ├── train_skipgram.py   # or CBOW/GloVe — your own embeddings
│   │   └── load_pretrained.py  # public GloVe loading + coverage check
│   ├── train.py                # generic training loop (used by all LMs)
│   ├── evaluate.py             # perplexity / cross-entropy, timing
│   ├── generate.py             # prompt-based generation, matched decoding
│   ├── downstream/
│   │   ├── extract_reps.py     # pooling: last-hidden vs mean-pool
│   │   ├── classifier.py       # simple classifier head
│   │   └── evaluate_task.py    # accuracy/macro-F1, error analysis
│   └── utils/
│       ├── seed.py
│       └── logging.py
├── notebooks/                  # exploratory analysis, plots
├── configs/                    # one YAML/JSON per experiment run
│   ├── partI_ngram.yaml
│   ├── partI_rnn.yaml
│   ├── partI_lstm.yaml
│   ├── partI_transformer.yaml
│   ├── partII_own_embed.yaml
│   ├── partII_public_embed.yaml
│   └── partIII_downstream.yaml
├── results/
│   ├── logs/                   # loss curves, training logs
│   ├── metrics.csv             # consolidated table across all runs
│   └── generations.md          # side-by-side generated text samples
└── report/
    └── report.pdf (≤ 6 pages)
```

**Design principle:** every model shares the same `tokenizer.py`, `train.py`, and `evaluate.py` where possible, so Part I comparisons are fair, and Part II only swaps the embedding layer without touching anything else.

---

## 2. Report Structure (≤ 6 pages + appendices)

1. **Setup** — corpus, preprocessing, split, vocab size, tokenization choice, downstream dataset (brief).
2. **Part I: Language Model Comparison**
   - Architectures & key hyperparameters (table)
   - Prediction quality: perplexity/cross-entropy table
   - Cost: training time, params, inference throughput, hardware (table)
   - Loss curves (1 figure, all 3 neural models overlaid)
   - Generated text comparison (short table/box, same prompts)
   - Discussion: tradeoffs, observation vs. hypothesis
3. **Part II: Embedding Ablation**
   - 3 settings recap, dimension/coverage/OOV handling
   - Comparison table (quality, convergence, stability)
   - Cost of training own embeddings (separate line item)
   - Interpretation
4. **Part III: Downstream Analysis**
   - Task, dataset, labels, pooling/representation methods compared
   - Classifier setup, frozen vs fine-tuned
   - Metric table + a few representative errors
   - Does LM ranking match downstream ranking?
5. **Limitations & Lessons Learned** (short, explicit)
6. **Appendices/References** — extra tables, full hyperparameter configs, extended generations

Keep prose lean — this is a "results and comparisons" report, not a tutorial on RNNs/Transformers.

---

## 3. Timeline & Milestones

| Week | Dates | Focus | Key Deliverables |
|---|---|---|---|
| **1** | Sep 9 – Sep 15 | **Setup + Part I (core)** | Corpus chosen & justified; preprocessing + shared tokenizer done; n-gram LM built and evaluated; RNN/LSTM/Transformer skeletons training end-to-end (even if not tuned) |
| **2** | Sep 16 – Sep 22 | **Part I (complete)** | All 4 models trained to reasonable convergence; perplexity/cross-entropy, timing, and model-size numbers logged; loss curves saved; generation script run on fixed prompt set |
| **3** | Sep 23 – Sep 29 | **Part I wrap-up + Part II start** | Part I analysis draft written (tradeoffs section); pick 1 architecture for Part II; train your own Skip-gram/CBOW/GloVe embeddings on the corpus; download & align public pretrained embeddings, compute vocab coverage |
| **4** | Sep 30 – Oct 6 | **Part II (complete)** | Train the two additional LM runs (own-frozen, public-frozen); compare against Part I baseline (random-init) on quality/convergence/stability; Part II analysis draft written |
| **5** | Oct 7 – Oct 12 | **Part III** | Pick downstream dataset & task; implement representation extraction (≥2 choices, e.g. LSTM vs Transformer, or pooling methods); train classifiers; get held-out metric + error examples; Part III analysis draft |
| **6** | Oct 13 – Oct 15 | **Integration + Report** | Consolidate all results into report (≤6 pages); write "connect results across parts" discussion; finalize README, configs, seeds for reproducibility; code cleanup |
| — | **Oct 16** | **Buffer + Submit** | Final proofread, check page limit, verify GitHub link/zip works, submit by 11:59pm SGT |

### Suggested self-check gates
- **End of Week 2:** If any Part I model isn't training stably, fix before moving on — Part II depends on a working architecture.
- **End of Week 4:** You should have a complete Part I + Part II results table. If not, cut scope (smaller model/data) rather than delaying Part III.
- **End of Week 5:** Have every number you need for the report. Week 6 is writing/polishing only, not new experiments.

### Time-saving tips given the "computationally reasonable" scope allowed
- Pick a modest corpus (e.g., a few MB of text) and small models — the assignment explicitly rewards fair comparison and interpretation over scale.
- Reuse one training loop/config system across all models to avoid duplicated debugging.
- Log everything (loss curves, timing, configs) from Week 1 onward — reconstructing this later is the most common time sink.
