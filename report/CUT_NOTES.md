# Eight-page report edit

The report on `cut_report` has **7 main-text pages**. Contribution Statement starts on page 8; references and supplementary appendices follow. The complete PDF is 28 pages because the detailed material is retained after the main text, not discarded.

## What stayed in the self-contained main report

| Rubric criterion | Evidence retained |
|---|---|
| Idea and contribution | Concrete recipient-impersonation problem; three RQs; scope change from proposal; group's conditions, gate and evaluation contributions |
| Technical quality | Modified Tasks 25/33, models/settings, tool permissions/stopping rules, attacker capabilities, all 22 condition roles, recipient-gate anchors/verdicts and trust assumptions, gate diagram |
| Evaluation and analysis | 330-episode protocol; all four metrics and denominators; complete 15-row five-setting comparison; three-model RQ2 summary; successes/failures and gate effects; single-trial variation, circularity, induced clarification, incomplete manual review, costs |
| Clarity and communication | Eight short sections; two compact tables; one design figure; brief trace evidence; reproduction and safe-use information; APA citations |

The main text does not require reading the appendix to understand the design, core comparisons, results, limitations or conclusions.

## What moved or was consolidated

- Repeated motivation, contribution and literature-review paragraphs were consolidated into Sections 1–2. The prior full source remains in `archive/Group18_Report_before_cuts.tex`.
- Detailed agent descriptions, the original workflow, standard benchmark task inventories, full evidence matrices and expanded gate rules are in Appendix A.
- Per-condition RQ2 result tables and the longer interpretation are in Appendix B. Main Section 5 retains their key findings and aggregate outcomes.
- All five RQ2 and six RQ3 trace walkthroughs, including editable abridged listings, are in Appendix C. Main Section 6 retains the decisive evidence and distinctions between evidence retrieval, unsafe action, clarification, over-blocking and non-completion.
- Full model/provider IDs and reproduction details are in Appendix D; essential versions/settings, run location, costs and responsible practice remain in main Sections 3, 6 and 7.
- The timeline is in Appendix E, and rounded per-setting costs/unaffected-work counts are in Appendix F. Main Sections 5–6 state the corresponding findings and total cost.
- The optional long executive summary was removed because its content duplicated the introduction and results.

## Typography and checks

The 11pt article class, default Computer Modern family, one-inch margins and 1.10 line spacing are preserved. Smaller-font commands were removed from the active source, including supplementary tables and trace listings. Space was saved through content editing, not font/margin reductions or negative vertical spacing. Original diagram labels remain part of the supplied images.

All figure/table/listing counters and bibliography references resolve. The build reports no overfull text boxes, and extracted text stays within the horizontal margins. The rendered pages were visually checked. Build with `latexmk -pdf Group18_Report.tex`.

## Files to edit

- `Group18_Report.tex`: template preamble, title/administration, contributions, bibliography, includes.
- `sections/main.tex`: the seven-page main report.
- `appendix/supplement.tex`: supplementary detail.
- `references.bib`: APA bibliography entries.

`latest_version/` and the original course template have not been edited. The pre-cut source is also retained in `archive/Group18_Report_before_cuts.tex`. No commit or push was made for this edit.

## Remaining author decisions

Contribution shares are still incomplete (one is a range); they must be agreed by the group and sum to 100%. Existing contribution descriptions cite some old section numbers and should be reviewed against the new structure. The prior incomplete AI-attribution placeholder is preserved in the archived source, not presented as a finished declaration. The group should add an accurate attribution if required. These were not invented during condensation.

Supplementary material intentionally preserves earlier wording for audit. In particular, the standard-task inventory includes Task 26 although the reported pipeline-check subset is 4, 5, 27, 29 and 38. Main results do not rely on Task 26. Review before a final submission if retaining the full inventory.
