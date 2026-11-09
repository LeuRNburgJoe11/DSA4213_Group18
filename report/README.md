# Group 18 report: LaTeX conversion

Main source: `Group18_Report.tex`
Compiled preview: `Group18_Report.pdf`
Images: `assets/` (six original embedded images extracted from the supplied PDF)
Original template: `Group Project Final Report Template.tex` (unchanged)

## Build

Run from this directory:

```sh
latexmk -pdf Group18_Report.tex
```

Alternatively upload `Group18_Report_LaTeX.zip` to Overleaf and set `Group18_Report.tex` as the main document, using pdfLaTeX or XeLaTeX. Overleaf should detect Biber automatically.

## Formatting and conversion scope

The source retains the template's 11pt article class, default Computer Modern font family, 1-inch margins, 1.10 line spacing, and original hyperlink settings. No font-size or margin reductions were used. Added packages support images, editable multipage tables, accented text, and keeping captions with their content.

Text and the PDF's native tables have been converted to editable LaTeX. The workflow diagrams, two graphical results tables, and two graphical trace listings remain original images. Tables split across pages in the input have been reassembled. The title and administrative layout follow the supplied template. Contribution Statement, References, and Appendix are placed after the main text in template order.

## Draft items preserved for the authors

This is a conversion, not a shortened or fact-checked rewrite. It preserves the supplied draft's wording, unfinished material, and section/caption labels.

- The draft currently exceeds the eight-page main-text limit; page counts change as content is edited. The template permits only 8 main-text pages. Substantial editing is still needed; changing font/margins is not a solution.
- Project Summary remains an instruction/placeholder. Sections 6–8 have since been populated with author-supplied text.
- Source headings are not sequential (including 3.2a/3.2b and 7.1/7.2). Internal prose section references need checking after the final structure is agreed.
- Tables, figures, and trace listings use automatic numbering with unique labels. Prose table references use `\ref` and update after recompiling twice.
- The aggregate table contains counts only in the supplied PDF although its caption mentions percentages. No values were invented or added.
- The missing Greshake et al. (2023) entry was restored from the proposal citation and verified against arXiv. The obsolete numeric-citation editorial note was removed. Citations now use APA author–date commands.
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

## APA 7 references and citations

`references.bib` is the bibliography database. `biblatex` with `style=apa` and the Biber backend generates the reference list and author–date citations automatically. Formatting includes author initials, author-list rules, alphabetisation, italics, and hanging indents. The report retains the course template's font, margins, and 1.10 spacing; APA document-wide double spacing is not imposed over the required template.

Add a new entry to `references.bib` using a unique key, for example:

```bibtex
@article{smith2026example,
  author       = {Smith, Jane and Tan, Wei},
  date         = {2026},
  title        = {An example title in sentence case with {LLM} protected},
  journaltitle = {Journal Name},
  volume       = {12},
  number       = {3},
  pages        = {10--25},
  doi          = {10.xxxx/example}
}
```

This example is a placeholder, not a real reference. Supply verified metadata, sentence-case titles, and braces around proper nouns/acronyms. Store DOI values without a URL prefix. Use the correct entry type (`article`, `inproceedings`, `book`, `online`, etc.). For sources without a DOI, supply the appropriate URL instead. Never hand-type the formatted bibliography.

In the report, use `\textcite{smith2026example}` for a narrative citation and `\parencite{smith2026example}` for a parenthetical citation. Combine sources with `\parencite{key1,key2}`; add a quotation page with `\parencite[p. 12]{key1}`. Only cited sources appear in the reference list by default. If a source is intentionally included without an in-text citation, use `\nocite{key}` explicitly.

Build with `latexmk -pdf Group18_Report.tex`, or manually:

```sh
pdflatex Group18_Report.tex
biber Group18_Report
pdflatex Group18_Report.tex
pdflatex Group18_Report.tex
```

For XeLaTeX substitute `xelatex` for `pdflatex`, or use `latexmk -xelatex Group18_Report.tex`. A single LaTeX pass cannot resolve a new bibliography; running Biber is required. If switching bibliography backends from an older cached build, use Overleaf's Recompile from scratch.
