# Group 18 report: LaTeX conversion

Main source: `Group18_Report.tex`
Compiled preview: `Group18_Report.pdf`
Images: `assets/` (six original embedded images extracted from the supplied PDF)
Original template: `Group Project Final Report Template.tex` (unchanged)

## Build

Run from this directory:

```sh
pdflatex -interaction=nonstopmode -halt-on-error Group18_Report.tex
pdflatex -interaction=nonstopmode -halt-on-error Group18_Report.tex
```

Alternatively upload `Group18_Report_LaTeX.zip` to Overleaf and set `Group18_Report.tex` as the main document, using pdfLaTeX.

## Formatting and conversion scope

The source retains the template's 11pt article class, default Computer Modern font family, 1-inch margins, 1.10 line spacing, and original hyperlink settings. No font-size or margin reductions were used. Added packages support images, editable multipage tables, accented text, and keeping captions with their content.

Text and the PDF's native tables have been converted to editable LaTeX. The workflow diagrams, two graphical results tables, and two graphical trace listings remain original images. Tables split across pages in the input have been reassembled. The title and administrative layout follow the supplied template. Contribution Statement, References, and Appendix are placed after the main text in template order.

## Draft items preserved for the authors

This is a conversion, not a shortened or fact-checked rewrite. It preserves the supplied draft's wording, unfinished material, and section/caption labels.

- The compiled document is 22 pages: 19 pages of main text, followed by contributions, references, and appendix. The template permits only 8 main-text pages. Substantial editing is still needed; changing font/margins is not a solution.
- Project Summary remains an instruction/placeholder. Several final sections contain headings only.
- Source headings are not sequential (including 3.2a/3.2b and 7.1/7.2). Internal prose section references need checking after the final structure is agreed.
- Table X/Y/Z, Figure X, and Listing X/Y are retained source placeholders; X/Y/Z table labels are reused. Replace with unique numbering and LaTeX labels/references before submission.
- The aggregate table contains counts only in the supplied PDF although its caption mentions percentages. No values were invented or added.
- Reference [4] is mentioned in the main text but absent from the final references. The source also contains an editorial note about optionally adding it. These need author review.
- Contribution shares and one member's contributions are incomplete; no missing shares were invented. The AI attribution sentence is also incomplete.
- No research claims, model names, or experimental results were independently revised as part of the conversion.

## Verification

The PDF was compiled twice with pdfLaTeX and all pages were visually reviewed. The final compilation has no overfull/underfull box warnings; extracted text lies within the 1-inch horizontal margins. The original source PDF and template were left unchanged.
