# PDF export

Build a paginated PDF from the same chapter order, Markdown preparation, links, citations and Mermaid images used for EPUB:

```sh
mdbindery build ./my-book --format pdf
```

EPUB remains the default. PDF output is `<output_dir>/<slug>.pdf`. Reports use `reports/pdf/build.json` and `reports/pdf/build.log`; EPUB reports stay in `reports/`. Building either format preserves the other book file and its reports. The generated cover image is shared. PDF export leaves source configuration unchanged; EPUB identifier generation applies only to EPUB.

## Install PDF dependencies

PDF uses the existing Node.js, Puppeteer and headless Chrome installed by `mdbindery install-tools`. The `pdf` Python extra adds pypdf for output validation. With version 0.2.0 or newer, inside your Python environment:

```sh
python -m pip install 'mdbindery[pdf]>=0.2.0'
mdbindery install-tools
mdbindery build ./my-book --format pdf
```

For a source checkout, use `python -m pip install '.[pdf]'` at the repository root instead. For an isolated CLI installation, use `uv tool install 'mdbindery[pdf]'` or `pipx install 'mdbindery[pdf]'`. An EPUB-only installation can keep `--no-node` and omit the PDF extra. PDF export reports missing dependencies before preparing chapters.

## Page settings

Set these under the existing `options` mapping:

```yaml
options:
  pdf:
    page_size: A4
    margin_mm: 20
    page_numbers: true
```

`page_size` accepts `A4` or `Letter`. Uniform margins accept finite values from 10 to 40 mm. Page numbers count every page, including cover and title. Defaults shown above. `options.toc` and `toc_depth` apply to both formats; `split_level` controls EPUB only.

PDF uses shared book CSS plus print overrides for page breaks, tables, code wrapping and image height. `options.css` and `extra_css` still apply, subject to those overrides. Fonts referenced by CSS must be listed in `options.embed_fonts`; use the same path in `url(...)` and that list. Font files and resolved chapter images are copied into temporary work storage. Other CSS resources and imports outside that explicit file set fail export. No remote assets download during PDF rendering.

## Checks and failures

Both formats run existing source checks for links, images, charts and includes. PDF additionally checks loaded images/fonts and internal HTML links, parses the generated PDF, and compares its extracted text with generated HTML text. Text comparison uses existing `wordcount_tolerance` and `wordcount_min_words`; it tolerates page numbers and repeated table headings. EPUBCheck, Ace and the EPUB-specific per-chapter word-count gate do not run for PDF.

Exit codes remain: `0` for passing checks, `1` for a failed gate, `2` for an input/build error. A readable PDF with a failed text gate remains available for inspection and is marked failed. Renderer errors preserve an older PDF and remove the partial replacement. PDF reports identify failed stages and record Chromium/Puppeteer versions.

Document scripts are disabled. Browser requests allow only staged assets and data URLs. Rendering uses a process deadline and process-tree cleanup. PDF never automatically retries without the browser sandbox. On a trusted CI/container host that cannot launch Chromium's sandbox, explicitly set `MDBINDERY_NO_SANDBOX=1`; export prints a warning. A remembered Mermaid sandbox fallback alone does not disable the PDF sandbox.

## Limits

Inspect the PDF before sharing. Text extraction cannot prove correct pagination, glyph appearance, reading order or absence of clipping. Math and unusual scripts can need manual inspection. Notes appear as endnotes. Table of contents links are clickable; printed destination page numbers are not generated.

PDF bytes can differ across builds due to browser metadata, fonts and renderer versions. EPUB reproducibility behavior is unchanged. PDF/A, PDF/UA, printer acceptance and full accessibility conformance are not claimed. Advanced print production and alternative PDF engines are outside this export option.
