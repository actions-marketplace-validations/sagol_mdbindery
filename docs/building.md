# Building

`mdbindery build` turns the book into an EPUB 3 file, validates it, and writes reports next to it. The rules the Markdown must follow are in [book-structure.md](book-structure.md), every configuration key is in [configuration.md](configuration.md), and the dry run that finds problems before a build is in [checking.md](checking.md).

For PDF, use `mdbindery build ./my-book --format pdf`. [PDF export](pdf.md) explains its dependencies, page settings and separate checks. This page describes the default EPUB build.

## Usage

```
mdbindery build [path] [-c CONFIG] [-o OUT] [--format epub|pdf] [--no-ace] [--keep-work] [-q]
```

| Argument | Meaning |
|---|---|
| `path` | Book folder, or a configuration file. Default: the folder of the `--config` file when one is given, otherwise the current folder |
| `-c CONFIG`, `--config CONFIG` | Configuration file to use instead of the one found in the book folder |
| `-o OUT`, `--out OUT` | Output folder. Default: `output_dir` from the configuration (`dist`), relative to the configuration file's folder, or to the book folder when there is no configuration file |
| `--format` | Select output; `epub` is the default. PDF dependencies, reports and checks are described in [PDF export](pdf.md) |
| `--no-ace` | Skip the Ace accessibility check. The gate is recorded as `skipped` and the log has no Ace line. `options.ace: false` in the configuration does the same |
| `--keep-work` | Keep the temporary work folder with every intermediate file. The log ends with `work folder kept: <path>` (with `-q`, that line is only in `reports/build.log`) |
| `-q`, `--quiet` | Print only the last line (`BUILD OK` or `BUILD FAILED: ...`). The full log still goes to `reports/build.log`. Errors that stop the build still go to stderr |

The configuration is found in this order: `--config`; `path` itself when it is a file; `mdbindery.yaml`, then `mdbindery.yml`, in `path` (or the current folder). The book folder is `source_dir` from the configuration when set (relative to the configuration file), otherwise `path` when it is a folder, otherwise the configuration file's folder.

An mdBook book is recognized automatically. When the book folder holds `book.toml` and the source folder it names (`src` in `book.toml`, `src/` by default) holds `SUMMARY.md`, that source folder becomes the book folder, the reading order comes from `SUMMARY.md`, and the title, authors, description, and language come from `book.toml` unless the configuration sets them. This also works when `source_dir` points at the folder with `book.toml`, and a book folder that holds `SUMMARY.md` with `book.toml` one level up works the same way. A `files:` list in the configuration overrides `SUMMARY.md`. A `SUMMARY.md` without any `book.toml` only sets the reading order. See [configuration.md](configuration.md#mdbook-books).

Without a configuration file, mdbindery infers everything from the folder (see [configuration.md](configuration.md#what-is-inferred-when-keys-are-missing)), but then each EPUB build gets a new identifier. PDF export does not generate or save one.

Examples:

```
mdbindery build                                   # the book in the current folder
mdbindery build path/to/book                      # another folder
mdbindery build books/my-book/mdbindery.yaml      # a configuration file (it may set source_dir)
mdbindery build -c ebook/mdbindery.yaml           # the same with --config
mdbindery build -o /tmp/epub --no-ace -q          # other output folder, no Ace, one line of output
```

`mdbindery build` works on a folder on disk. To build a GitHub repository, clone it first; `mdbindery check <URL>` can look at a repository without cloning it.

Exit status:

| Status | Meaning |
|---|---|
| 0 | The EPUB was built and no gate failed (gates reported as `warn` or `skipped` do not count) |
| 1 | The EPUB was built, but at least one gate failed |
| 2 | A configuration error (`config error: ...`) or a build error that stopped the build before the EPUB was written (`build error: ...`), for example pandoc not installed, a listed file or the cover image not found, a chapter that is not UTF-8, or `-o` naming a file (`build error: output folder is a file: <path>`) |
| 3 | An internal error (`internal error: ...`): a bug in mdbindery. See [troubleshooting.md](troubleshooting.md#internal-errors) |
| 130 | Interrupted with Ctrl+C |

A build of the sample book in `examples/sample-book` prints one line per file and one per gate:

```
mdbindery: writing-a-book-in-markdown (5 files) from .../sample-book
  k00 README.md: dropped ['Contributing']
  k01 01-why-markdown.md: 2 refs, 2 image(s)
  k02 02-structure.md: 1 chart(s), 2 image(s)
  k03 03-publishing.md: 1 refs
  k04 appendix-a-checklist.md: tables as cards
  built .../sample-book/dist/writing-a-book-in-markdown.epub (108 KB)
  EPUBCheck: no messages
  Ace: 0 violation(s), 0 blocking
  word count: every file within 2% or 25 words of its source
BUILD OK
```

`k00`, `k01`, ... are the file keys: the position of each file in the reading order. They prefix every anchor in the EPUB (see [design.md](design.md#identifier-prefixing)).

A build with problems keeps going, so one run shows all of them. This is `tests/fixtures/broken-book` with `files:` cut to its first two chapters (the third is not UTF-8, which stops a build, and the fourth does not exist) and an empty `identifier:` line added:

```
mdbindery: broken-book (2 files) from .../broken-book
  config warning: unknown config key: options.toc_dept (did you mean "toc_depth"?)
  generated identifier urn:uuid:33df157a-2798-40dd-96ef-a8ffc1f6bc65 (saved in mdbindery.yaml)
  k00 01-intro.md: 2 refs, uncited ['4', '5'], 4 image(s), HTML removed: <iframe>x1, <script>x1, first heading promoted to level 1
  k01 02-body.md: 1 chart(s), wide tables [10] cols
  CHART in 02-body.md failed to render (placeholder used): Error: Parse error on line 2: ...t LR  A[Start --> B[ ----------------------^
  UNRESOLVED link in 01-intro.md to 02-body.md#no-such-anchor (text: the body)
  LINK to a missing file in 01-intro.md: ghost.md
  IMAGE remote: https://example.org/logo.png in 01-intro.md
  IMAGE missing: images/missing.png in 01-intro.md
  built .../broken-book/dist/broken-book.epub (19 KB)
  EPUBCheck: {'ERROR': 1}
    ERROR RSC-032: Fallback must be provided for foreign resources, but found none for resource "EPUB/media/file1.bmp" of type "image/x-ms-bmp". [EPUB/text/ch001.xhtml:21]
  Ace: 1 violation(s), 0 blocking
    moderate heading-order x1
  word count: every file within 2% or 25 words of its source
BUILD FAILED: charts, links, images, epubcheck (details: .../broken-book/dist/reports/build.json)
```

## The pipeline

1. Load the configuration. mdbindery reads the configuration file, checks every value, merges it with the defaults, and fills in what it can infer (reading order, title, language, rights, cover). An unknown top-level key or a wrong value stops the build with `config error:`; an unknown nested key is logged as `config warning:` and ignored.
2. Check the basics before writing anything. The build stops if pandoc 3.8 or newer is not found, or if the reading order is empty (`no Markdown files in the reading order (MB100)`). Then the output folder is created and mdbindery's own files in `reports/` are removed (see [Outputs](#outputs)).
3. Take the build timestamp, as described under [Reproducible builds](#reproducible-builds).
4. Prepare each file (the Python pre-pass):
   - The file is read as UTF-8. A file that is not valid UTF-8 stops the build: `build error: 03-latin.md is not valid UTF-8 (byte 17); re-save it as UTF-8`.
   - Line endings and a byte order mark are normalized.
   - mdBook directives are expanded: `{{#include path}}` with the `:N`, `:N:M`, `:N:`, `::M`, and `:anchor` selections, `{{#rustdoc_include ...}}` (treated as an include), and `{{#playground path}}`. `{{#title ...}}` is removed, and `\{{#include ...}}` stays as literal text. Paths are relative to the Markdown file and must stay inside the repository. A directive that cannot be expanded stays in the text and fails the `includes` gate.
   - Sections listed in `drop_sections` and lines matching `drop_lines` are removed.
   - Reference definitions for citation labels are collected: numeric labels (`[1]: url "Title"`) by default, every label with `options.citation_labels: all`, none with `options.citations: none`. A label used by an image (`![alt][label]`), or a named label whose definition points to an image file, is never a citation. The definition lines stay in the text, so ordinary reference links (`[text][label]`) and images keep working.
   - Mermaid blocks are rendered to PNG with mermaid-cli, or replaced by a placeholder (see [charts](#charts)).
   - In mdBook books (those with a `book.toml`), lines starting with `# ` in Rust code blocks are hidden and `##` becomes `#`, as mdBook does.
   - The visible reference list is inserted under the last heading named in `reference_headings` (after the underline of a setext heading), or under a new `## References` heading (`reference_heading_new`) at the end of the file.

   Code blocks, inline code, and HTML comments are never changed. The list is built here because pandoc's Markdown reader turns reference definitions into invisible link targets.
5. Convert each file. Each prepared file goes through `pandoc -f gfm -t json` with the Lua filter `book.lua` in its `file` phase. The filter:
   - converts raw HTML at any depth (quotes, list items, divs): `<a id>` anchors become anchors, a `<div class="name">` on its own line becomes a styled block, other HTML blocks are read by pandoc's HTML reader, and inline tags such as `<br>`, `<sup>`, `<b>`, `<kbd>`, `<small>`, `<mark>`, `<img>`, and `<a href>` become the matching document elements. Tags with no equivalent are dropped, and the file's log line lists them (`HTML removed: <iframe>x1`). Their text is usually kept; the word-count gate catches the cases where it is not. Comments are dropped;
   - resolves image paths and makes figures, full-page images, and inline images (see [images](#images)); an `<img>` inside an HTML `<figure>` becomes a figure with the `<figcaption>` as its caption;
   - turns each reference link whose text is a citation label and whose URL is that label's definition into a `[1]` link (class `citation`) to the reference list;
   - makes sure the file starts with exactly one level-1 heading, or pandoc would merge it into the previous chapter. A file without one gets its `title:` from the configuration as the heading; without a `title:`, the file's first heading is promoted to level 1 when nothing visible comes before it (the file's other headings move up by the same number of levels, but never above level 2); otherwise a title is made from the file name (`04-power-budget.md` becomes "Power budget", and a `README.md` gets the book title). Content above the level-1 heading (badges, logos) is moved below it. A `title:` for a file that has a heading replaces the heading's text and keeps its anchor (and any `<a id>` anchors inside it), so existing links still work. `<a id>` anchors written inside a heading move to just below it;
   - turns wide tables into cards for files listed under `options.cards.files`;
   - prefixes every identifier with the file key;
   - rewrites links (see [links](#links)): a link to another book file becomes an internal link, `chapter.html` counts as `chapter.md` (and `folder/index.html` as `folder/README.md`) when that file is in the book, a link to a file outside the book points to `source_url` or becomes plain text, and characters that are not allowed in URLs are percent-encoded.

   The filter writes a JSON report per file, and the build logs one line per file with what it did: expanded includes, references, charts, images, dropped sections, removed HTML, title fixes (`title from config`, `first heading promoted to level 1`, `title made from the file name`), moved blocks, and links kept as text.
6. Merge the files and resolve links. The per-file documents are concatenated into one, and the filter runs again in its `links` phase. Every internal link is matched against the identifiers of the whole book.
7. Settle the identifier and the date. If `metadata.identifier` is empty, a `urn:uuid` is generated and written into the empty `identifier:` line of the configuration file (`generated identifier urn:uuid:... (saved in mdbindery.yaml)`), so every later build reuses it. If the file has no `identifier:` line, or there is no configuration file, the identifier is used for this build only and the log says `warning: generated identifier ... for this build only`. With `date: git` (the default), the publication date is the UTC date of the build timestamp.
8. Decide the source gates: `charts`, `links`, `images`, and, when a directive failed, `includes` (see [Gates](#gates)).
9. Make the covers and the stylesheet. The store cover and the embedded cover are produced (see [Covers](#covers)). The stylesheet is the default `epub.css`, or `options.css`, with `options.extra_css` appended.
10. Write the EPUB. The book metadata (title, subtitle, authors, description, rights, publisher, subjects, series) goes into the document as literal text, so `*`, `_`, `@`, or `<div>` in a title stays as typed. `pandoc -f json -t epub3` then writes the book into the work folder with the stylesheet, the embedded cover, `--split-level` and `--toc-depth` from the options, a table of contents (`options.toc`), syntax highlighting (`options.highlight_style`, `monochrome` by default), and any `options.embed_fonts`. mdbindery sets `SOURCE_DATE_EPOCH` for this step. pandoc warnings appear in the log as `pandoc: ...` and are stored in `build.json` under `pandoc_warnings`.
11. Post-process the package. mdbindery adds schema.org accessibility metadata to the package document: `accessMode` `textual` (and `visual` when the book has images, rendered charts included), `accessModeSufficient` `textual`, the features `tableOfContents`, `readingOrder`, `structuralNavigation`, and `alternativeText` (only when every image has alt text), `accessibilityHazard` `none`, the accessibility summary, and `dcterms:conformsTo` when `options.conformance_claim` is set. Each endnote gets its number, linked back to the reference in the text. The ZIP container is rewritten in a fixed form (see [Reproducible builds](#reproducible-builds)) into `<slug>.epub.part` in the output folder and renamed to `<slug>.epub` only when it is complete, so an interrupted build never leaves a half-written file under the final name.
12. Run the validation gates. EPUBCheck, Ace, and the word-count check run on the finished file.
13. Write the reports. `reports/build.json` is written, and the command writes the log to `reports/build.log`. A build that stops with an error writes both too (see [Outputs](#outputs)).

Every external program runs with a time limit and is stopped with all its child processes when the limit passes or you press Ctrl+C: 3 minutes per Mermaid chart, 5 minutes per file for the word count, 20 minutes for EPUBCheck, 30 minutes for Ace and for writing the EPUB, 15 minutes for other pandoc runs. On a slow machine or a very large book, `MDBINDERY_TIMEOUT_SCALE=3` triples every limit.

The EPUB is written even when a gate fails, so you can open it and look at the problem. Do not publish a file from a failed build.

With `--keep-work`, the work folder (in the system temporary folder, named `mdbindery-...`) keeps, for each file key: the prepared Markdown (`k01.md`), the filter context (`k01.ctx.json`), the pandoc AST (`k01.json`), and the filter report (`k01.report.json`). It also keeps `merged.json`, `linked.json`, `links.ctx.json`, `links.report.json`, `book.json` (the AST with the metadata), `book.css`, `cover.jpg`, `book.epub` (pandoc's output before post-processing), the Mermaid sources with `mermaid-config.json`, and the rendered charts in `images/`. Comparing `k01.md` with the XHTML inside the EPUB is the quickest way to find lost text.

## Outputs

```
dist/
├── <slug>.epub              the ebook
├── <slug>-cover.jpg         full-size cover for store uploads
└── reports/
    ├── build.json           gate results and per-file statistics
    ├── build.log            the log of the build
    ├── epubcheck.json       EPUBCheck's own JSON report (all messages)
    └── ace/                 Ace's report: report.html, report.json, and their assets
```

`<slug>` is `slug` from the configuration, or the title in lowercase with every run of characters other than letters and digits replaced by a hyphen (`Writing a Book in Markdown` becomes `writing-a-book-in-markdown`). Letters of any script are kept, so a Russian title gives a Cyrillic file name; set `slug` if you want a Latin one.

- `build.json` holds `gates` (per gate, the result `pass`, `warn`, `fail`, or `skipped`, and its details), `files` (per file: pre-pass statistics, images, removed HTML, external links, math), `links` (unresolved and approximately matched links), `pandoc_warnings`, the paths of the EPUB and the cover, `ok`, `failed_gates`, `skipped_gates`, and `warning_gates`. It also records what made the book: `provenance` (the versions of mdbindery, Python, pandoc, EPUBCheck, and Ace, the git commit of the source, and the effective options) and `timings` (seconds per stage). Attach it to a bug report. The format is described in [design.md](design.md#buildjson).
- `build.log` has the same lines the console shows without `-q`.
- `epubcheck.json` is missing when EPUBCheck could not run. The build log and `build.json` show at most the first 50 EPUBCheck messages; this file has all of them.
- `ace/report.html` opens in a browser and lists each accessibility violation with the element that caused it.

At the start of each build, mdbindery deletes the files it wrote into `reports/` last time (`build.json`, `build.log`, `epubcheck.json`, and `ace/`), so a stale report never sits next to a new book. Other files you keep in `reports/` stay. The rest of the output folder is not cleaned: an EPUB with an old slug stays until you delete it.

When the build stops with exit status 2 before it starts (a configuration error, pandoc not found, an empty reading order, `-o` naming a file), nothing is written. When it stops later, for example on a chapter that is not UTF-8, an unreadable cover, or a tool that ran past its time limit, `build.json` describes the failure: `ok: false`, `failed_stage` (`analysis`, `identifier`, `cover`, `epub`, `epubcheck`, `ace`, or `wordcount`), `error`, the timings of the stages that finished, and `artifact`. `artifact` is `none`, or a warning that the EPUB in the output folder is from an earlier build. `build.log` has the log up to the error.

## Gates

A gate that fails makes the build fail (exit status 1, `BUILD FAILED: <gates> (details: <path to build.json>)`). A gate in `warn` state is logged but lets the build pass. The details are in the log and in `reports/build.json` under `gates`.

| Gate | Fails when | Warns when (the build passes) | Skipped when |
|---|---|---|---|
| `links` | An internal link has no target anchor, or a link points to a file that does not exist | The same problems with `options.strict_links: false` | Never |
| `images` | An image is missing, remote, has an empty path, or (in the trial build of a checked repository) lies outside the repository | Never | Never |
| `charts` | A Mermaid chart fails to render | The book has charts, `options.mermaid` is `png`, and mermaid-cli is not installed | Never |
| `includes` | An mdBook directive could not be expanded. The gate appears in `build.json` only in this case | Never | Never |
| `epubcheck` | EPUBCheck reports an `ERROR` or `FATAL` message, cannot run (no Java 11+ or no EPUBCheck), or crashes without writing a report | Never | `options.epubcheck: false` |
| `ace` | Ace reports a `critical` or `serious` violation whose rule is not in `options.ace_waivers`, or Ace is installed but produces no report | Ace is not installed | `--no-ace` or `options.ace: false` |
| `wordcount` | A file's word count in the EPUB differs from its source by more than `wordcount_tolerance` and by more than `wordcount_min_words` words | Never | Never |

### links

Every link to another book file, or to an anchor in the same file, must land on a heading, an `<a id>` anchor, or a reference-list entry. Anchors follow GitHub's rule (see [book-structure.md](book-structure.md#4-links)). A link is matched in three steps:

1. Exactly.
2. Ignoring letter case, as GitHub does. This is silent.
3. By a unique match that ignores ASCII punctuation and spaces (letters of every script are still compared). This works but is logged, and `mdbindery check` reports it as MB201 so you can make it exact:

   ```
     link in 02-setup.md to 02-setup.md#install_the_tools matched approximately (anchor is #install-the-tools)
   ```

A link that still has no target fails the gate. It is pointed at the start of the target chapter so the EPUB stays valid:

```
  UNRESOLVED link in 01-intro.md to 02-body.md#no-such-anchor (text: the body)
```

Links to files follow these rules:

- A link to `chapter.html` goes to `chapter.md` when that file is in the book, and a link to `folder/index.html` or `folder/` goes to that folder's `README.md` (or `readme.md`, `index.md`), as mdBook and websites name them. The file's log line counts them (`3 .html link(s) resolved to .md files`).
- A link to an existing file that is not in the book (`LICENSE`, source code, `../preface.md` above the book folder) points to `source_url`, resolved like a relative web address: `../preface.md` against `https://github.com/o/r/blob/main/get-started/` gives `https://github.com/o/r/blob/main/preface.md`. Without `source_url` the link is removed, its text stays, and the file's log line lists it: `links to files outside the book kept as text (no source_url): ['LICENSE']`. Neither case fails the gate.
- A link to a file that does not exist fails the gate: `LINK to a missing file in 02-setup.md: appendix/more.md`.
- When `source_url` is a website rather than a github.com address (for example `https://doc.rust-lang.org/book/`), links to files that are not in the repository may still exist on that site. They stay web links, are not checked, and do not fail the gate. The log counts them and names up to five, with their paths relative to the book folder:

  ```
    3 link(s) to pages that are not in the repository kept as web links (not checked): ['../api/index.html', '../guide/gone.md', '../other/README.md']
  ```

- With a website `source_url`, every link to a `.md` file outside the book, found or not, points to the published page: `../guide/start.md` becomes `.../guide/start.html`, and `../other/README.md` becomes `.../other/index.html`. A GitHub `source_url` keeps `.md`.

A path that starts with `/` means the root of the git repository that contains the book, as on GitHub. For a folder that is not in git, `/` is the book folder, or for an mdBook the folder with `book.toml`.

### images

The filter resolves every image path against the Markdown file's folder. A path starting with `/` means the repository root, as for links. An image URL that points into the same GitHub repository (`https://github.com/OWNER/REPO/blob/BRANCH/img/x.png?raw=true`, `raw.githubusercontent.com/...`) uses the local file instead, and the file's log line says so (`1 image URL(s) of this repository replaced by the local file`). The repository is known from `source_url` or from the `origin` remote of the git checkout.

Each image gets a status. `missing`, `remote` (`http://`, `https://`), and `empty` fail the gate. `outside` fails it too, but only in the trial build of a repository fetched by `mdbindery check <URL>`: such a repository is untrusted, so its images must stay inside it. A normal build uses any image file it can read.

An image that fails is replaced in the EPUB by the text `[image: <alt text>]` (or its path when there is no alt text), styled as `span.missing-image`, and logged:

```
  IMAGE remote: https://example.org/logo.png in 01-intro.md
  IMAGE missing: images/missing.png in 01-intro.md
```

Unsupported formats such as BMP pass this gate; EPUBCheck rejects them (RSC-032). Missing alt text does not fail a gate: `mdbindery check` warns about it (MB402), and the package metadata leaves out the `alternativeText` accessibility claim.

### includes

A directive that could not be expanded stays in the text as typed and is logged with the reason: `file not found`, `outside the repository`, `anchor not found: <name>`, `cannot read: ...`, or one of the limits that keep a bad include from blowing up a book: `include cycle: ch1.md -> a.md -> a.md`, `includes nested deeper than 10 levels`, `more than 5000 includes in one file`, `included text exceeds 20 MB in one file`.

```
  INCLUDE in 01-intro.md not expanded (file not found): {{#include listings/missing.rs}}
  INCLUDE in 01-intro.md not expanded (anchor not found: nosuchanchor): {{#include listings/hello.rs:nosuchanchor}}
```

`mdbindery check` reports the same problem as MB131.

### charts

Each Mermaid block is rendered once per build to a PNG in the work folder, with the `neutral` theme, an 18px font, and a white background (`mermaid_theme`, `mermaid_font_size`, and `mermaid_scale` change this). Gantt charts are drawn without the "today" line unless `mermaid_today_marker: true`, so a rebuild on another day gives the same image.

A chart that fails is replaced by a placeholder, a quote with the chart's alt text followed by "This chart is available in the online edition" and, when `source_url` is set, a link to the online version of the chapter. The gate fails:

```
  CHART in 02-body.md failed to render (placeholder used): Error: Parse error on line 2: ...t LR  A[Start --> B[ ----------------------^
```

When mermaid-cli is not installed (after `install-tools --no-node`) and `options.mermaid` is `png`, every chart becomes a placeholder and the gate is `warn`:

```
  warning: 1 chart(s) became placeholders: mermaid-cli is not installed (run `mdbindery install-tools`, or set options.mermaid: placeholder)
```

`options.mermaid: placeholder` gives placeholders on purpose without the warning, and `options.mermaid: keep` leaves the Mermaid source as a code block.

### epubcheck

EPUBCheck runs as `java -jar epubcheck.jar book.epub --json epubcheck.json -q` on a copy of the EPUB in a temporary folder, because Java on Windows reads command-line paths in the system code page and would break on names such as `Книга.epub`; the report is then copied to `reports/epubcheck.json`. The log line is `EPUBCheck: no messages`, or the count per severity followed by the first 50 messages:

```
  EPUBCheck: {'ERROR': 1}
    ERROR RSC-032: Fallback must be provided for foreign resources, but found none for resource "EPUB/media/file1.bmp" of type "image/x-ms-bmp". [EPUB/text/ch001.xhtml:21]
```

Warnings and usage notes do not fail the gate. The gate also fails when EPUBCheck cannot run, so an unvalidated book never ends with `BUILD OK`:

- No Java 11+ or no EPUBCheck:

  ```
    EPUBCheck: NOT RUN: Java 11+ or EPUBCheck missing (run `mdbindery install-tools`, or set options.epubcheck: false to build without validation)
  ```

- EPUBCheck starts but crashes or writes no valid report, for example with a damaged jar. The log shows the end of its output, and `build.json` records `EPUBCheck did not produce a report: ...` under `detail`:

  ```
    EPUBCheck: FAILED to run (exit 1): Error: Invalid or corrupt jarfile .../tools/epubcheck/x/epubcheck.jar
  ```

`options.epubcheck: false` turns the gate off (`EPUBCheck: skipped (options.epubcheck: false)`). Use it only for drafts on machines without Java.

### ace

Ace runs as `node <ace-puppeteer script> -f -s -o reports/ace <epub>`, with the headless Chrome build that matches its Puppeteer version. The log gives the totals and then one line per rule as `<impact> <rule> x<count>`. Only `critical` and `serious` violations block. To accept a rule, add its name to `options.ace_waivers`, for example `ace_waivers: [color-contrast]`; waived rules are still logged:

```
  Ace: 11 violation(s), 0 blocking
    serious color-contrast x11 (waived)
```

When Ace is not installed (after `install-tools --no-node`), the gate is `warn` and the build can pass:

```
  Ace: not run: not installed (tools were installed with --no-node); accessibility not checked. Run `mdbindery install-tools` to add it.
```

When Ace is installed but produces no report, the gate fails and the log says `Ace: FAILED to run:` followed by the end of Ace's output. `build.json` keeps up to 1000 characters of that output under `detail`. See [troubleshooting.md](troubleshooting.md#puppeteer-and-chrome-launch-failures) for launch problems; `--no-ace` builds the rest meanwhile.

### wordcount

This gate catches text lost or duplicated in conversion, usually by HTML that the conversion reads differently from GitHub. Both sides are counted for each file:

- Source: the prepared Markdown (after the pre-pass), converted to plain text by `pandoc -f gfm -t plain` with the filter `plaintext.lua`, which turns raw HTML into the text a reader sees (tags, comments, scripts, and styles removed, image alt text kept).
- EPUB: the XHTML files of the reading order, joined and cut at the level-1 heading of each source file, so any `split_level` works. Tags, `<head>`, entities, figure captions made from image titles, and the TeX copies of formulas are removed; image alt text is kept, as on the source side.

URLs are left out of both counts. A word starts with a letter or a digit and runs through the letters, digits, underscores, apostrophes, and hyphens that follow.

A file fails when the difference is larger than `wordcount_tolerance` (default `0.02`, 2%) and also larger than `wordcount_min_words` (default 25 words). The second condition is a floor: a difference of 25 words or fewer never fails, so short files do not fail on a few words.

Files with cards (`options.cards.files`) are checked like any other. Cards repeat a column label on every card and drop the header row, so the gate subtracts the repeated labels and adds back the header words before it compares. The difference is exact when no other text changed.

The count is a tolerance check, not a comparison of the text. It cannot see a word replaced by another word, or text moved within a file, and a loss smaller than the limit passes.

The log line on success names the largest difference only when some file's difference is above the floor:

```
  word count: every file within 2% or 25 words of its source
  word count: every file within 2% or 25 words of its source; largest difference 2.0% in 02-structure.md
```

On failure it names up to five files, worst first, with the source and EPUB counts and the sign of the difference (a `<textarea>` loses its text in this example):

```
  word count: FAILED: text lost or added beyond 2% or 25 words per file: 02-setup.md 44 -> 17 words (-61.4%)
```

`build.json` has the counts per file under `gates.wordcount.files` (`source`, `epub`, `diff`, and for files with cards `card_labels` and `compared`, the EPUB count after the label adjustment) and the failing files under `gates.wordcount.failing`.

## Reproducible builds

Building the same commit twice with the same tools gives byte-identical EPUB files. mdbindery does the following:

- It takes one timestamp for the build: the time of the last commit in the git repository that contains the book folder. If the folder is not in a git repository (or `git` is missing), it uses `metadata.date` when it has the form `YYYY-MM-DD`, and otherwise the modification time of the newest source file. Uncommitted changes do not change the git timestamp. With `date: git` (the default), the publication date in the book is this timestamp's UTC date.
- It passes the timestamp to pandoc as `SOURCE_DATE_EPOCH`, which sets the modification date in the package metadata. Timestamps before 1980-01-01 are raised to that date, because ZIP dates start in 1980; a book dated earlier still builds.
- It rewrites the ZIP container: `mimetype` first and uncompressed, every other entry deflated, every entry dated with the build timestamp (1980-01-01 if there is none; ZIP dates end in 2107), given permissions 0644, and marked as made on Unix, so the bytes are the same on Linux, macOS, and Windows. Blank lines are removed from the package document.
- The identifier must be stable, so keep an `identifier:` line in the configuration. With an empty line, the first build fills it in. Without the line, every build generates a new random identifier and the files differ.

The reports are not reproducible: they contain absolute paths, temporary folder names, and dates. A cover generated by mdbindery depends on the fonts found on the machine, and other versions of pandoc, Pillow, or mermaid-cli write other bytes, so compare builds made with the same tools.

## Covers

Every build writes two covers.

- The store cover, `dist/<slug>-cover.jpg`: your cover image at full size as an RGB JPEG (quality 92), or the generated cover. Upload this file where a store asks for a separate cover.
- The embedded cover inside the EPUB: the same picture scaled down to `cover.embed_height` pixels high (default 1000) to keep the book small. Readers show it in the library view and as the first page.

The cover image is `cover.image` from the configuration (a path relative to the configuration file's folder). Without that key, mdbindery looks for `cover.jpg`, `cover.jpeg`, or `cover.png` in the book folder and in its `images/`, `image/`, `img/`, `assets/`, `media/`, `figures/`, and `cover/` folders. Aim for 1600x2560 px (see [book-structure.md](book-structure.md#6-images)).

Any format Pillow can read works (JPEG, PNG, GIF, WebP, and others); it is converted to JPEG. Transparent areas are placed on white, CMYK images are converted to RGB, and the EXIF orientation of a phone photo is applied, so a rotated photo appears upright. A file that cannot be read stops the build with `build error: cover image cannot be read (...); save it again as JPEG`, and a wrong path with `build error: cover image not found: <path>`.

Without a cover image, mdbindery generates a 1600x2560 typographic cover: the title in a bold serif font, the subtitle and the authors in a sans-serif font, and an accent band, in the colors `cover.background` (`#1d2330`), `cover.foreground` (`#f2efe6`), and `cover.accent` (`#c8643b`). Fonts come from `fc-match` when it is available (asking for fonts that cover the book's language), then from a list of common Linux, macOS, and Windows fonts that cover Latin, Cyrillic, and Greek, then from Pillow's built-in font.

## Previewing pages

```
mdbindery preview EPUB OUT [PAGE ...] [--width 412] [--height 915] [--full]
```

`preview` opens pages of the EPUB in headless Chrome at phone size and saves PNG screenshots to the folder `OUT`. It needs the Node.js tools from `mdbindery install-tools`; after an install with `--no-node` it stops with ``preview error: preview needs Node.js and Puppeteer: run `mdbindery install-tools` (without --no-node)``.

- Without `PAGE` arguments it captures the cover, the title page, the table of contents, and the first two chapter files: `text/cover.xhtml`, `text/title_page.xhtml`, `nav.xhtml`, `text/ch001.xhtml`, and `text/ch002.xhtml`.
- A page is a path inside the EPUB, written with or without the `EPUB/` prefix (`text/ch003.xhtml` or `EPUB/text/ch003.xhtml`), optionally with an id to scroll to: `text/ch003.xhtml#k02-a-chart`. Chapter files are `ch001.xhtml`, `ch002.xhtml`, ... in reading order; list them with `unzip -l dist/<slug>.epub`.
- `--width` and `--height` set the viewport in CSS pixels (width 200 to 4000, height 200 to 8000). Screenshots are taken at device scale 2, so the defaults give 824x1830 px images. `--full` captures the whole page instead of one screen.
- Output names are the page path with `/` replaced by `_`, then `_<id>` when an id is given, `_full` with `--full`, and `.xhtml` removed: `text_ch003_k02-a-chart.png`, `text_ch002_full.png`. The command prints each file it wrote.

Before starting Chrome, `preview` checks its input and exits with status 2 on a problem: `preview error: EPUB not found: <path>`, `preview error: not an EPUB file: <path>`, a viewport out of range, or a page that is not in the EPUB. In the last case it lists the pages the book has and creates no output folder:

```
preview error: not in the EPUB: text/ch009.xhtml
pages: nav.xhtml, text/ch001.xhtml, text/ch002.xhtml, text/ch003.xhtml, text/ch004.xhtml, text/ch005.xhtml, text/cover.xhtml, text/title_page.xhtml
```

An id that does not exist on the page is not an error; the command captures the top of the page and prints:

```
WARN no element with id "k02-no-such" in text/ch003.xhtml; captured the top of the page
```

`preview` treats the EPUB as untrusted, since it may come from someone else: scripts in the book do not run, and a page may load only files from the EPUB itself (and `data:` URLs), never other files on your computer or anything from the network. EPUBs with more than 50,000 files or more than 2 GB unpacked are refused. Chrome runs with its sandbox where the system allows it (see [installation.md](installation.md#headless-chrome)). If the sandbox cannot start, `preview` prints a warning and takes that run's screenshots without it. Chrome renders the XHTML with the book's stylesheet, which is close to what reading apps show but not identical, so check the final file in a real reader too.

## Uploading to stores

Apple Books, Google Play Books, Kobo, and Amazon (Kindle Direct Publishing and Send to Kindle) accept EPUB files directly, so no MOBI or other conversion is needed. Upload `dist/<slug>.epub`, and upload `dist/<slug>-cover.jpg` where the store's form asks for the cover separately.

Before uploading:

- Build from a clean state and confirm `BUILD OK` with Ace installed and enabled, and `mdbindery doctor` showing EPUBCheck. With Ace missing, the build passes with a warning, but accessibility was not checked.
- Keep `metadata.identifier` unchanged between versions of the same book: stores and reading apps use it to recognize an update.
- Look through the book in at least one reading app, and use `mdbindery preview` for phone-size checks.

## Styling

- `options.extra_css`: a stylesheet appended after the default one. Use it for small changes.
- `options.css`: a stylesheet that replaces the default one. Start from a copy of [`src/mdbindery/data/epub.css`](../src/mdbindery/data/epub.css).
- `options.embed_fonts`: font files to embed in the EPUB (passed to pandoc as `--epub-embed-font`). Refer to them in your CSS with `@font-face`. Remote fonts (`@import url(https://...)`) are not allowed in an EPUB and fail EPUBCheck with RSC-006.
- `options.highlight_style`: the pandoc style for code highlighting, or `none`. The default, `monochrome`, stays readable on e-ink and passes Ace's contrast check; colored styles may not.

Paths in these options are relative to the configuration file's folder. The details are in [configuration.md](configuration.md#styling).

mdbindery produces these classes and elements besides pandoc's usual markup (headings inside `section` elements, `figure`/`figcaption`, `a.footnote-ref`, `nav#toc`):

| Selector | Produced by | Default style |
|---|---|---|
| `div.cards`, `div.card` | Wide tables in files listed under `options.cards.files`: one `div.card` per row inside a `div.cards` | Bordered block per row, kept on one page when possible |
| `div.full-page` | An image whose title starts with `full-page` (`"full-page"` or `"full-page: Caption"`, any letter case); the `figure` sits inside the div | Page break before and after; image at most 92% of the screen height |
| `div.references` | The visible reference list built from reference definitions (a `ul` inside the div) | No bullets, hanging indent, long URLs may break anywhere |
| `a.citation` | A citation such as `[1]`, linked to its entry in the reference list | None (an ordinary link) |
| `a.footnote-back` | The number at the start of each endnote, linked back to the note reference in the text | Bold, not underlined |
| `img.inline` | An image inside a sentence | At most 1.4em high, aligned with the text |
| `span.missing-image` | The `[image: ...]` text that replaces an image that failed the images gate | Italic |
| `div.note`, `div.tip`, `div.important`, `div.warning`, `div.caution` | GitHub alerts (`> [!NOTE]` and the others); each box starts with a `div.title` | Colored left border and light tint per type |
| `span.small` | HTML `<small>` | 0.85em |
| `mark` | HTML `<mark>` | Light yellow background |
| `hr` | A scene break (`***`) or a horizontal rule | Centered asterism instead of a line |
| custom classes | `<div class="name">` on a line of its own, a blank line, Markdown, a blank line, `</div>` | None; define them in `extra_css` |

Every tinted box (block quotes, code blocks, table headers, GitHub alerts, `mark`) sets its text color (`#1a1a1a`) together with its background, so the text stays dark on the light tint when a reading app switches to a night theme with light text. The title page is centered.

After changing colors, build with Ace enabled: text with too little contrast against its background fails the `color-contrast` rule, a `serious` violation.
