# Design

This page describes how mdbindery works inside, for people who change its code. User-facing behavior is in [building.md](building.md), [checking.md](checking.md), [configuration.md](configuration.md), and [installation.md](installation.md); the book rules are in [book-structure.md](book-structure.md).

mdbindery is a small Python package (dependencies: PyYAML and Pillow; Python 3.9 or newer) that orchestrates external programs. pandoc does all parsing and EPUB writing. Two Lua filters shipped with the package adapt GitHub-style Markdown to a single EPUB and prepare text for the word count. EPUBCheck, DAISY Ace, and the word count validate the result.

## Module map

| Path | Responsibility |
|---|---|
| `src/mdbindery/cli.py` | argparse front end for `build`, `check`, `init`, `install-tools`, `doctor`, `preview`; exit codes; one-line errors on stderr; writes `reports/build.log` after a build |
| `src/mdbindery/__main__.py` | `python -m mdbindery` |
| `src/mdbindery/__init__.py` | `__version__`, the only place the version is set (`pyproject.toml` reads it) |
| `src/mdbindery/config.py` | `DEFAULTS`; loading, merging, and validating `mdbindery.yaml`; unknown-key errors and warnings; reading-order discovery (toc files, README links, file names); mdBook `book.toml` and `SUMMARY.md`; inference of title, rights, language, cover, slug; git facts (repository root, GitHub remote, branch); containment rules for untrusted repositories; `save_identifier()`; `starter_yaml()` for `init` |
| `src/mdbindery/markdown.py` | The line-based pre-pass: block splitting (`split_blocks()`), heading scan, `drop_sections`, `drop_lines`, mdBook directives, hidden Rust lines, Mermaid source and alt text, reference definitions and the generated reference list; `mask_dropped()` for `check` |
| `src/mdbindery/build.py` | `analyze()` (pre-pass, per-file pandoc pass, links pass), the Mermaid renderer, covers, metadata, stylesheet, the EPUB call, `postprocess()`, the gates, and `build()` |
| `src/mdbindery/data/book.lua` | The main pandoc Lua filter, with a `file` phase and a `links` phase |
| `src/mdbindery/data/plaintext.lua` | Filter for the word count: raw HTML becomes the text a reader sees |
| `src/mdbindery/data/epub.css` | Default stylesheet |
| `src/mdbindery/check.py` | `check`: fetching a folder, GitHub URL, or git URL; static checks with MB codes; reuse of `analyze()`; the optional trial build; Markdown and JSON reports |
| `src/mdbindery/cover.py` | Generated typographic cover; fonts come from fontconfig (`fc-match`) for the book's language, else from a list of common system fonts |
| `src/mdbindery/preview.py` | Phone-size screenshots through Node.js and Puppeteer |
| `src/mdbindery/tools.py` | Tool home, tool discovery, commands, the environment for tool processes, the process runner (time limits, stopping process trees), Chrome sandbox handling |
| `src/mdbindery/installer.py` | `install-tools`: pinned versions and checksums, download, verification, safe extraction; `self_test()` used by `doctor` |
| `install/install.sh`, `install/install.ps1` | Bootstrap installers: uv, the isolated environment, then `install-tools` |
| `tests/` | pytest suite, fixture books, and the CI script for non-ASCII paths |
| `examples/sample-book/` | A small book that uses every feature; CI builds it |

## Data flow

```
mdbindery.yaml -> config.load() -> Config (data, path, base, source, repo_root, trusted, github, ...)

for each file in the reading order (key k00, k01, ...):
  <file>.md
    -> markdown.prepass()                                  -> work/kNN.md
    -> pandoc -f gfm -t json --lua-filter book.lua         -> work/kNN.json
         (MDBINDERY_PHASE=file, MDBINDERY_CTX=work/kNN.ctx.json)
                                                           -> work/kNN.report.json

concatenate the blocks of every kNN.json                   -> work/merged.json
pandoc -f json -t json --lua-filter book.lua               -> work/linked.json
     (MDBINDERY_PHASE=links, MDBINDERY_CTX=work/links.ctx.json)
                                                           -> work/links.report.json

linked.json + metadata as literal MetaString values        -> work/book.json
pandoc -f json -t epub3 book.json (SOURCE_DATE_EPOCH set)  -> work/book.epub
  with work/book.css and work/cover.jpg
postprocess(): accessibility metadata, numbered endnotes,
  normalized zip written to <slug>.epub.part, then renamed -> <out>/<slug>.epub
gates: charts, links, images, includes, EPUBCheck, Ace, word count
                                                           -> <out>/reports/
```

`work` is a temporary folder (`tempfile.mkdtemp(prefix='mdbindery-')`), deleted at the end unless `--keep-work` is given. Mermaid sources go to `work/mermaid-<hash>.mmd`, the chart config to `work/mermaid-config.json`, and PNGs to `work/images/mermaid-<hash>.png`, where the hash is the first 12 hex digits of the SHA-256 of the chart source.

Why one pandoc run per file instead of one run over all files: pandoc would concatenate the inputs and lose what each file needs on its own, namely its folder (for relative image and link paths), its reference definitions, and GitHub's per-file anchor namespace. The second pass is needed because a link can only be resolved once the identifiers of the whole book are known.

`build()` in order: refuse an empty reading order, a missing pandoc, an output folder that is a file, and a slug that is not a plain file name, before anything is written; create `<out>/reports/` and remove only the files a build writes there (`build.json`, `build.log`, `epubcheck.json`, `ace/`); compute the timestamp (`source_epoch()`: last git commit, else a fixed `metadata.date`, else the newest source file); run `analyze()`; save a generated identifier (`ensure_identifier()`); log one line per file; decide the charts, links, images, and includes gates; make the covers; write the stylesheet; run pandoc; log its warnings; post-process; run EPUBCheck, Ace, and the word count; write `build.json` (atomically, through a `.part` file). Each stage's duration goes into `timings`, and `provenance()` records the tool versions, the source commit, and the effective options. An exception after `reports/` exists (a `BuildError` or any other) still writes `build.json` with `ok: false`, `failed_stage`, `error`, and `artifact` (`none`, or a note that the EPUB in the folder is from an earlier build), then propagates. The CLI writes `build.log` from the collected log lines after `build()` returns or raises `BuildError`. `build(..., analysis=a)` reuses a result of `analyze()` instead of running it; the caller then owns the work folder (`a['work']`), which `build()` leaves alone.

## Loading the configuration

`config.load(target, config_path, name_hint, trusted, repo_root, ignore_config)` in order:

1. Find the file: `config_path`, else `target` when it is a file, else `mdbindery.yaml` or `mdbindery.yml` in the folder. `base` (what config paths are relative to) is the file's folder; the source folder is `source_dir`, else the folder given on the command line, else `base`.
2. Parse YAML (errors name the file, line, and column). Unknown top-level keys raise `ConfigError`; unknown nested keys become `Config.warnings`.
3. mdBook: a `book.toml` in the source folder (also one that `source_dir` points to) moves the source to its `src` (default `src/`) when that holds `SUMMARY.md`; a `SUMMARY.md` with `book.toml` one level up is read too. The folder with `book.toml` is remembered as `book_root`. `book.toml` supplies title, authors, description, and language. A `SUMMARY.md` without any `book.toml` is not an mdBook: it only feeds the reading order in step 6.
4. `deep_merge()` with `DEFAULTS`, then `validate()`: types, ranges, allowed values, colors, `slug`, `source_url` (a trailing `/` is added), regular expressions in `drop_lines`.
5. Git facts (`git_facts()`, only for trusted books): the checkout root becomes `repo_root` when it contains the source folder; outside git, `repo_root` is `book_root` for an mdBook (so `{{#include ../listings/...}}` reaches beyond `src/`), else the source folder. The `origin` remote gives `github` and, with the branch, `suggested_source_url`. For untrusted books, `source_dir`, `css`, `extra_css`, `embed_fonts`, and `cover.image` must stay inside `repo_root`. `load()` builds one predicate for this, `ok(path)`: always true for a trusted book, else `contained(path, guard)`, where `guard` is the resolved repository root and `contained()` compares resolved paths, so a symlink is judged by its target. The same predicate guards the configuration file itself, `book.toml`, `discover_files()`, `find_cover()`, `detect_rights()`, and every `files:` entry (`files entry X points outside the repository`).
6. Files: entries are normalized (`./a.md` to `a.md`; absolute paths and `..` are errors), get `role: chapter` and `key: kNN` by default, and duplicate keys or files are errors (found with a `Counter`). Without `files:`, `discover_files()` looks in `chapters/` when it exists, else in the source folder, skipping `README.md` and the names in `SKIP_FILES`. The order comes from the first of `TOC_FILES` (`SUMMARY.md`, `toc.md`, `TOC.md`, `contents.md`, `CONTENTS.md`, `table-of-contents.md`) that links to local `.md` files (one link is enough for `SUMMARY.md`, the others need two; with `SUMMARY.md`, unlisted files are left out, and with the others they follow by name); else, when the chapter files are not all numbered, from the README's links if they cover at least half of the files; else from the names (`matter_group()`: front matter names first, then chapters, numbered ones in natural order, then appendices (`appendix`, `приложение`, or `ap`/`app` plus a letter from a to h, such as `apA` or `app-b`), then back matter). `README.md` goes first as front matter, except with `SUMMARY.md`, which must list it. `Config.order_source` records where the order came from.
7. Inference for what is still empty: title (`book.toml`, the first level-1 heading of the README or first file, `name_hint`, the folder name), rights (`detect_rights()` on LICENSE-like files in the source folder, then the repository root), language (`book.toml`, else a Cyrillic-share guess between `ru` and `en-US`), cover (`find_cover()`), and slug. The accessibility summary is left empty here: `options._summary_lang` records the book's language, and the build writes `default_summary()` once it knows whether every image has alt text. `Config.inferred` lists what was guessed, and `options._mdbook` (true only when a `book.toml` was found) marks mdBook books.

## The pre-pass

`markdown.prepass()` works on lines. It never rewrites the author's text lines: it removes lines and sections, expands includes, replaces Mermaid blocks, and inserts the reference list. Citations are linked later, on the pandoc AST. In order:

1. Normalize line endings and remove a byte order mark.
2. Expand mdBook directives (`expand_includes()`), in every file, before anything else: `{{#include path}}`, with a line selection (`:N`, `:N:M`, `:N:`, `::M`) or an anchor (`:name`, the lines between `ANCHOR: name` and `ANCHOR_END: name`); `{{#rustdoc_include ...}}` and `{{#playground ...}}` the same way. `{{#title ...}}` is removed, and `\{{#include ...}}` becomes the literal text. Paths are relative to the Markdown file and must stay inside the repository root; `ANCHOR` marker lines are dropped from included text; nested directives are expanded too. `expand_includes(text, base_dir, root, origin)` keeps the chain of resolved files it is inside (starting with `origin`, the file being prepared) and stops at `INCLUDE_MAX_DEPTH` (10) levels of nesting, `INCLUDE_MAX_DIRECTIVES` (5000) expansions per file, and `INCLUDE_MAX_BYTES` (20 MB) of included text per file. Failures (`outside the repository`, `file not found`, `cannot read: ...`, `anchor not found: ...`, `include cycle: ch1.md -> a.md -> a.md`, and the three limits) leave the directive in place and are returned in `stats['include_errors']`. It returns `(text, expanded, errors)`; `check` uses the same call with the same origin.
3. Remove sections named in the file's `drop_sections`: a heading and everything below it up to the next heading of the same or a higher level. `dropped_spans()` finds the line ranges once; `drop_sections()` removes them and `check`'s `mask_dropped()` blanks them.
4. Split the file into blocks with `split_blocks()`, which yields `(kind, info, start_line, lines)`:
   - `text`: everything else;
   - `code`: a fenced block (backticks or tildes, also indented in list items and behind `>` quote markers; `info` is the lowercased first word of the info string). A line that starts with ```` ```code``` ```` followed by text is inline code, not a fence;
   - `icode`: an indented code block (four spaces or a tab after a blank line, outside lists). Trailing blank lines are returned to the text;
   - `comment`: an HTML comment block that starts a line (`<!--`, also multi-line, also behind `>`).
5. In `code` blocks: a `mermaid` block is replaced by what the render callback returns (unless `options.mermaid: keep`); in mdBook books (`options._mdbook`), `rust` blocks lose their hidden lines (`hide_rust_lines()`: a line `# x` or a bare `#` is removed, `##x` becomes `#x`). Other code, `icode`, and `comment` blocks pass through unchanged.
6. In `text` blocks: lines matching any `options.drop_lines` pattern are removed and counted. With `options.citations: refdefs`, reference definitions (`[label]: url "title"`, also `'title'` or `(title)`, also behind `>` quote markers) whose label counts as a citation (`is_citation_label()`: numeric labels, or every label with `options.citation_labels: all`) are collected. Labels that images use (`![alt][label]`, `![label]`, found by `image_labels()`) are never citations, and neither are named labels whose URL ends in an image extension (`IMAGE_EXT_RE`). The definition lines stay in the text, so pandoc still resolves every reference link and image.
7. If citation definitions were found, build the list: numeric labels first, in numeric order, then the other labels in order of first appearance. `label_ids()` gives each label an anchor `ref-<slug>`, where the slug keeps Unicode letters (`ref-иванов`) and repeats get `-2`, `-3`. Each entry is a Markdown list item `- <a id="ref-1"></a>\[1\] Title. <url>` (the title is Markdown-escaped, bare URLs in it become autolinks, and a period is added unless it ends with `.`, `?`, or `!`). The list is wrapped in `<div class="references">` and inserted after the last heading whose text is in `options.reference_headings` (after the underline for a setext heading), or after a new `## <reference_heading_new>` heading appended at the end.

`prepass()` returns the prepared text and `stats`: `mermaid` (charts replaced), `dropped_lines`, `dropped_sections` (headings), `includes` (directives expanded), `include_errors` (`[directive, error]` pairs), `citations` (`[{label, url, id}]`, passed to the filter), and `references` (list entries, present only when there are any).

The Mermaid callback (`build.Mermaid`) receives the chart source and alt text. `mermaid_source()` adds `todayMarker off` to Gantt charts unless `options.mermaid_today_marker` is true, so the image does not depend on the build date. `mermaid_alt()` takes the file's `mermaid_alt`, else the chart's `title` line or `title:` front matter, else its node labels, after `options.mermaid_alt_prefix`. mermaid-cli runs as `mmdc -q -i <mmd> -o <png> -b white -c mermaid-config.json -s <mermaid_scale> -p <puppeteer-config.json>`; the config sets `theme` (`mermaid_theme`) and `themeVariables.fontSize` (`mermaid_font_size`). A rendered chart becomes `![alt](<absolute png path>)`; a failed or disabled one becomes a quote: `> alt. This chart is available in the online edition: <source_url + file>`. Failures are collected as `{file, alt, error}` (the error trimmed to 300 characters).

The reference list is built in Python because pandoc's Markdown reader turns reference definitions into invisible link targets: a filter cannot recover the list of definitions from the AST. Recognizing the citations themselves is easier on the AST, where code, math, and URLs are already separate elements.

## The Lua filter

`book.lua` reads its context with `pandoc.system.read_file()` from the JSON file named in `MDBINDERY_CTX` (read through `pandoc.system.environment()`), decodes it with `pandoc.json`, and runs the phase named in `MDBINDERY_PHASE`. Each phase writes its report with `pandoc.system.write_file()` to `ctx.report`. File existence is tested with `pandoc.path.exists()`, and `pandoc.system.list_directory()` tells a folder from a file. These pandoc functions handle Unicode paths on Windows; Lua's own `io` library does not.

### File phase

Runs on one prepared file (`gfm` to `json`), in this order:

1. Raw HTML blocks, in every list of blocks (top level, block quotes, list items, divs), through `doc:walk{ Blocks = convert_blocks }`. A block that is exactly `<div class="...">` opens a Div with those classes, closed by a `</div>` block; an unclosed one is flattened into its parent. A comment block is dropped. `<a id="x"></a>` or `<a name="x"></a>` alone becomes an empty Span with that id. Any other HTML block is parsed by pandoc's HTML reader (`pandoc.read(text, "html")`); tags that are not wrappers, inline formatting, void, or structural (tables, lists, headings, quotes, `pre`, definition lists, `a`, `img`) are counted in `html_removed`. Images from such blocks follow the HTML alt rule below, image by image: the filter reads each `<img>` tag of the block (comments removed) and pairs them with the reader's images in order; only when the counts differ does it fall back to the image's caption. `id` attributes that the HTML reader drops (on a bare `<pre>`, for example) are kept as empty Spans before the block, so links to them still resolve. A block pandoc cannot parse is counted as `unparsed-block`.
2. Inline HTML, in every list of inlines. Comments are dropped. `<a id>` or `<a name>` without `href` becomes an empty Span with the id. `<br>` becomes a line break. `<img>` becomes an Image; an `<img>` without an `alt` attribute is marked as missing alt text, `alt=""` as decorative. Attribute values are HTML-entity-decoded once (`alt="R&amp;D"` gives `R&D`). Paired tags (`sup`, `sub`, `b`, `strong`, `i`, `em`, `u`, `ins`, `s`, `del`, `strike`, `kbd`, `code`, `q`, `small`, `mark`, and `a href`) become the matching pandoc element when the closing tag is in the same inline list; `kbd` and `code` flatten their content to text; `small` and `mark` become Spans with those classes. Wrapper tags (`span`, `font`, `center`, `p`, `div`, `abbr`, `cite`, `dfn`, `time`, `var`, `samp`, `details`, `summary`, `picture`, `figure`, `figcaption`, `big`, `tt`) are dropped silently with their content kept. Anything else, including a paired tag without its closing tag, is dropped and counted; unknown tags such as mdBook's `<Listing>` lose the tag and keep the content.
3. Figures. pandoc's HTML reader already turns a `<figure>` block into a Figure (the `<figcaption>` becomes its caption); its images are resolved as `kind: figure`. A paragraph that holds only one image (spaces and line breaks allowed) becomes a Figure: without a caption when the image has no title (`kind: block`), with the title as caption otherwise (`figure`), and wrapped in a `full-page` Div when the title starts with `full-page` or `fullpage` in any letter case (`full-page`; the text after an optional `:` or `-` is the caption). A Plain block (an HTML `<img>` line, for example) that holds only one image is treated the same way at the top level or directly inside a Div other than a card, but not in table cells or tight lists, where images stay inline. An image that cannot be resolved becomes a paragraph with a placeholder instead.
4. Every other image gets the class `inline` and is resolved as `kind: inline`; an unresolved one becomes a placeholder Span. Inline math is recorded in `math` (the TeX source, at most 120 characters), which `check` uses for MB711.
5. Chapter title (`fix_title()`). Every file must start with one level-1 heading, or pandoc (with `--split-level 1`) merges it into the previous chapter. Without a level-1 heading:
   - with a `title:` for the file, a new level-1 heading with that text is inserted (`h1_fix: "title"`);
   - else, if the first visible block is a heading (empty anchors and comments above it do not count), that heading is promoted to level 1 (`"promoted"`), every other heading of the file moves up by the same number of levels but never above level 2, and the anchors that were above it move below it;
   - else a heading is inserted from `ctx.fallback_title` (the book title, for `README.md`) or from the file name without folder, extension, leading digits, spaces, dots, underscores, and hyphens, with `-` and `_` turned into spaces and the first letter capitalized (`"filename"`).

   Inserted headings get an identifier from `slug()` that `unique_id()` makes unique in the file (`intro-1` when `intro` exists), so EPUBCheck sees no duplicate ids. When a level-1 heading exists but is not the first block, the blocks above it move below it and the number of visible ones is reported as `moved_before_h1`. Finally, a `title:` replaces the text of an existing level-1 heading; its identifier and any empty anchor Spans inside it stay, so links to the original anchors keep working.
6. Heading anchors. Empty Spans with an id inside a heading (from `<a id>` in the heading line) move into a Plain block right after the heading, because EPUB navigation entries must be text only (EPUBCheck RSC-005).
7. Tables. In a file listed under `options.cards.files`, a table with at least `card_min_columns` columns becomes a `cards` Div with one `card` Div per row, rows inside bodies' heads and the table foot included, so no cell is lost; header rows after the first become one bold line above the cards (cells joined with ` / `). In each card the first `card_title_columns` cells form a bold heading, and every other non-empty cell becomes a paragraph `<column header>: value` (cells with several blocks keep their structure). The first empty anchor in the row's first cell becomes the card's identifier; further anchors from that cell stay as empty Spans at the start of the card. Every column label a card adds is recorded in `card_labels` and the text of each table's first header row in `card_headers`, so the word count can subtract exactly what cards repeat. Other tables with at least `wide_table_warn` columns are reported in `wide_tables`.
8. Identifiers: see [Identifier prefixing](#identifier-prefixing).
9. Links and citations: see [Citations](#citations) and [The mdbindery:// link scheme](#the-mdbindery-link-scheme).
10. The report is written.

#### Image resolution

`resolve_image()` records `{src, kind, alt, status}` for every image, plus `path` when the file was found and `local_copy` for a same-repository URL. `alt` is true when the image has alt text or is an HTML decorative image (`alt=""`); Markdown `![](x)` and `<img>` without `alt` count as missing. The source is resolved like this:

| Source | Resolved to | Status |
|---|---|---|
| empty | | `empty` |
| a GitHub URL of this repository (`github.com/O/R/blob/BRANCH/p`, `.../raw/BRANCH/p`, `raw.githubusercontent.com/O/R/BRANCH/p`, with `?raw=true` and similar ignored), where `O/R` equals `ctx.github` | `<repo_root>/p`; `local_copy` is `p` | `ok`, or `remote` when the local file is missing |
| any other URL (a scheme other than `file:`) | | `remote` |
| a path inside `ctx.work_dir` | as is (a rendered chart) | `ok` |
| `file:///abs/p`, `C:\...`, `C:/...`, or a UNC path `\\host\...` | as is (a file on this machine) | `ok` or `missing` |
| `/p` | `<repo_root>/p` (GitHub resolves `/` against the repository root) | `ok` or `missing` |
| anything else, including `file:p` and `file://p` (percent-decoded, `?query` and `#fragment` removed) | relative to `ctx.file_dir` | `ok` or `missing` |

When `ctx.image_root` is set (repositories fetched by `check`, see `Config.trusted`), a resolved path outside it gets `outside`, and so does a path under any entry of `ctx.blocked`: the symlinks in the repository whose targets leave it (`build.escaping_links()`), since Lua cannot resolve symlinks itself. An `ok` image's source is replaced by the absolute path, which pandoc embeds. Any other status leaves a text placeholder `[image: <alt or src>]` in a Span with class `missing-image`, so the EPUB never gets a broken image reference; the images gate then fails the build.

#### Citations

`ctx.citations` lists `{label, url, id}` from the pre-pass. In `rewrite_link()`, a Link whose text equals a citation label (compared in lowercase with spaces collapsed) and whose target equals that label's URL (both percent-decoded) becomes a Link with the text `[label]`, the target `#<id>`, and the class `citation`; the label is recorded in `cited`. The target then goes through the link scheme like any in-file anchor. Because the test is on the AST, the shortcut `[1]`, the collapsed `[1][]`, and an inline `[1](same URL)` all become citations, while `[text][1]` (different text), `![alt][1]`, code, math, and URLs never do. `analyze()` compares `cited` with the file's citation labels and adds `stats['uncited']`.

#### The mdbindery:// link scheme

A link target with a URL scheme is kept, with characters that EPUBCheck rejects in URLs (`[`, `]`, `"`, `<`, `>`, `\`, `^`, `` ` ``, `{`, `|`, `}`, and space) percent-encoded (`clean_url()`; an IPv6 host in brackets is left alone). Any other target is split into a path and a fragment, both percent-decoded; backslashes become `/` and a `?query` is dropped. The path is resolved:

- empty: the same file;
- starting with `/`: the repository root, as on GitHub. The result is made relative to the book folder: `ctx.source_prefix` (the book folder relative to the repository root) is removed when the path starts with it, else `ctx.root_prefix` (the repository root relative to the book folder, such as `..`) is put in front, so `/book/01-a.md` becomes `01-a.md` and `/src/x.py` becomes `../src/x.py`;
- anything else: relative to the file's folder (`ctx.file_rel_dir`).

`normalize()` removes `.` and `a/..` segments but keeps leading `../` segments, so links that climb out of the book folder stay correct. The normalized path is looked up in `ctx.files`, which maps each book file to its key. When that fails, two web-style forms are tried, each counted in `html_links`: a path ending in `.html` or `.htm` with `.md` instead (mdBook), and a path ending in `index.html` or `/` as the folder's `README.md`, `readme.md`, or `index.md` (mdBook builds `README.md` as `index.html`).

- Found: the target becomes `mdbindery://<target key>/<fragment>` followed by the byte `\x1f` (written `"\31"` in Lua) and `from=<source key>`.
- Not found, `source_url` set: `outside_url()` resolves the path against `source_url` like a relative URL (`../preface.md` against `.../blob/main/get-started/` gives `.../blob/main/preface.md`), the fragment is appended, and the report records `{"path": ..., "mode": "source_url", "exists": ...}`. `source_url` can be a GitHub blob URL or a published website. For a website (a host that is not github.com), a path ending in `README.md` becomes `index.html` and any other `.md` becomes `.html`, as sites built from Markdown serve them.
- Not found, no `source_url`: the link is replaced by a Span with its text (a dead link would fail EPUBCheck RSC-007), and the report records `mode: "unlinked"`.

`exists` says whether the path exists under the source folder (a folder counts). `build()` fails the links gate for every entry with `exists: false`, except `source_url` entries when `source_url` is a website rather than github.com (`build.site_links()`): those stay web links, are logged, and are not checked.

The links phase needs only the target key and fragment. The source key is carried along so that reports can name the file that contains a bad link: `check` maps it back to a file and searches that file for `#<fragment>` to report a line number. `\x1f` (the ASCII unit separator) does not occur in real link targets, which makes it a safe separator. No `mdbindery://` link survives the links phase.

### Links phase

Runs once on `merged.json` (`json` to `json`). It collects the identifiers of every Header, Span, Div, Table, and Figure, plus the chapter start of every file from `ctx.h1`, and groups them by key (the text before the first `-`). Then, for each `mdbindery://` link:

1. No fragment: the target is the chapter start (`ctx.h1[key]`).
2. `<key>-<fragment>` exists: use it.
3. `<key>-<fragment in lowercase>` exists: use it (GitHub matches anchors case-insensitively).
4. Exactly one identifier of that key is equal after lowercasing and removing ASCII punctuation and whitespace (`squash()`; letters of every script are kept): use it and record it in `fuzzy`.
5. Otherwise record the link in `unresolved` and point it at the chapter start, so the EPUB stays valid.

Every link ends up as `#<identifier>`. pandoc rewrites these to `chNNN.xhtml#<identifier>` when it splits the book into files.

### Identifier prefixing

The files are merged into one document, but GitHub anchors are only unique within one file: two chapters can both have a `## Summary` section. The file phase therefore prefixes every identifier on a Header, Span, Div, CodeBlock, Table, Figure, and Image with `<key>-`.

- Keys are `k00`, `k01`, ... by position in the reading order (`config.load()` sets them with `f'k{i:02d}'`). A file entry may set `key:` itself. `config.load()` accepts only letters, digits, and underscores, because the links phase takes the text before the first `-` of an identifier as its key, and rejects duplicate keys.
- Headings get their identifiers from pandoc's `gfm` reader (GitHub's algorithm). A heading without one gets `slug()`: the text in lowercase with runs of whitespace and punctuation turned into `-`.
- The first level-1 heading is the chapter start, and its identifier is reported as `h1`. A fallback inserts an empty Span with id `<key>` when there is no level-1 heading, but `fix_title()` makes sure one always exists.
- Reference entries become `<key>-ref-<label slug>`, for example `k01-ref-1`.

## JSON contracts

pandoc's JSON encoder writes an empty Lua table as `{}`. `build.load_report()` turns `{}` back into `[]` for the keys that are lists (file report: `ids`, `wide_tables`, `external`, `images`, `html_removed`, `cited`, `math`, `card_labels`, `card_headers`; links report: `unresolved`, `fuzzy`), so readers of the raw files should do the same.

### Filter context

File phase (`work/kNN.ctx.json`, written by `analyze()`):

| Key | Contents |
|---|---|
| `key`, `file` | this file's key and its path relative to the source folder |
| `files` | every book file (POSIX path relative to the source folder) mapped to its key |
| `file_dir` | absolute folder of this file |
| `file_rel_dir` | folder of this file relative to the source folder, `""` at the top |
| `title` | the file's `title:` from the configuration, or `""` |
| `fallback_title` | the book title for `README.md` (any case), else `""` |
| `citations` | `[{label, url, id}]` from the pre-pass |
| `cards` | true when the file is listed in `options.cards.files` |
| `card_min_columns`, `card_title_columns`, `wide_table_warn` | from `options` |
| `source_url` | `source_url`, or `""` |
| `github` | `owner/repo` of the book's GitHub repository, or `""` |
| `source_root` | absolute source folder |
| `repo_root` | absolute repository root (`/` in links and images) |
| `root_prefix` | the repository root relative to the source folder, `""` when they are the same |
| `source_prefix` | the source folder relative to the repository root, `""` when they are the same |
| `work_dir` | the work folder (rendered charts live there) |
| `image_root` | `""` for local books; the repository root for repositories fetched by `check` |
| `blocked` | for repositories fetched by `check`: absolute paths of symlinks that point outside the repository; empty otherwise |
| `report` | where to write the file report |

Links phase (`work/links.ctx.json`): `{"h1": {"k00": "k00-writing-a-book-in-markdown", ...}, "report": ".../links.report.json"}`.

### File report

`work/kNN.report.json`, from the sample book (paths shortened, empty lists as `load_report()` returns them):

```json
{
  "cited": ["2", "1"],
  "external": [],
  "h1": "k01-1-why-markdown",
  "h1_fix": "",
  "html_blocks": 0,
  "html_links": 0,
  "html_removed": [],
  "ids": ["k01-ref-1", "k01-ref-2", "k01-1-why-markdown", "k01-plain-text-lasts", "k01-references"],
  "images": [
    {"alt": true, "kind": "figure", "path": ".../sample-book/images/pipeline.png",
     "src": "images/pipeline.png", "status": "ok"},
    {"alt": true, "kind": "inline", "path": ".../sample-book/images/icon.png",
     "src": "images/icon.png", "status": "ok"}
  ],
  "math": [],
  "moved_before_h1": 0,
  "wide_tables": []
}
```

- `images[]`: `kind` is `inline`, `block`, `figure`, or `full-page`; `status` is `ok`, `missing`, `remote`, `empty`, or `outside`; `path` is present only for `ok`; `local_copy` only for a same-repository URL.
- `external[]`: `{path, mode, exists}`, `mode` `source_url` or `unlinked`; `path` is relative to the source folder and may start with `../`.
- `html_removed[]`: `{tag, count}`; `html_blocks`: HTML blocks handed to pandoc's HTML reader; `html_links`: web-style links (`.html`, `index.html`, a folder with `/`) resolved to book files.
- `h1_fix`: `""`, `title`, `promoted`, or `filename`; `moved_before_h1`: visible blocks moved below the title.
- `wide_tables[]`: column counts; `math[]`: inline TeX; `cited[]`: citation labels that were linked.
- `card_labels[]`: the column label of every field the cards added; `card_headers[]`: per converted table, the text of its first header row.

### Links report

`work/links.report.json`:

```json
{
  "unresolved": [{"key": "k01", "fragment": "no-such-anchor", "text": "the body", "source": "k00"}],
  "fuzzy": [{"from": "k02-water-budget-ample_ice", "to": "k02-water-budget-ample-ice",
             "key": "k02", "fragment": "water-budget-ample_ice", "source": "k00"}]
}
```

`key` is the target file's key and `source` the key of the file that contains the link. `analyze()` adds `file`, the target file's path, to every entry.

### analyze() result

```
{
  "files": {"<file>": {"key": "k01", "stats": {<pre-pass stats> + "uncited"}, "report": {<file report>},
                       "prepared": "<work/k01.md>"}},
  "h1": {"k01": "k01-1-why-markdown"},
  "mermaid_failures": [{"file": "<file>", "alt": "<alt text>", "error": "<at most 300 characters>"}],
  "links": {<links report>},
  "linked": "<work/linked.json>",
  "work": "<work folder>"
}
```

`analyze(cfg, work, log, skip_missing=False)` raises `BuildError` without pandoc (or with one older than 3.8) and for an empty reading order. With `skip_missing=True` (used by `check`), missing files are skipped and files are read with invalid UTF-8 replaced; otherwise a missing file or a non-UTF-8 file (`<file> is not valid UTF-8 (byte N); re-save it as UTF-8`) is a `BuildError`.

### build.json

`<out>/reports/build.json`, written at the end of `build()`, and also when it stops with an exception after creating `reports/`. Keys: `gates`, `files`, `links`, `pandoc_warnings`, `epub`, `cover`, `provenance`, `timings`, `ok`, `failed_gates`, `skipped_gates`, `warning_gates`; after an exception, `failed_stage`, `error`, and (when no EPUB was written) `artifact` instead of the keys the build did not reach.

```json
{
  "gates": {
    "charts": {"result": "pass", "charts": 1},
    "links": {"result": "pass", "unresolved": 0, "missing_files": 0},
    "images": {"result": "pass", "problems": []},
    "epubcheck": {"result": "pass", "counts": {}, "messages": []},
    "ace": {"result": "pass", "violations": []},
    "wordcount": {"result": "pass", "worst": 0.0, "failing": [],
                  "files": {"01-why-markdown.md": {"source": 175, "epub": 175, "diff": 0.0}}}
  },
  "files": {"01-why-markdown.md": {"stats": {}, "images": [], "html_removed": [], "external_links": [], "math": []}},
  "links": {"unresolved": [], "fuzzy": []},
  "pandoc_warnings": [],
  "epub": ".../dist/writing-a-book-in-markdown.epub",
  "cover": ".../dist/writing-a-book-in-markdown-cover.jpg",
  "provenance": {"mdbindery": "0.1.1", "python": "3.12.14", "pandoc": "3.11", "epubcheck": "epubcheck-5.4.0",
                 "ace": "1.4.6", "source_revision": "<git commit or null>", "options": {}},
  "timings": {"analysis": 1.9, "epub": 0.6, "epubcheck": 2.8, "ace": 6.1, "wordcount": 0.5},
  "ok": true,
  "failed_gates": [],
  "skipped_gates": [],
  "warning_gates": []
}
```

| Gate | Results and extra keys |
|---|---|
| `charts` | `pass` with `charts` (count); `warn` with `placeholders` when charts exist, `options.mermaid` is `png`, and mermaid-cli is missing; `fail` with `failures` (`{file, alt, error}`) when a chart fails to render |
| `links` | `pass`, or `fail` (`warn` with `strict_links: false`), with `unresolved` and `missing_files` counts |
| `images` | `pass` or `fail`, with `problems`: file-report image entries whose status is not `ok`, plus `file` |
| `includes` | present only on failure: `fail` with `problems` (`{file, directive, error}`) |
| `epubcheck` | `pass` or `fail` with `counts` (severity to count) and `messages` (the first 50 as `{severity, id, message, path, line}`); `fail` with `detail` `EPUBCheck not available` (no Java 11+ or no jar) or `EPUBCheck did not produce a report: ...`; `skipped` with `options.epubcheck: false` |
| `ace` | `pass` or `fail` with `violations` (`{impact, rule, count}`; `rule` is what `ace_waivers` matches); blocking are `critical` and `serious` rules not waived; `warn` with `detail: "Ace not installed"`; `fail` with `detail` (up to 1000 characters of Ace's output) when Ace runs but writes no report; `skipped` with `--no-ace` or `options.ace: false` |
| `wordcount` | `pass` or `fail`, with `worst` (largest absolute `diff` among failing files, else 0), `failing` (file names), and `files` (`{source, epub, diff}` per file, `diff` = `(compared - source) / source` rounded to 4 places; files with cards add `card_labels` and `compared`, otherwise `compared` is `epub`) |

`ok` is true when no gate has `result: "fail"`, and `failed_gates` lists the ones that do; `skipped_gates` and `warning_gates` list the gates at `skipped` and `warn`, so a passing build still shows which checks did not fully run. `failed_stage` is one of `analysis`, `identifier`, `cover`, `epub`, `epubcheck`, `ace`, `wordcount`. `pandoc_warnings` holds pandoc's stderr lines from the EPUB call (for example `Could not convert TeX math`), which are also logged.

The word count: `source_words()` runs `pandoc -f gfm -t plain --wrap=none --lua-filter plaintext.lua` on each prepared file (raw HTML becomes its visible text: tags, comments, scripts, and styles removed, `<img>` alt text kept) and counts words after removing URLs. On the EPUB side, the spine documents are joined without their `<head>`, cut at each file's `h1` identifier in reading order (so any `split_level` works), and reduced to text by `xhtml_text()` (alt text kept, figure captions and MathML annotations removed). For a file with cards, `compared` is the EPUB count minus the words of `card_labels` plus the words of `card_headers` (cards repeat the labels and drop the header row). A file fails when its difference exceeds both `wordcount_tolerance` and `wordcount_min_words`; no file is exempt. The log states the result as a tolerance (`every file within 2% or 25 words of its source`), since equal-length substitutions and moves within a file are invisible to a count.

### check JSON

`mdbindery check --json <file>` writes the keys `target`, `ok`, `counts`, `by_code`, `facts`, and `findings`:

```json
{
  "target": "broken-book",
  "ok": false,
  "counts": {"error": 12, "warning": 9, "info": 4},
  "by_code": [{"code": "MB103", "severity": "error", "count": 1}],
  "facts": {
    "source": ".../broken-book",
    "config": ".../broken-book/mdbindery.yaml",
    "inferred": [],
    "title": "Broken Book",
    "lang": "en-US",
    "files": ["01-intro.md", "02-body.md", "03-latin.md", "04-gone.md"],
    "totals": {"refs": 2, "footnotes": 0, "images": {"inline": 4, "block": 0, "figure": 0, "full-page": 0},
               "charts": 1, "math": 0, "includes": 0}
  },
  "findings": [
    {"severity": "error", "code": "MB200", "file": "01-intro.md", "line": 5,
     "message": "link to missing anchor: 02-body.md#no-such-anchor (link text: the body)",
     "fix": "Point the link at an existing heading (GitHub-style slug) or add <a id=\"...\"></a> there."}
  ]
}
```

`by_code` counts findings per code and severity, sorted by severity and then code. Optional `facts` keys: `github` (`owner`, `repo`, `branch`, `subdir`) for GitHub URLs; `trial_build` with `--build` (`passed (<n> KB)`, `failed: <gates> (<n> KB)`, `failed: <exception>`, or `skipped: fix the errors first`); `suggested_config` (the text `init` would write) when there is no configuration file. `ok` is true when there are no findings with severity `error`. `Report.add()` drops exact duplicates. The Markdown report adds a `Summary` table of counts per code when there are more than 10 findings, and groups more than three findings of one code in one file into one entry with the line list.

## How check reuses analyze()

`check()` first fetches the target (`fetch()`):

- an existing path: used in place (a file that is not a folder is an error);
- `parse_target()` accepts GitHub URLs with or without the scheme or `www.`, optionally with `/tree/<branch>/<folder>` (a `/blob/` URL is an error with a hint), `git@github.com:O/R.git` and `ssh://git@github.com/O/R`, and other git URLs (`https://`, `ssh://`, `git://`, `file://`, `git@...`, `*.git`); a target starting with `-` is rejected;
- a URL is cloned with `git clone --depth 1 --quiet [--branch B] -- <url> <tmp>/repo`, with `GIT_TERMINAL_PROMPT=0` and SSH in `BatchMode`, so git never asks for credentials. Errors become `branch or tag not found: B`, `repository not found or not accessible: ...`, or `git clone failed: ...`;
- without git, a GitHub repository (from an HTTPS or SSH URL) is downloaded as `https://github.com/O/R/archive/<branch>.zip` (the default branch comes from the GitHub API) and extracted after checking that no member leaves the folder; other URLs need git.

After a clone or download, `remove_escaping_symlinks()` walks the checkout without following links and deletes every symlink whose target resolves outside it; `check()` reports each as MB407. The temporary folder is removed on every error and after the check. Progress lines go to stderr. Then `_check()` runs:

1. Load the configuration with the repository name (for any URL, the last part of the URL) as the fallback title. A fetched repository is untrusted (`trusted=False`, `repo_root` = the clone): `source_dir`, `options.css`, `extra_css`, `embed_fonts`, and `cover.image` must stay inside it, and images are contained (`image_root`). A `ConfigError` becomes MB102 (error), and the check stops.
2. Configuration notes: unknown nested keys (MB102 warning), no config (MB101), mdBook layout (MB130), no files (MB100, stop), reading order source (MB125), missing listed files (MB103), unlisted Markdown files in the source folder and `chapters/` (MB104), a toc file in the reading order (MB126), metadata (MB120 to MB124), cover (MB410 to MB412).
3. For a GitHub URL with no `source_url` configured, `source_url` is set in memory to `https://github.com/<owner>/<repo>/blob/<branch>/<book folder>/` (the book folder relative to the clone, `src/` for an mdBook), so links to files outside the book behave as they would in a build with that setting. For a local folder, `Config.suggested_source_url` (from the `origin` remote and branch) is only suggested.
4. Static checks per file, in pure Python: encoding (MB105), includes (MB131, from one `expand_includes()` call whose text the later checks read), YAML front matter (MB111, then blanked, as pandoc drops it), headings (MB106 to MB110), citations and footnotes (MB300 to MB306), images (MB400 to MB406; for an untrusted repository an image outside it is an MB406 error, and so is an image URL of the same repository whose local file resolves outside it), HTML tags (MB500), wide tables (MB600), long code lines (MB720), math count; then MB107 as a book-level note when several files start with the same level-1 heading, and MB710. Lines that the build will drop (`drop_sections`, `drop_lines`) are blanked first with `markdown.mask_dropped()`, so they are not reported and line numbers stay correct. Scanners use `iter_text_lines()`, so code, indented code, and HTML comments are never scanned. The image scan estimates each image's kind by line: an image counts as alone when nothing but `<p>`, `<div>`, `<center>`, or `<picture>` tags surrounds it, and an `<img>` on a line with `<figure>` counts as a figure.
5. If pandoc is available, `analyze(cfg, work, skip_missing=True)` runs in a temporary folder, which `check()` keeps until the end: the same code path as a build, so links resolve exactly as they will in the EPUB. With `--no-render`, or without mermaid-cli, `options.mermaid` is switched from `png` to `placeholder` first, so no browser starts (and MB700 is added when charts exist and mermaid-cli is missing). `analysis_findings()` maps the results: `unresolved` to MB200 and `fuzzy` to MB201 (file from `source`, line found by searching for `#<fragment>`); `external` entries to MB203 (missing, website `source_url`), MB204 (missing otherwise), MB202 warning (`unlinked`), or MB202 note (`source_url` set only in memory); `html_links` to MB205; `html_removed` to MB501; image entries that are not `ok` and not already reported to MB400, MB401, or MB406; suspicious inline math (prose between dollar signs) to MB711; `mermaid_failures` to MB701. A `BuildError` becomes MB903. Without pandoc, a single MB001 warning says that links were not verified.
6. With `--build` and no errors so far, `trial_build()` runs `build(..., analysis=a)` into a temporary output folder, reusing the analysis of step 5, so each file is converted once and each chart rendered once; then the analysis folder is removed. When the configuration has no identifier, it sets a random one in memory first, so a trial build never writes into the configuration file. EPUBCheck messages become MB900 (ERROR and FATAL as errors); Ace violations become MB901 (`critical` and `serious` as errors, others as warnings, rules in `ace_waivers` as notes), and an ace gate at `warn` (Ace not installed) becomes an MB901 warning; a failed word count becomes MB902 (naming up to five files); pandoc's `Could not convert TeX math` warnings become MB711; every failed gate not already covered by an error of its own code becomes MB904; an exception becomes MB903. The trial build uses the check's configuration object, so after `--no-render` its charts are placeholders.

## Tool discovery

`tools.home()` is `MDBINDERY_HOME`, or the per-system default (`%LOCALAPPDATA%\mdbindery`, `~/Library/Application Support/mdbindery`, `$XDG_DATA_HOME/mdbindery` or `~/.local/share/mdbindery`). Tools live in `<home>/tools/`. `tools.find(name)` returns a path or `None`:

| Tool | Where it is looked for | Falls back to `PATH` |
|---|---|---|
| `pandoc` | `tools/pandoc/bin/pandoc[.exe]`, `tools/pandoc/pandoc[.exe]` | Yes, if `pandoc --version` reports 3.8 or newer (`MIN_PANDOC`, needed for `--syntax-highlighting`) |
| `java` | `tools/jre/bin/java[.exe]`, `tools/jre/Contents/Home/bin/java` | Yes (`JAVA_HOME` is not read) |
| `node` | `tools/node/node[.exe]`, `tools/node/bin/node` | Yes |
| `npm` | `npm-cli.js` under `tools/node/node_modules/npm/bin/` or `tools/node/lib/node_modules/npm/bin/` | No |
| `mmdc` | the `mmdc` bin script from `@mermaid-js/mermaid-cli/package.json` in the npm modules folder (`tools/npm/node_modules` on Windows, `tools/npm/lib/node_modules` elsewhere) | No |
| `ace` | the `ace-puppeteer` bin script from `@daisy/ace/package.json` in the same folder | No |
| `epubcheck` | the first `epubcheck.jar` (sorted) anywhere under `tools/epubcheck/` | No |

Lookups are cached per process (`_find()` and `pandoc_version()` under `functools.lru_cache`, keyed by the tool home and `PATH`); `install_all()` calls `tools.clear_cache()` when it finishes. The bundled copy always wins, Java included. `tools.command(name)` returns the argv prefix: `[node, script]` for `mmdc`, `ace`, and `npm`, so npm packages run without Windows `.cmd` shims and no command ever goes through a shell (`build.run()` never uses `shell=True`); `[java, -jar, epubcheck.jar]` for EPUBCheck, only when `java -version` reports 11 or newer (`tools.epubcheck_cmd()`); `[path]` otherwise. mermaid-cli and Ace are never taken from `PATH`, because only the bundled copies are paired with the browser cache. `tools.old_pandoc_on_path()` lets `doctor` mention a pandoc on `PATH` that is too old.

Every external program runs through `tools.run_process(cmd, env, cwd, timeout, tail)`: no shell, stdin closed, output into temporary files rather than pipes (so a chatty tool cannot block on a full pipe), and the child in its own process group (`start_new_session`, or `CREATE_NEW_PROCESS_GROUP` on Windows). On timeout or `KeyboardInterrupt`, `_kill_tree()` stops the whole group (`killpg`, or `taskkill /T /F`); a timeout returns exit code -9 with `(stopped after N s)` in stderr. `tail` keeps only the last N bytes of each stream, for diagnostic output. `tools.deadline(seconds)` scales a limit by `MDBINDERY_TIMEOUT_SCALE`. `build.run()` adds the per-stage limits (Mermaid 180 s, word count 300 s per file, EPUBCheck 1200 s, Ace and the EPUB 1800 s, default 900 s) and turns a timeout into a `BuildError` where the result is needed; the installer, `doctor`, and `preview` use the same runner.

`tools.tool_env()` prepends the Node.js folder to `PATH` and sets `PUPPETEER_CACHE_DIR=<home>/tools/puppeteer`. `tools.ace_env()` adds `PUPPETEER_EXECUTABLE_PATH`: it reads the `chrome-headless-shell` version from Ace's `puppeteer-core/lib/cjs/puppeteer/revisions.js` and points at that build in the cache, so Ace does not need a full Chrome. `preview` uses the first `node_modules/puppeteer` found under the npm modules folder (sorted) through `NODE_PATH`.

Chrome sandbox: `tools.puppeteer_config()` writes `<home>/tools/puppeteer-config.json` for mermaid-cli, with `--no-sandbox --disable-setuid-sandbox` only when `tools.no_sandbox()` is true: `MDBINDERY_NO_SANDBOX` or `CI` is set, the process runs as root, or the marker `<home>/tools/no-sandbox` exists. The Mermaid renderer and `doctor`'s render test retry once without the sandbox when Chrome's output matches `SANDBOX_ERRORS`, and `tools.disable_sandbox()` writes the marker so later runs skip the failing attempt. `preview` retries the same way but never writes the marker: it opens EPUBs that may come from others, so it warns and drops the sandbox for that run only. Its page script also turns JavaScript off and intercepts requests, allowing only `file:` URLs under the extracted EPUB and `data:` URLs. Ace's Puppeteer runner always launches its Chrome without a sandbox; it only loads the EPUB that was just built.

## Installer and pinned versions

Everything is installed in user space, pinned, and checksum-verified before use:

| Component | Version | Where | Names to change |
|---|---|---|---|
| uv | 0.12.19 | `install/install.sh` | `UV_VERSION`; `UV_ASSET` and `UV_SHA` in the four platform lines |
| uv | 0.12.19 | `install/install.ps1` | `$UvVersion`; `$UvAssets` (x64 and arm64) |
| Python for the tool environment | 3.12 | both installers | `--python 3.12` in the `uv tool install` line |
| pandoc | 3.11 | `src/mdbindery/installer.py` | `PANDOC_VERSION`; asset names and SHA-256 in `PANDOC` (Windows arm64 uses the x86-64 build) |
| EPUBCheck | 5.4.0 | `src/mdbindery/installer.py` | `EPUBCHECK_VERSION`, `EPUBCHECK_SHA` |
| Node.js | 24.21.0 | `src/mdbindery/installer.py` | `NODE_VERSION`; asset names and SHA-256 in `NODE` |
| mermaid-cli, Ace | 12.0.0, 1.4.6 | `src/mdbindery/installer.py` | `NPM_PACKAGES` |
| Java runtime | 21 (Eclipse Temurin) | `src/mdbindery/installer.py` | `JRE_MAJOR`; the latest build and its SHA-256 come from the Adoptium API at install time |

The installers fetch uv (unless one is on `PATH`), then run `uv tool install --force --python 3.12` with the local folder (`--local`, `-Local`) or `https://github.com/sagol/mdbindery/archive/<ref>.zip`, so the one-line install needs the repository to be public. uv's state stays in the tool home (`uv/`, `uv-tools/`, `python/`), and uninstalling removes only those folders and `tools/`.

`install_all()` installs pandoc, EPUBCheck, and (in `--java auto` mode only when no Java 11 or newer is found, or with `--force` when a runtime was downloaded before) the Java runtime. Node.js and the npm packages follow unless `--no-node` is given; they are best effort: a failure there is printed as a warning and recorded in `status['notes']['node']`, and the command still succeeds when pandoc and EPUBCheck work (`install-tools` exits 1 only when one of those two is missing, 2 on an installer exception). npm runs with `PUPPETEER_SKIP_DOWNLOAD=1`, `ELECTRON_SKIP_BINARY_DOWNLOAD=1`, and its cache in `<home>/tools/npm-cache`, which is deleted afterwards; then every `node_modules/puppeteer` copy installs the `chrome-headless-shell` build it expects (`puppeteer browsers install chrome-headless-shell`).

Installs are transactional. `_place()` moves an extracted folder to `tools/.staging-<name>`, writes its marker there, and `_swap_in()` renames the current folder to `.old-<name>`, the staged one into place, and runs a check on it (`_runs()`: the binary starts with `--version` or `-version`; EPUBCheck: the jar is there; npm: both packages are installed into the staging prefix). On any failure the old folder comes back; on success it is deleted. `install_all()` holds `tools/.install.lock` (created with `O_EXCL`, treated as abandoned after three hours) for the whole run.

`extract()` refuses archive members whose names leave the target folder, tar symbolic and hard links that point outside it or are absolute, and tar members that are not files, folders, or links; it uses tarfile's `data` filter when Python has it, and restores zip permissions (folders last). Each component gets a `.mdbindery-version` marker (for npm in `tools/npm/`, holding the joined `NPM_PACKAGES` string; for Java the major version). `install-tools` reinstalls a component when its marker differs from the constant, so a version bump reaches users on their next `install-tools` run.

To bump a version:

1. Change the version constant and every asset name that contains it.
2. Download each asset from the official location and compute its SHA-256:

   ```
   V=NEW_VERSION
   for a in pandoc-$V-linux-amd64.tar.gz pandoc-$V-linux-arm64.tar.gz pandoc-$V-arm64-macOS.zip \
            pandoc-$V-x86_64-macOS.zip pandoc-$V-windows-x86_64.zip; do
     curl -fsSL -o "/tmp/$a" "https://github.com/jgm/pandoc/releases/download/$V/$a" && sha256sum "/tmp/$a"
   done
   ```

   The other download locations: `https://github.com/w3c/epubcheck/releases/download/v<version>/epubcheck-<version>.zip`, `https://nodejs.org/dist/v<version>/<asset>` (compare with `SHASUMS256.txt` in the same folder), and `https://github.com/astral-sh/uv/releases/download/<version>/<asset>` for the six uv archives.
3. Check that the archive layout still matches what the installer looks for: `bin/pandoc` (`pandoc.exe` anywhere on Windows), `epubcheck.jar` anywhere in the EPUBCheck folder, `bin/node` (`node.exe`), and `bin/java` (`java.exe`) in the JRE.
4. For pandoc, read the changelog for anything the filters and the build rely on: the `gfm` reader's heading identifiers and alerts, the JSON API version (all files of one build must agree), `pandoc.json`, `pandoc.system.read_file`/`write_file`/`list_directory`, `pandoc.path.exists`, `pandoc.text.lower`, `pandoc.Figure`, and the options `--syntax-highlighting`, `--split-level`, `--epub-cover-image`, `--epub-embed-font`, and `--resource-path`.
5. For mermaid-cli and Ace, check that `tools.command()` still finds the bin scripts in their `package.json`, that `tools.ace_env()` still finds the `chrome-headless-shell` version in Ace's `revisions.js`, and that `preview` still works with the Puppeteer copy it picks.
6. Run `mdbindery install-tools`, `mdbindery doctor`, `MDBINDERY_REQUIRE_TOOLS=1 python -m pytest`, and a build of a copy of `examples/sample-book`. Update the version table and disk sizes in [installation.md](installation.md) and the CHANGELOG.

## Tests

```
pip install -e ".[test]"
mdbindery install-tools          # or set MDBINDERY_HOME to an existing tool home
python -m pytest                 # tests that need a missing tool are skipped
MDBINDERY_REQUIRE_TOOLS=1 python -m pytest   # a missing tool fails those tests instead
```

| File | Covers | Needs tools |
|---|---|---|
| `tests/conftest.py` | Puts `src/` on `sys.path`; defines `FIXTURES`, `EXAMPLES`, the `needs_pandoc` and `needs_epubcheck` skip markers, `HAVE_MMDC`, `validate_if_installed()`, and the `copy_book` fixture | |
| `tests/test_markdown.py` | The pre-pass: the generated reference list and `stats['citations']`, code and blank lines left untouched, numeric and named labels (`citation_labels`), the added References heading, setext References headings, commented-out definitions, URLs in titles, `drop_sections` and `drop_lines`, duplicate definitions, headings in code and comments, `# Learning C#`, block kinds of `split_blocks()`, the linear code-span scan, Mermaid `todayMarker` and alt text, label ids, mdBook includes, hidden Rust lines | No |
| `tests/test_config.py` | Inferred reading order, title, rights, cover, and slug; the `chapters/` folder; language guess; unknown nested and top-level keys; invalid values (parametrized); coercion of scalars; containment for untrusted repositories; reading order from `toc.md` and front and back matter names; numbered names winning over README links; the mdBook layout; license names; an external config with `source_dir`; identifier saving; `starter_yaml()` keeping values and round-tripping | No |
| `tests/test_check_build.py` | `check` on the broken fixture (planted codes, line numbers, both report formats); the sample book with no errors or warnings (MB700 only, when mermaid-cli is missing); a sample build that passes all gates and contains the expected markup (the one test that requires EPUBCheck); byte-identical rebuilds; the Russian book; repair of files without a level-1 heading or with text above it, with `split_level: 2`; `init` output that accepts a saved identifier; `drop_lines` and HTML alt rules in `check`; `check --build` that leaves the configuration unchanged | pandoc; EPUBCheck for the sample-build test |
| `tests/test_regressions.py` | Code, blank lines, math, URLs, HTML in quotes, entities, and endnotes surviving a build; links that leave the book folder; title promotion over anchors and comments; containment of images for untrusted books; literal metadata; `reports/` keeping foreign files; input errors (empty book, non-UTF-8); MB904 for a failed trial gate; comments and indented code in `check`; one-line CLI errors and exit codes; `init --force` backup; same-repository image URLs and text placeholders; `/` links and folder index pages; anchors kept under a `title:` override; image definitions that are not citations; `check` false positives (front matter, code spans, footnotes in quotes, `<YOUR_NAME>`); license, mdBook, and `source_dir` details; `--report` into a new folder; `file:` image URLs and a single MB406 for an image outside a checked repository; an mdBook outside git, `<figure>` images, and `.md` links against a website `source_url`. From the second audit: no reads through symlinks in an untrusted repository (chapters, config, listed files, cover, images, same-repository URLs) and their removal from a fetched checkout; cards that keep header, body, and footer rows with an exact word count, and a lost paragraph in a cards chapter failing; per-image alt text in HTML blocks and the matching summary; `.nan`, `.inf`, and impossible dates; include cycles and depth; `build.json` and `build.log` after a failed build; `check --build` converting each file once; `run_process` stopping a process tree on timeout; a failed tool update keeping the working version; the install lock | pandoc for most; none use EPUBCheck |
| `tests/ci_unicode_paths.py` | Not a pytest file: CI runs it to build the sample book from a folder and a temp folder with non-ASCII names and spaces | pandoc, EPUBCheck |

Fixtures:

- `tests/fixtures/broken-book/`: planted problems for MB102 (a misspelled option), MB103 (a missing listed file), MB105 (a Latin-1 file; CRLF line endings), MB106, MB108, MB200, MB204, MB300, MB301, MB302, MB304, MB400, MB401, MB402, MB403 (a BMP image), MB500 (`<iframe>`, `<script>`), MB600, and MB701 (a broken Mermaid chart).
- `tests/fixtures/ru-book/`: Cyrillic anchors, guillemets, em dashes, footnotes, a named citation label with `citation_labels: all`, a scene break, a Mermaid chart, and an inferred file list; used for the reproducibility test.
- `examples/sample-book/`: the sample book, also built in CI.

`needs_pandoc` and `needs_epubcheck` are `pytest.mark.skipif(...)` objects imported from `conftest`, not registered markers, so `-m` cannot select them; select tests with `-k` or by file. With `MDBINDERY_REQUIRE_TOOLS` set to any non-empty value, they never skip. Tool lookup goes through `tools.find()`, so `MDBINDERY_HOME` decides which tools the tests use. The build tests pass `run_ace=False`, so Ace is not needed; Mermaid charts are rendered when mermaid-cli is installed and become placeholders otherwise. Content tests pass their configuration through `validate_if_installed()`, which turns EPUBCheck off only when it is missing and tools are not required, so a pandoc-only environment runs every content assertion and skips just the EPUBCheck integration test, while CI validates every build.

A build writes into the book (the generated identifier into `mdbindery.yaml`, and `dist/`). Tests therefore never build a book in place: `copy_book` copies a fixture into `tmp_path` (without `dist/`) first. Do the same when you try things by hand.

A new check needs a code, a fix text, an entry in [checking.md](checking.md), and a test (see CONTRIBUTING.md).

## CI

`.github/workflows/ci.yml` runs on every branch push, pull request, and manual dispatch, with read-only `contents` permission and every action pinned to a commit SHA, and the release workflow calls it (`workflow_call`, input `ref`) to test the release tag before publishing. Three jobs:

- `test`, on Ubuntu with Python 3.12 and 3.9, macOS with 3.12, and Windows with 3.12 (45-minute timeout), with `MDBINDERY_REQUIRE_TOOLS=1` and `PYTHONUTF8=1`: `pip install -e ".[test]"`, `mdbindery install-tools`, `mdbindery doctor`, `python -m pytest -v`, `mdbindery build examples/sample-book`, `python tests/ci_unicode_paths.py`, `mdbindery check tests/fixtures/broken-book --json broken.json -q` (must exit with 1), and `mdbindery check "file://$GITHUB_WORKSPACE" --no-render -q --report url-check.md` (must exit with 0 or 1). The sample book's `dist/` is uploaded as an artifact, even when an earlier step failed.
- `installers`, on Ubuntu, macOS, and Windows (30-minute timeout): `install.sh --local . --no-node`, `doctor`, `build examples/sample-book --no-ace` with the installed command, then `install.sh --uninstall` and a check that the command is gone; on Windows the same with `install.ps1 -Local . -NoNode` and `-Uninstall` in PowerShell 7, and `install.ps1 -Local . -NoTools`, `--version`, and `-Uninstall` in Windows PowerShell 5.1.
- `action`, on Ubuntu, macOS, and Windows: the repository's own `action.yml` with `node: 'false'`, then `doctor` and a build of the sample book.

The one-line form (download through `curl | bash` or `irm | iex`) runs in `install-public.yml`, started by the release workflow with the new tag or by hand.

## Release checklist

1. Set `__version__` in `src/mdbindery/__init__.py` (the only place; `pyproject.toml` reads it).
2. Add a CHANGELOG entry.
3. If tool versions changed, follow [the bump procedure](#installer-and-pinned-versions) and update [installation.md](installation.md).
4. Check that [book-structure.md](book-structure.md), [checking.md](checking.md), [configuration.md](configuration.md), and the two skills under `skills/` match the code (rules, check codes, keys, defaults, commands).
5. Locally: `MDBINDERY_REQUIRE_TOOLS=1 python -m pytest`; build a copy of `examples/sample-book` with Ace enabled and get `BUILD OK`; run `mdbindery check tests/fixtures/broken-book` and get exit status 1.
6. Push and wait for the `ci` workflow (tests, installers, and the Action on all systems).
7. Tag the release (`vX.Y.Z`) and push the tag. The `release` workflow builds the wheel and source archive and checks that their version matches the tag. Before anything is published, `verify` runs the whole `ci` workflow on the tag, and `wheel-smoke` installs the built wheel into a fresh virtual environment on Linux, macOS, and Windows, runs `install-tools --no-node`, and builds the sample book. Only when both pass does it create the GitHub release with the packages, both installers, and the CHANGELOG entry as notes. When the repository variable `PUBLISH_PYPI` is `true`, it also publishes the files attached to the GitHub release to PyPI through trusted publishing (the `pypi` environment; the PyPI project trusts `sagol/mdbindery`, workflow `release.yml`). Running the workflow by hand with an existing tag never replaces that release's files, whose checksums the Homebrew formula and PyPI pin; it only publishes what is missing.
8. Update the Homebrew formula in `sagol/homebrew-tap` (`Formula/mdbindery.rb`): the source archive URL from the release and its SHA-256 (`shasum -a 256`). The tap's own CI installs and tests the formula on macOS and Linux.
9. The release workflow then starts `install-public` with the new tag: the one-line installers taken from that tag (with `--ref`/`-Ref`) on Linux, macOS, and Windows, then a check and build of the sample book. Watch it pass. It can also be run by hand for `main` or any tag.
10. Users of the Action pick the new version by changing `uses: sagol/mdbindery@vX.Y.Z`; `install.sh --ref vX.Y.Z` and `install.ps1 -Ref vX.Y.Z` install that tag.

## Known limitations

- Headings with emoji get different anchors from pandoc and from GitHub, so no link to such a heading works in both places.
- Fuzzy anchor matching ignores only ASCII punctuation and whitespace; it cannot repair a link that differs in letters.
- A link or image path starting with `/` means the repository root. For a folder that is not in a git checkout, `/` is the book folder, or for an mdBook the folder with `book.toml`.
- Citations are recognized by link text and URL on the AST, so `[1][]` and an inline `[1](same URL)` also become citations.
- `check` estimates image kinds line by line, so its `Images:` counts can differ from the build for HTML spread over several lines (for example a `<figure>` whose `<img>` is on its own line).
- mdBook preprocessors other than the built-in directives (`include`, `rustdoc_include`, `playground`, `title`) are not run.
- When mermaid-cli is not installed, charts become placeholders and the charts gate only reports `warn`. When Ace is not installed, the ace gate reports `warn`. In both cases the build passes, and `doctor` exits with 0.
- `check --no-render`, or a missing mermaid-cli, also makes the trial build of `check --build` use chart placeholders.
- The word-count gate compares counts per file, so it does not see text that moved within a file or that was replaced by the same number of words, and a loss below the tolerance passes.
- `check` of a private repository needs the user's own git credentials (SSH keys or a credential helper); git is never allowed to prompt. The HTTPS archive fallback without git works only for public GitHub repositories.
- npm packages are pinned by top-level version only, so their dependencies may change between installs. The Java runtime is the latest Temurin 21 build at install time, verified with the checksum the Adoptium API reports. `build.json` records the versions that made each book (`provenance`), but not the npm dependency tree or the browser builds.

## PDF output path

`build(..., output_format="pdf")` reuses `analyze()` and existing source gates, then calls `pdf.render()`. EPUB writer, postprocessing and validation functions retain their behavior. PDF creates one HTML5 document from the resolved Pandoc AST, stages declared assets, adds print CSS and uses Puppeteer `page.pdf()`. `tools.puppeteer_runtime()` shares browser discovery with EPUB preview. No PDF renderer registry or plugin layer.

The optional `pdf` extra supplies pypdf. PDF validation checks actual extracted text against generated HTML text and records page count. Failed text checks retain the PDF for inspection. Renderer failure removes temporary output and preserves the previous PDF. Reports live under `reports/pdf/`, leaving EPUB reports untouched. `tests/test_pdf.py` covers PDF content, Unicode paths, settings, resources, failures and EPUB coexistence. Tests needing browser tools fail rather than skip when `MDBINDERY_REQUIRE_TOOLS=1`.
