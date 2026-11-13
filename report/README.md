# Current condensed report

The main text is in `main.tex` (8 compiled pages), with detailed evidence in `supplement.tex`. `Group18_Report.tex` is the main file to compile. See `CUT_NOTES.md` for the rubric coverage, relocation map and remaining author decisions. The original course typography is preserved. Contribution Statement begins on page 9; references and appendix are excluded from the main-text limit.

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

For Overleaf, upload the report sources, bibliography and `assets/` directory, then set `Group18_Report.tex` as the main document using pdfLaTeX.

## Formatting and conversion scope

The source retains the template's 11pt article class, default Computer Modern font family, 1-inch margins, 1.10 line spacing, and original hyperlink settings. No font-size or margin reductions were used. Added packages support images, editable multipage tables, accented text, and keeping captions with their content.

Text and the PDF's native tables have been converted to editable LaTeX. The workflow diagrams, two graphical results tables, and two graphical trace listings remain original images. Tables split across pages in the input have been reassembled. The title and administrative layout follow the supplied template. Contribution Statement, References, and Appendix are placed after the main text in template order.

## Draft items preserved for the authors (written at the original conversion; several are resolved)

This is a conversion, not a shortened or fact-checked rewrite. It preserves the supplied draft's wording, unfinished material, and section/caption labels.

- (Original conversion note, now out of date: the first compiled version was 22 pages with 19 pages of main text. The current main text is 8 pages, within the template's 8-page limit, with the Contribution Statement on page 9.)
- Project Summary remains an instruction/placeholder. Several final sections contain headings only.
- Source headings are not sequential (including 3.2a/3.2b and 7.1/7.2). Internal prose section references need checking after the final structure is agreed.
- Tables, figures, and trace listings use automatic numbering with unique labels. Prose table references use `\ref` and update after recompiling twice.
- The aggregate table contains counts only in the supplied PDF although its caption mentions percentages. No values were invented or added.
- Reference [4] is mentioned in the main text but absent from the final references. The source also contains an editorial note about optionally adding it. These need author review.
- Contribution shares and one member's contributions are incomplete; no missing shares were invented. The AI attribution sentence is also incomplete.
- No research claims, model names, or experimental results were independently revised as part of the conversion.

## Verification

The PDF was compiled twice with pdfLaTeX and all pages were visually reviewed. The final compilation has no overfull/underfull box warnings; extracted text lies within the 1-inch horizontal margins. The original source PDF and template were left unchanged.

## Adding captions and references

Use the shared caption command; never type a caption number:

```tex
\reportcaption{table}{tab:unique-name}{Caption text.}
\reportcaption{figure}{fig:unique-name}{Caption text.}
\reportcaption{listing}{lst:unique-name}{Caption text.}
```

Refer to them with `Table~\ref{tab:unique-name}`, `Figure~\ref{fig:unique-name}`, or `Listing~\ref{lst:unique-name}`. Each label must be unique. The three types have separate serial counters. The shared command handles bold labels, flush-left alignment, and caption spacing. Place captions before data tables and after figures, consistently with the existing document. Longtable counter increments are disabled because the caption command owns numbering. Administrative information is an unnumbered layout table.
