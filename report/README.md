# Group 18 report (DSA4213)

Main source: `Group18_Report.tex` (title, administration, contributions, AI declaration, bibliography, includes)
Main text: `main.tex` (8 compiled pages; the Contribution Statement starts on page 9)
Supplement: `supplement.tex` (Appendices A-F, after the references)
Bibliography: `references.bib` (biblatex, APA style, Biber backend)
Compiled PDF: `Group18_Report.pdf` (30 pages)
Images: `assets/` (original diagrams; the recipient-gate figure in the main text is `page-12-image-01.png`, shown at 0.62 of the text width so the main text fits 8 pages)
Original template: `Group Project Final Report Template.tex` (unchanged)

See `CUT_NOTES.md` for rubric coverage, what moved to the appendix, and the change log.

## Build

Run from this directory. The bibliography needs Biber, so the sequence is pdfLaTeX, Biber, then pdfLaTeX twice:

```sh
pdflatex -interaction=nonstopmode -halt-on-error Group18_Report
biber Group18_Report
pdflatex -interaction=nonstopmode -halt-on-error Group18_Report
pdflatex -interaction=nonstopmode -halt-on-error Group18_Report
```

`latexmk -pdf Group18_Report.tex` does the same where Perl is installed (on Windows/MiKTeX without Perl, run the four commands above). Needed packages are installed on demand by MiKTeX. For Overleaf, upload the sources, `references.bib` and `assets/`, then set `Group18_Report.tex` as the main document (pdfLaTeX, Biber).

## Formatting

11pt article class, default Computer Modern, 1-inch margins and 1.10 line spacing, as in the template. No font-size, margin or negative-spacing reductions. Page fit was achieved by editing content and by scaling the gate figure.

## Current state (13 Nov 2026)

- Main text: 8 pages. Contribution Statement on page 9, then the AI declaration, references and Appendices A-F. PDF: 30 pages.
- Numbering: main-text Tables 1-3 (pages 5, 5, 6) and Figure 1; Contribution table is Table 4; appendix tables 5-16, Figures 2-3, Listings 1-2.
- Contribution shares are complete (25% each, 100% total) and the AI-assistance declaration is filled in.
- The last build had no LaTeX errors, no overfull boxes and no unresolved citations or references.
- Latest edits: Section 3 grammar fix ("name the recipients"); Section 4 gate figure scaled to 0.62 of the text width to keep the main text at 8 pages.

## Which file to edit

| Change | File |
|---|---|
| Title, administration, project summary, contributions, AI declaration, bibliography, includes | `Group18_Report.tex` |
| Main report text (Sections 1-8, Tables 1-3, Figure 1) | `main.tex` |
| Appendices A-F (extra tables, traces, timeline, costs) | `supplement.tex` |
| References | `references.bib` (APA via biblatex) |
| Diagrams | `assets/` |

Do not edit `Group Project Final Report Template.tex`; it is the original course template.

## After every edit

1. Rebuild with the four-command sequence above (Biber is needed whenever citations change).
2. Check the page count: the Contribution Statement must still start on page 9.
3. Search `Group18_Report.log` for `Overfull`, `undefined` and `Rerun`; there should be none.
4. Check table, figure and listing order in the PDF.
5. Commit the sources and the rebuilt `Group18_Report.pdf` together. Auxiliary files (`.aux`, `.bbl`, `.log`, and so on) are git-ignored.

## Captions and cross-references

Use the shared caption command; never type a caption number:

```tex
eportcaption{table}{tab:unique-name}{Caption text.}
eportcaption{figure}{fig:unique-name}{Caption text.}
eportcaption{listing}{lst:unique-name}{Caption text.}
```

Refer to them with `Table~ef{tab:unique-name}`, `Figure~ef{fig:unique-name}` or `Listing~ef{lst:unique-name}`. Labels must be unique. Tables, figures and listings have separate counters, and the command handles bold labels, alignment and spacing. Put captions before tables and after figures, as in the existing document. Longtable's own counter increment is disabled because the caption command owns numbering. In prose, use `\code{...}` for identifiers and `llowbreak` after underscores in long names so they wrap.
