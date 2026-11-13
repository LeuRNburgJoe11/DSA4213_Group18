# Eight-page report edit

The report has **8 main-text pages**. Contribution Statement starts on page 9; the AI declaration, references and supplementary appendices follow. The detailed material is retained after the main text, not discarded.

## What stayed in the self-contained main report

| Rubric criterion | Evidence retained |
|---|---|
| Idea and contribution | Concrete recipient-impersonation problem; three RQs; scope change from proposal; group's conditions, gate and evaluation contributions |
| Technical quality | Modified Tasks 25/33, models/settings, tool permissions/stopping rules, attacker capabilities, all 22 condition roles, recipient-gate anchors/verdicts and trust assumptions, gate diagram |
| Evaluation and analysis | 330-episode protocol; all four metrics and denominators; complete 15-row five-setting comparison; three-model RQ2 summary; successes/failures and gate effects; single-trial variation, circularity, induced clarification, incomplete manual review, costs |
| Clarity and communication | Eight short sections; two compact tables; one design figure; brief trace evidence; reproduction and safe-use information; APA citations |

The main text does not require reading the appendix to understand the design, core comparisons, results, limitations or conclusions.

## What moved or was consolidated

- Repeated motivation, contribution and literature-review paragraphs were consolidated into Sections 1–2. The prior full source was removed from this report folder.
- Detailed agent descriptions, the original workflow, standard benchmark task inventories, full evidence matrices and expanded gate rules are in Appendix A.
- Per-condition RQ2 result tables and the longer interpretation are in Appendix B. Main Section 5 retains their key findings and aggregate outcomes.
- All five RQ2 and six RQ3 trace walkthroughs, including editable abridged listings, are in Appendix C. Main Section 6 retains the decisive evidence and distinctions between evidence retrieval, unsafe action, clarification, over-blocking and non-completion.
- Full model/provider IDs and reproduction details are in Appendix D; essential versions/settings, run location, costs and responsible practice remain in main Sections 3, 6 and 7.
- The timeline is in Appendix E, and rounded per-setting costs/unaffected-work counts are in Appendix F. Main Sections 5–6 state the corresponding findings and total cost.
- The optional long executive summary was removed because its content duplicated the introduction and results.

## Typography and checks

The 11pt article class, default Computer Modern family, one-inch margins and 1.10 line spacing are preserved. Smaller-font commands were removed from the active source, including supplementary tables and trace listings. Space was saved through content editing, not font/margin reductions or negative vertical spacing. Original diagram labels remain part of the supplied images.

All figure/table/listing counters and bibliography references resolve. The build reports no overfull text boxes, and extracted text stays within the horizontal margins. The rendered pages were visually checked. Build with `latexmk -pdf Group18_Report.tex`, or without Perl: `pdflatex`, `biber Group18_Report`, `pdflatex`, `pdflatex` (see `README.md`).

## Files to edit

- `Group18_Report.tex`: template preamble, title/administration, contributions, bibliography, includes.
- `main.tex`: the eight-page main report.
- `supplement.tex`: supplementary detail.
- `references.bib`: APA bibliography entries.

The older `latest_version/` copy and pre-cut archive were removed from this report folder. The original course template remains unchanged.

## Change log (13 Nov 2026)

- Section 3 wording fixed: "User requests name the recipients without supplying their addresses."
- The Section 4 recipient-gate figure was scaled from full width to 0.62 of the text width. This brought the main text back to 8 pages: the Contribution Statement is on page 9 (it had slipped to page 10), and the PDF is 30 pages. Tables 1-3 are on pages 5, 5 and 6.
- The PDF was rebuilt with pdfLaTeX, Biber, pdfLaTeX twice. No errors, overfull boxes or unresolved references.

## Remaining author decisions

Contribution shares (25% each, 100% total) and the AI-assistance declaration are now filled in; the group should confirm they are accurate. Contribution descriptions still cite section numbers (for example Sections 4, 5.1, 5.2, 6-8 and Appendices A-B), so check them against the current structure.

The standard-task inventory in Appendix A.1 now lists only the pipeline-check tasks (4, 5, 27, 29, 38) plus modified Tasks 25 and 33; Task 26 no longer appears.
