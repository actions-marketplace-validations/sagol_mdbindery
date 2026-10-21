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

## Navigation, metadata and the title page

With `options.toc` true (the default), the PDF has a bookmark outline that matches the printed contents: the same entries, `toc_depth` deep, nested as the contents nests them, each opening the page its heading is printed on. Each bookmark title is the entry's text as the printed contents show it, on one line (each run of spaces and line breaks becomes one space, whatever `white-space` keeps on the page), in the case `text-transform` gives it: words that print-only CSS hides there are left out, and an image counts as its alt text. Text that print CSS adds there with `::before` or `::after` counts too when it is a string or `attr()`; a counter or a quote mark generated there stops the build, since the bookmark cannot repeat it, and so does generated text that is positioned, transformed, or moved out of view by a margin, padding or `text-indent` (Chrome still writes such text, away from the entry; any transform, even one that changes nothing, does the same), or that clips its own overflow in a box with a size, or that sits inside an element whose content runs past its clip edge, since how much of it shows cannot be measured (in a box of no width or height it counts as hidden). Text drawn invisibly counts as hidden: zero opacity on the entry or above it, or a transparent text colour; so does an image under a clip path, a mask or an SVG filter, whose drawing cannot be checked, or under a filter that clears it (`opacity(0)`); other filters, such as `grayscale()`, still print it. An image turned, mirrored or skewed by a transform (a half turn or a negative scale included) counts as drawn only when it fills its box or its whole box prints, since where its pixels land inside the box cannot be read. Text kept out of the PDF in other ways (zero size, clipping or a mask, placing it off the page) stops the build too, and so does a contents entry whose text is only partly visible, with letters or lines cut off by an element that hides its overflow (a fixed width, or `text-overflow`) or by the page edge, since what of it prints cannot be told from the page text. After that, the `outline` gate reads the printed contents pages as the sequence of entries, each with its own list marker (none where CSS hides the marker or gives it no size; a clear-coloured marker is still in the page text; an item CSS shows as a block, not a list item, has no marker and the numbering skips it); with markers it cannot spell out (custom counters, an image marker, or a style other than decimal, alphabetic, Roman or a bullet) it reports the contents text as not checked. Text drawn only as an outline (a clear fill with a stroke or a shadow) is read where it prints, written twice as Chrome writes it; if it lands elsewhere in the page text, that entry's filled words are still found in order before the next entry, and the entry is noted as not fully checked. With `options.toc` false there is neither a printed contents page nor an outline. A heading listed in the contents must be printed: one hidden by CSS (`display: none`, or `visibility: hidden` with no part of it made visible again, on it or a parent), or one whose content draws nothing (an image-only heading whose image CSS hides; text the heading generates with `::before` or `::after` counts as drawn), stops the build with its title; so does a `display: contents` heading, which has no box for a bookmark to open at (Markdown gives nothing inside it an id to use instead), and so does a contents entry with nothing visible; show it, or keep it out of the contents with a lower `toc_depth`.

The contents page is headed by `options.toc_title`, else the built-in title for the book's language («Содержание», Contents), as in the EPUB; a language without a built-in title and no `toc_title` gets no heading. The title page carries `metadata.rights`, when set, below the title, author and date.

The document information comes from the configuration: Title from `title` (without the subtitle), Author from `authors` joined with `; `, Subject from `description`, Keywords from `subjects`. An XMP metadata stream holds the same, with `dc:rights`, `dc:publisher` and `dc:language` when set. Empty fields are left out. The language stays in the catalog's `Lang`, from `metadata.lang`.

PDF uses shared book CSS plus print overrides for page breaks, tables, code wrapping and image height. `options.css` and `extra_css` still apply, subject to those overrides. Fonts referenced by CSS must be listed in `options.embed_fonts`; use the same path in `url(...)` and that list. Font files and resolved chapter images are copied into temporary work storage. Other CSS resources and imports outside that explicit file set fail export. No remote assets download during PDF rendering.

## Checks and failures

Both formats run existing source checks for links, images, charts and includes. PDF additionally checks loaded images/fonts and internal HTML links, parses the generated PDF, and compares its extracted text with generated HTML text. The final file is then reopened for three more checks, reported as parts of the `pdf` gate in `build.json`: `outline` (the bookmarks equal the contents, each title on its destination page, and each entry's words in the contents pages' own text, in order), `front_matter` (the title and the rights line on the title page, with every word the title block draws on that same page, the contents heading on the contents page, each drawn by its own element and none partly cut off by an element that hides its overflow or by the page edge; a part that does not apply is recorded as such) and `metadata` (Info, XMP and `Lang` equal the configuration). The checks find the title page, the contents and the rights line by destinations that hidden links in the document head point to, which the book never shows; the PDF is printed a second time without those links, and if the book's CSS makes the two prints differ (a selector such as `:has()` on `html` or `head` that sees them), the build stops. Any failed part fails the gate. Text comparison uses existing `wordcount_tolerance` and `wordcount_min_words`, and expects of the contents only the words each entry prints there; it tolerates page numbers and repeated table headings. EPUBCheck, Ace and the EPUB-specific per-chapter word-count gate do not run for PDF.

Exit codes remain: `0` for passing checks, `1` for a failed gate, `2` for an input/build error. A readable PDF with a failed gate remains available for inspection and is marked failed. Renderer errors preserve an older PDF and remove the partial replacement. PDF reports identify failed stages and record Chromium/Puppeteer versions.

Document scripts are disabled. Browser requests allow only staged assets and data URLs. Rendering uses a process deadline and process-tree cleanup. PDF never automatically retries without the browser sandbox. On a trusted CI/container host that cannot launch Chromium's sandbox, explicitly set `MDBINDERY_NO_SANDBOX=1`; export prints a warning. A remembered Mermaid sandbox fallback alone does not disable the PDF sandbox.

## Limits

Inspect the PDF before sharing. Text extraction cannot prove correct pagination, glyph appearance, reading order or absence of clipping. Math and unusual scripts can need manual inspection. Notes appear as endnotes. Table of contents links and bookmarks are clickable; printed destination page numbers are not generated. The title page must fit on one page for its check to pass.

PDF bytes can differ across builds due to browser metadata, fonts and renderer versions. EPUB reproducibility behavior is unchanged. PDF/A, PDF/UA, printer acceptance and full accessibility conformance are not claimed. Advanced print production and alternative PDF engines are outside this export option.
