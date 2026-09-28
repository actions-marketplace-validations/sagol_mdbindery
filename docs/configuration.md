# Configuration

mdbindery reads its settings from a YAML file named `mdbindery.yaml` (or `mdbindery.yml`). Every key is optional. Without a file, mdbindery infers a configuration from the book folder, and `mdbindery init` writes a starter file from the same inference so you can review and edit it.

This page lists every key, the values each one accepts, and how mdbindery checks them. The rules for the Markdown itself (headings, links, citations, images, tables, charts) are in [book-structure.md](book-structure.md), and the check codes mentioned here are explained in [checking.md](checking.md).

## Where the configuration lives

### In the book repository

The usual place is the root of the book repository, next to the chapters:

```
my-book/
├── mdbindery.yaml
├── README.md
├── 01-first-chapter.md
└── images/
```

Run `mdbindery build` or `mdbindery check` in that folder, or pass the folder as the argument, and they find the file on their own. The build writes to `dist/` inside the same folder.

### Outside the book repository

The configuration can also live in a separate folder, for example when you build someone else's repository, or when you want the book repository to stay free of build files. Set `source_dir` to the book folder, relative to the configuration file:

```
books/
├── my-book/                 # the book repository, not modified
└── my-book-epub/
    ├── mdbindery.yaml       # source_dir: ../my-book
    ├── cover.jpg
    └── dist/                # written by the build
```

```
mdbindery build books/my-book-epub/mdbindery.yaml
mdbindery check books/my-book-epub
```

### How the command line finds the configuration and the book

`mdbindery build` takes an optional `PATH` (a book folder or a configuration file) and an optional `-c FILE`. `mdbindery check` takes a target (a book folder or a repository URL, default `.`; see [checking.md](checking.md#targets)) and an optional `-c FILE`.

| Command | Configuration file | Book folder |
|---|---|---|
| `mdbindery build` | `./mdbindery.yaml`, else `./mdbindery.yml`, else none (inferred) | `source_dir` if set, else `.` |
| `mdbindery build BOOK` | `BOOK/mdbindery.yaml`, else `BOOK/mdbindery.yml`, else none | `source_dir` if set, else `BOOK` |
| `mdbindery build path/to/mdbindery.yaml` | that file | `source_dir` if set, else the file's folder |
| `mdbindery build -c FILE` | `FILE` | `source_dir` if set in `FILE`, else the folder of `FILE` |
| `mdbindery build BOOK -c FILE` | `FILE` | `source_dir` if set in `FILE`, else `BOOK` |
| `mdbindery check` or `mdbindery check BOOK` | as for `build` | as for `build` |
| `mdbindery check -c FILE` | `FILE` | `source_dir` if set in `FILE`, else the current folder |
| `mdbindery check URL -c FILE` | `FILE` | the cloned repository (or its `/tree/BRANCH/FOLDER`) |

Things to know about these rules:

- `source_dir` always wins over `PATH`, and it is relative to the configuration file.
- `check` does not accept a configuration file as its target: `mdbindery check path/to/mdbindery.yaml` stops with `check error: not a folder`. Give the folder that holds the file instead.
- `check -c FILE` without a target checks the current folder, because the target defaults to `.`. `build -c FILE` without a `PATH` uses the folder of `FILE`.
- A configuration used with `check URL -c FILE` must not set `source_dir`, and its other paths must point inside the clone ([Untrusted repositories](#untrusted-repositories)).
- After this lookup, an mdBook layout can move the book folder to the `src` folder named in `book.toml` ([mdBook books](#mdbook-books)).
- A configuration without `source_dir` can be reused for several copies of a book: `mdbindery build checkout-a -c shared.yaml`.
- A missing `-c FILE` is an error: `config error: config file not found: ...`.

### Which folder relative paths use

| Paths | Relative to |
|---|---|
| `source_dir`, `output_dir`, `cover.image` (when set in the file), `options.css`, `options.extra_css`, `options.embed_fonts` | the folder of the configuration file (without a file: the folder given on the command line) |
| `files[].file`, `options.cards.files` | the book folder |
| `cover.image` found by inference | the book folder |
| `-o` on the command line | the current folder |

So if an external configuration sets `cover.image` to a file inside the book repository, write it as `../my-book/images/cover.jpg`. Leaving `cover.image` empty also works, because the inferred cover is looked up in the book folder.

## Minimal configuration

```yaml
metadata:
  title: A Colony on Mars
  authors: [Jane Doe]
  lang: en-US
  identifier:
  rights: CC BY 4.0
```

Everything else is either a default or inferred (see [What is inferred](#what-is-inferred-when-keys-are-missing)). Leave `identifier:` empty on its own line: the first build fills it in (see [The identifier](#the-identifier)).

## Top-level keys

| Key | Type | Default | Allowed values | Meaning |
|---|---|---|---|---|
| `slug` | text | inferred from the title | letters (any script), digits, `.`, `-`, `_`; does not start with `.` or `-`; no `..` | Base name of the output files: `<slug>.epub` and `<slug>-cover.jpg`. |
| `source_dir` | path | the book folder given on the command line, else the configuration file's folder | an existing folder | Folder with the Markdown files, relative to the configuration file. |
| `output_dir` | path | `dist` | any path | Output folder, relative to the configuration file. `mdbindery build -o DIR` overrides it. |
| `source_url` | URL | `""` | starts with `http://` or `https://`; a missing trailing `/` is added | Web address of the online copy of the book folder. See [source_url](#source_url). |
| `metadata` | mapping | see [metadata](#metadata) | | Title, authors, language, identifier, and other publication metadata. |
| `cover` | mapping | see [cover](#cover) | | Cover image, or the colors of the generated cover. |
| `files` | list | inferred | | Reading order and per-file settings. See [files](#files). |
| `options` | mapping | see [options](#options) | | Conversion, layout, and validation settings. |

`output_dir` receives `<slug>.epub`, `<slug>-cover.jpg` (the full-size cover for store uploads), and a `reports/` folder with `build.json`, `build.log`, `epubcheck.json`, and the Ace report in `ace/`. A build replaces only those report files; anything else you keep in `reports/` stays.

### source_url

`source_url` is the web address of the online copy of the book folder. mdbindery uses it for links to files that are not part of the book (a `LICENSE`, source code, data, a Markdown file that is not in the reading order) and for the link under a chart placeholder. It can be one of two kinds:

| Kind | Example | Link to a file that is not in the repository |
|---|---|---|
| GitHub blob URL of the book folder | `https://github.com/you/book/blob/main/`, or `https://github.com/you/repo/blob/main/book/` for a book in a subfolder | error MB204; the build's links gate fails |
| The published website of the book | `https://doc.rust-lang.org/book/` | kept as a web link and not checked: warning MB203, no gate failure |

A URL on `github.com` is treated as the first kind, anything else as a website.

A link's path, taken relative to the book folder, is resolved against `source_url` like a relative URL, and a `#fragment` is kept:

| Link in a chapter | Book folder | `source_url` | Link in the EPUB |
|---|---|---|---|
| `[license](LICENSE)` | repository root | `https://github.com/you/book/blob/main/` | `https://github.com/you/book/blob/main/LICENSE` |
| `[preface](../preface.md)` | `get-started/` | `https://github.com/you/repo/blob/main/get-started/` | `https://github.com/you/repo/blob/main/preface.md` |
| `[license](/LICENSE)` | `get-started/` | `https://github.com/you/repo/blob/main/get-started/` | `https://github.com/you/repo/blob/main/LICENSE` |
| `[code](../src/main.rs#L10)` | `book/` | `https://example.org/book/` | `https://example.org/src/main.rs#L10` |
| `[start](../guide/start.md#intro)` | `book/` | `https://example.org/book/` | `https://example.org/guide/start.html#intro` |
| `[guide](../guide/README.md)` | `book/` | `https://example.org/book/` | `https://example.org/guide/index.html` |

A link that starts with `/` means the [repository root](#the-repository-root). With a website `source_url`, a link to a `.md` file points to the published page: `x.md` becomes `x.html` and `README.md` becomes `index.html`, as mdBook, Jekyll, and GitHub Pages publish them. A GitHub `source_url` keeps `.md`, because GitHub shows the Markdown file.

Without `source_url`, a link to an existing file outside the book is removed and its text kept (warning MB202), because a relative link to a file that is not in the EPUB fails EPUBCheck. A link to a file that does not exist is MB204 in both cases, except for a website `source_url`.

`mdbindery init` fills `source_url` from the git remote when `origin` is on GitHub and a branch is checked out: `https://github.com/OWNER/REPO/blob/BRANCH/` plus the book's subfolder. `mdbindery check` of a GitHub URL computes the same address, uses it while checking, and puts it into the suggested configuration.

## metadata

| Key | Type | Default | Allowed values | Meaning |
|---|---|---|---|---|
| `title` | text | inferred | numbers and dates are read as text (`title: 1984`) | Book title (`dc:title`). |
| `subtitle` | text | `""` | | Subtitle, written as a second `dc:title` of type subtitle and shown on the title page and the generated cover. |
| `authors` | list of text, or one text | `[]` | a single string becomes a one-item list | Authors, each written as `dc:creator` with the author role. |
| `lang` | language tag | `en-US`, or inferred | `en-US`, `ru`, `de`, ...; quote codes YAML reads as booleans (`lang: 'no'`) | Book language (`dc:language`). It drives hyphenation, the reader's dictionary, and the default accessibility summary. |
| `identifier` | text | `""` | `~` and `null` count as empty | Permanent identifier. When empty, the first build generates a `urn:uuid:` and writes it into this key. |
| `date` | `git` or a date | `git` | `git`, `YYYY`, `YYYY-MM`, or `YYYY-MM-DD`, and a real calendar date (`2026-02-30` is an error); unquoted YAML dates are accepted | Publication date (`dc:date`). |
| `rights` | text | `""`, or inferred from a license file | | Rights statement (`dc:rights`), for example `CC BY 4.0` or `© 2026 Jane Doe. All rights reserved.` |
| `publisher` | text | `""` | | Publisher (`dc:publisher`). Omitted when empty. |
| `description` | text | `""` | | Short description (`dc:description`) that stores and reading apps show. Omitted when empty. |
| `subjects` | list of text, or one text | `[]` | | Subjects or keywords (`dc:subject`). |
| `series` | text | `""` | | Series name, written as `belongs-to-collection`. |
| `series_position` | text or number | `""` | | Position in the series (`group-position`). Used only when `series` is set. |

Metadata is written literally: Markdown or HTML in a title or description (`*`, `_`, `<div>`) appears in the book exactly as typed.

`date: git` means the date of the last commit of the git repository that holds the book folder. When the folder is not in a git repository, it is the date of the newest source file.

The timestamps inside the EPUB archive come from the last git commit, else from a fixed `date` in `YYYY-MM-DD` form, else from the newest source file; dates before 1980 become 1980, the earliest date a zip file can store. This is what makes two builds of the same commit byte-identical.

### The identifier

Stores and reading apps use the identifier to recognize a new version of a book they already have, so it must stay the same for the life of the book.

When `metadata.identifier` is empty, `mdbindery build` generates `urn:uuid:<random UUID>` and looks in the configuration file for the first line that consists of `identifier:` followed by nothing, `""`, `''`, `~`, or `null`, optionally with a comment. It writes the value into that line (the comment stays) and logs `generated identifier ... (saved in mdbindery.yaml)`. Commit the changed file.

The value is not saved, and the build log shows `warning: generated identifier ... for this build only`, when:

- there is no configuration file;
- the file has no such line, for example because `identifier` sits inside a one-line mapping such as `metadata: {identifier: ""}`.

In those cases each build gets a new identifier, so stores see a different book and two builds are not byte-identical. The trial build of `mdbindery check --build` uses a temporary identifier and never writes to the configuration.

You can also set the identifier yourself. A value starting with `urn:uuid:` is written with the UUID scheme, and EPUBCheck warns (OPF-085) if the rest is not a valid UUID. Anything else, for example `urn:isbn:9781234567897`, is written as a URI.

## cover

| Key | Type | Default | Allowed values | Meaning |
|---|---|---|---|---|
| `image` | path | `""`, or inferred | an image file; relative to the configuration file when set here | Cover image. JPEG or PNG at 1600x2560 px is best. |
| `embed_height` | whole number (px) | `1000` | 200 to 10000 | Height of the copy embedded in the EPUB. Larger covers are scaled down to this height. |
| `background` | color | `#1d2330` | `#rgb` or `#rrggbb`, in quotes | Background of the generated cover. |
| `foreground` | color | `#f2efe6` | `#rgb` or `#rrggbb`, in quotes | Text color of the generated cover. |
| `accent` | color | `#c8643b` | `#rgb` or `#rrggbb`, in quotes | Color of the horizontal band on the generated cover. |

Write colors in quotes (`background: "#1d2330"`): without them YAML reads everything after `#` as a comment, and the empty value is a configuration error.

The cover image may be in any format Pillow can read. mdbindery applies its EXIF rotation, flattens transparency onto white, and converts it to an RGB JPEG. The full-size copy goes to `<output_dir>/<slug>-cover.jpg` for store uploads, and a copy scaled to `embed_height` goes into the EPUB. Without an image, mdbindery draws a 1600x2560 typographic cover with the title, subtitle, and authors in the three colors. Cover checks are MB410 to MB412; the size rules are in [book-structure.md](book-structure.md#the-cover).

## files

`files` is the reading order. Each entry is either a path or a mapping. Paths are relative to the book folder.

```yaml
files:
  - file: README.md
    role: front
    title: About this book
    drop_sections: [Contributing, License]
  - 01-site-selection.md
  - chapters/02-power.md
  - file: 03-water.md
    mermaid_alt: "Chart: water loop from the ice mine to the greenhouse"
  - file: appendix-a-data.md
    role: appendix
```

| Key | Type | Default | Allowed values | Meaning |
|---|---|---|---|---|
| `file` | path | required | a relative path inside the book folder; `./` and backslashes are normalized; absolute paths and `..` are errors | Markdown file. A plain string entry is the same as `file:` alone. |
| `role` | text | `chapter` | any text; `init` writes `front`, `appendix`, and `back` | Informational label. It does not move the file or change its formatting; the position in `files` decides the order. |
| `title` | text | `""` | | Chapter title. It replaces the text of the file's level-1 heading and keeps that heading's anchor and any `<a id>` anchors inside it, so links to the old heading still work. In a file without a level-1 heading, a heading with this text is inserted at the top. |
| `drop_sections` | list of text, or one text | `[]` | | Headings whose sections are removed, for example `Contributing` in a README. Each is matched against the heading text exactly as written (case-sensitive, any level), and the section runs until the next heading of the same or a higher level. |
| `mermaid_alt` | text | `""` | | Alt text for every Mermaid chart in this file, used as written (no prefix is added). |
| `key` | text | `k00`, `k01`, ... | letters, digits, `_`; unique | Internal prefix of every anchor ID from the file. Leave it unset. |

A file listed twice, two entries with the same `key`, or an entry without `file:` is a configuration error. Any other key in an entry is reported as unknown (a warning, with a "did you mean" hint). A listed file that does not exist is MB103 in `check` and stops the build (`listed file not found`). When a configuration file exists, or the book has a `chapters/` folder, `check` reports each Markdown file that is not listed as MB104.

## options

Options are grouped by topic below. Setting a list option replaces the whole default list; mappings such as `cards` are merged key by key, so `cards: {files: [x.md]}` keeps the default `min_columns` and `title_columns`.

Some rules hold for every option:

- Booleans must be `true` or `false`. YAML also reads unquoted `yes`, `no`, `on`, and `off` as booleans; quoted text such as `"yes"` is an error.
- Numbers must lie in the range given in the tables. Quoted digits (`"2"`) are accepted; whole-number options reject fractions, and every option rejects `.nan` and `.inf` (`options.wordcount_tolerance must be a finite number, not nan`).
- List options (`drop_lines`, `reference_headings`, `embed_fonts`, `ace_waivers`, `cards.files`) must be YAML lists, even with one item.

### Citations and references

| Key | Type | Default | Allowed values | Meaning |
|---|---|---|---|---|
| `citations` | text | `refdefs` | `refdefs`, `none` | Whether Markdown reference definitions (`[1]: URL "Title"`) become a visible reference list. |
| `citation_labels` | text | `numeric` | `numeric`, `all` | Which definition labels count as citations: only numbers (`[1]`), or every label (`[Smith2020]` too) except image definitions. |
| `reference_headings` | list of text | `References`, `Sources`, `Notes`, `Bibliography`, `Works cited`, `Литература`, `Источники`, `Примечания`, `Список литературы` | | Heading texts that mark a file's reference section (exact match, any level). |
| `reference_heading_new` | text | `References` | | Text of the `##` heading added at the end of a file that has citations but none of the `reference_headings` (MB303). |

With `refdefs`, mdbindery builds a list from each file's citation definitions and inserts it directly under the last heading in that file whose text is in `reference_headings` (for an underlined heading, after the underline). Without such a heading, it adds `## References` at the end of the file. Each entry reads `[label] Title. URL`. Numeric labels come first in numeric order, then word labels in the order they are defined. Definitions nobody cites are listed too (MB300 reports them).

A reference link whose text is a citation label and whose URL is that label's definition, such as `[1]` or `[1][]`, becomes a `[1]` link to its list entry. `[text][1]` stays an ordinary link to the URL. Labels that are not citation labels (with `numeric`: `[GitHub]`, `[Smith2020]`) stay ordinary reference links, as on GitHub. In both modes, a definition used by an image (`![alt][label]`, `![label]`) is not a citation and stays out of the list; with `all`, neither is a named label whose URL ends in an image extension (`.png`, `.jpg`, `.svg`, ...). A numeric label pointing to an image file, such as a cited chart, stays a citation. The conversion works on pandoc's document tree, so code blocks, inline code, math, and URLs are never changed. The definition lines stay in the Markdown; pandoc keeps them invisible.

With `none`, no list is built and `[1]` becomes a plain link to its URL, as on GitHub. `check` then skips MB300 to MB303 and MB306.

### Text clean-up

| Key | Type | Default | Allowed values | Meaning |
|---|---|---|---|---|
| `drop_lines` | list of regular expressions | `[]` | valid Python regular expressions | Lines to remove before conversion: every line outside code blocks and HTML comments that matches one of the patterns (searched anywhere in the line). |

Typical uses are badge lines and GitHub navigation lines. Write the patterns in single quotes so that YAML keeps the backslashes:

```yaml
options:
  drop_lines:
    - 'img\.shields\.io'
    - '^\[(Back to contents|Next chapter)\]'
```

Per-file section removal is `drop_sections` under [files](#files). `mdbindery check` applies both: it reads dropped lines and sections as blank lines, so their problems are not reported and the line numbers of the rest stay correct.

### Table of contents and file splitting

| Key | Type | Default | Allowed values | Meaning |
|---|---|---|---|---|
| `toc` | boolean | `true` | | Put a table of contents page into the reading order, after the title page. With `false` the EPUB still has its navigation document, so the reader's contents menu works, but no contents page appears in the text. |
| `toc_depth` | whole number | `2` | 1 to 6 | Heading levels shown in the table of contents and the navigation document. |
| `split_level` | whole number | `1` | 1 to 6 | Heading level at which a new XHTML file starts inside the EPUB. |

The word-count gate compares the whole book in reading order, so any `split_level` works with it.

### Charts

| Key | Type | Default | Allowed values | Meaning |
|---|---|---|---|---|
| `mermaid` | text | `png` | `png`, `placeholder`, `keep` | What happens to ```` ```mermaid ```` blocks. |
| `mermaid_scale` | number | `2` | 0.5 to 8 | Scale factor passed to mermaid-cli (`-s`). 2 gives images at twice the layout size, sharp on high-density screens. |
| `mermaid_theme` | text | `neutral` | `default`, `neutral`, `dark`, `forest`, `base` | Mermaid theme. `neutral` is grayscale and reads well on e-ink. |
| `mermaid_font_size` | whole number (px) | `18` | 6 to 72 | Font size of chart text. |
| `mermaid_alt_prefix` | text | `Chart` | | First part of generated alt text. Set it in the book's language (`Схема`, `Diagramm`). |
| `mermaid_today_marker` | boolean | `false` | | With `false`, a Gantt chart without a `todayMarker` line gets `todayMarker off`, so the image does not depend on the build date. `true` leaves Gantt charts unchanged. |

The three `mermaid` modes:

- `png` renders each chart to a PNG with mermaid-cli, on a white background. If mermaid-cli is not installed, charts become placeholders, the charts gate reports `warn`, and the build still passes (`mdbindery check` reports MB700). A chart that fails to render also becomes a placeholder, and that fails the charts gate (MB701).
- `placeholder` replaces each chart with a quote that holds its alt text, followed by "This chart is available in the online edition" and, when `source_url` is set, a link to the chapter's source file.
- `keep` leaves the block in the book as a code listing.

Generated alt text is `<prefix>: <title>` when the chart has a `title` line (or `title:` in its front matter), otherwise `<prefix>: <node labels>` (up to 300 characters), otherwise the prefix alone. `mermaid_alt` on a file entry replaces it.

### Tables

| Key | Type | Default | Allowed values | Meaning |
|---|---|---|---|---|
| `cards.files` | list of paths | `[]` | paths as in `files` (normalized the same way) | Files whose wide tables are rendered as cards: one block per row, each value labeled with its column header. |
| `cards.min_columns` | whole number | `9` | 1 to 100 | In those files, tables with at least this many columns become cards; narrower tables stay tables. |
| `cards.title_columns` | whole number | `1` | 1 to 20 | Number of leading columns joined with ": " to form each card's heading. |
| `wide_table_warn` | whole number | `9` | 2 to 100 | Column count from which `mdbindery check` reports a table as too wide (MB600) and the build log lists it, for files not in `cards.files`. |

`<a id>` anchors in a row's first cell move to the card, so links to table rows keep working. Files in `cards.files` are counted by the word-count gate but never fail it, because the column labels add words, and MB600 is not reported for them.

### Styling

| Key | Type | Default | Allowed values | Meaning |
|---|---|---|---|---|
| `css` | path | `""` (the built-in `epub.css`) | an existing file | Stylesheet that replaces the built-in one. |
| `extra_css` | path | `""` | an existing file | Stylesheet appended after the main one, for adjusting a few rules. |
| `embed_fonts` | list of paths | `[]` | existing files | Font files to embed in the EPUB. |
| `highlight_style` | text | `monochrome` | `pygments`, `tango`, `espresso`, `zenburn`, `kate`, `monochrome`, `breezedark`, `haddock`, or `none` | Code highlighting style, passed to pandoc as `--syntax-highlighting`. An empty value means `none`. |

The three path keys are relative to the configuration file, and a missing file is a configuration error (`options.css: file not found: ...`). `highlight_style` must consist of letters, digits, `-`, and `_`; a name pandoc does not know passes that test and then stops the build (`Unknown highlight-style`).

Embedded fonts end up in the EPUB's `fonts/` folder; refer to them from `extra_css`:

```css
@font-face { font-family: "Literata"; src: url("../fonts/Literata-Regular.ttf"); }
body { font-family: "Literata", serif; }
```

Colored highlight styles can fail Ace's contrast check; `monochrome` passes it and reads well on e-ink.

### Validation gates

| Key | Type | Default | Allowed values | Meaning |
|---|---|---|---|---|
| `strict_links` | boolean | `true` | | A link to a missing anchor or a missing file fails the links gate. With `false` the gate reports `warn` and the build succeeds; a link to a missing anchor then points to the top of the target chapter. |
| `wordcount_tolerance` | number | `0.02` | 0 to 1 | Largest relative difference allowed between the words in a source file and in its part of the EPUB (0.02 is 2%). |
| `wordcount_min_words` | whole number | `25` | 0 to 100000 | A file fails the word-count gate only when the difference is also larger than this many words, so short files do not fail over a few words. |
| `epubcheck` | boolean | `true` | | Run EPUBCheck. If it cannot run (no Java 11+, not installed, or no report), the gate fails. With `false` the gate is skipped and the EPUB is not validated. |
| `ace` | boolean | `true` | | Run the DAISY Ace accessibility check. `mdbindery build --no-ace` also skips it. If Ace is not installed the gate reports `warn`; if it is installed but produces no report, the gate fails. |
| `ace_waivers` | list of text | `[]` | Ace rule names | Rules whose critical or serious violations do not fail the build, for example `color-contrast`. Use the names shown in the build log or in MB901 messages. |

`mdbindery check` reports MB200 and MB204 as errors whatever `strict_links` says. Its trial build applies `ace_waivers`: a waived violation appears as a note.

### Accessibility metadata

| Key | Type | Default | Meaning |
|---|---|---|---|
| `accessibility_summary` | text | a built-in sentence in English or Russian | Written as `schema:accessibilitySummary`. |
| `conformance_claim` | text | `""` | When set, written as `dcterms:conformsTo`, for example `EPUB Accessibility 1.1 - WCAG 2.2 Level AA`. |

The built-in English summary is: "This publication has a navigable table of contents and a logical reading order; headings, lists, and tables are marked up structurally", and its ending follows the book: ", and images carry text alternatives." when every image has alt text, "; some images have no text alternative." when some do not, and a plain full stop for a book without images. So the summary never claims more than the `alternativeText` feature does. The Russian one is used when `metadata.lang` starts with `ru`; every other language gets the English text, so write your own summary for books in other languages. Set `conformance_claim` only after the book has actually been evaluated against the standard you name.

mdbindery adds the other schema.org accessibility properties itself: access mode `textual`, plus `visual` when the book has images (rendered charts count); the features `tableOfContents`, `readingOrder`, and `structuralNavigation`, plus `alternativeText` only when every image has alt text; and hazard `none`.

## What is inferred when keys are missing

| Value | How it is inferred | Reported by `mdbindery check` |
|---|---|---|
| Configuration | No `mdbindery.yaml` or `mdbindery.yml`: everything below is inferred and the defaults apply. | MB101 |
| Book folder | An mdBook layout moves it to the `src` folder of `book.toml` ([mdBook books](#mdbook-books)). | MB130 |
| `files` | Only when `files` is empty or missing; see [Reading order](#reading-order). | MB125 says where the order came from |
| `metadata.title` | The `title` in `book.toml`. Else the first level-1 heading (`#`, an `===` underline, or `<h1>`) of `README.md` if it is in the reading order, else of the first file. Else, for `check` of a repository URL, the repository name from the URL. Else the name of the book folder. | MB120 (not for a title from `book.toml`) |
| `metadata.authors`, `metadata.description` | `authors` and `description` in `book.toml`. | not reported |
| `metadata.lang` | Only when the configuration has no `lang` key at all. The `language` in `book.toml`; else `ru` if more than 30% of the letters in the first 4000 characters of each of the first three files are Cyrillic; else `en-US`. | MB122 |
| `metadata.rights` | A license file in the book folder, then at the repository root when the book sits in a subfolder; see [License detection](#license-detection). | MB123 when nothing is found |
| `cover.image` | The first existing `cover.jpg`, `cover.jpeg`, or `cover.png` in the book folder, then in its `images/`, `image/`, `img/`, `assets/`, `media/`, `figures/`, and `cover/` subfolders. | MB410 when nothing is found |
| `slug` | The title in lowercase, with every run of characters other than letters and digits turned into one hyphen. Letters of every script are kept, so a Russian title gives a Cyrillic slug; a title with no letters or digits gives `book`. | not reported |
| `metadata.identifier` | Generated at build time (see [The identifier](#the-identifier)). | MB124 |
| `options.accessibility_summary` | The built-in text for the book's language. | not reported |

Inferred values appear in `facts.inferred` of the JSON report ([checking.md](checking.md#json-report)). A report on a folder without a configuration file also contains a suggested `mdbindery.yaml` built from these values.

### Reading order

When `files` is missing or empty, mdbindery builds the reading order from the Markdown files in `chapters/` if that folder exists, else from the book folder itself (subfolders are not searched). It leaves out `README.md` (it is placed separately) and repository files whose name, without `.md` and in any letter case, is one of: `changelog`, `contributing`, `code_of_conduct`, `code-of-conduct`, `security`, `license`, `licence`, `authors`, `support`, `governance`, `citation`, `funding`, `pull_request_template`, `issue_template`, `maintainers`, `codeowners`, `summary`, `toc`, `contents`, `table-of-contents`, `table_of_contents`.

The order comes from the first of these that applies:

1. A table of contents in the book folder: `SUMMARY.md` with at least one link, or `toc.md`, `TOC.md`, `contents.md`, `CONTENTS.md`, or `table-of-contents.md` with at least two links to existing `.md` files inside the book folder (subfolders included). The files follow in link order and the table of contents itself is left out. With `SUMMARY.md` the book contains only the listed files, as in mdBook, and `README.md` only if `SUMMARY.md` lists it. With the other names, links to `README.md` are ignored and the remaining files follow in file-name order.
2. The links in `README.md` (found in any letter case), when they point to at least two of the files and to at least half of them. The remaining files follow in file-name order. This step is skipped when the chapter files are all numbered (at least two chapter files, each name starting with a digit; front matter, back matter, and appendix names do not count), because numbered names already give the order.
3. File names.

Without a `SUMMARY.md`, `README.md` always comes first.

File-name order puts files that start with a digit in natural order (`2-...` before `10-...`). Files without a number are grouped by name: front matter goes before the chapters, appendices after them, back matter last, and every other unnumbered file sorts with the chapters, after the numbered ones.

| Group | File names (without `.md`, any letter case) |
|---|---|
| Front matter, in this order | `title-page`, `titlepage`, `half-title`, `dedication`, `epigraph`, `foreword`, `preface`, `prologue`, `introduction`, `intro`, `посвящение`, `предисловие`, `пролог`, `введение` |
| Appendices | any name that contains `appendix` or `приложение`, or `ap`/`app` followed by one letter from `a` to `h`, alone or before `-`, `_`, a space, or `.` (`apA`, `app-b`, `apC-data`; `api` and `ap1` are chapters) |
| Back matter, in this order | `afterword`, `epilogue`, `conclusion`, `glossary`, `bibliography`, `references`, `acknowledgments`, `acknowledgements`, `about-the-author`, `about-the-authors`, `colophon`, `index`, `послесловие`, `эпилог`, `заключение`, `глоссарий`, `библиография`, `благодарности` |

A name matches a front or back matter word when it is that word or starts with it followed by `-` or `_` (`preface-2.md`). Numbered files are always chapters: `01-preface.md` keeps its numeric place.

MB125 names the source of the order, and `mdbindery init` writes it as a comment above `files:`. MB126 warns when one of the table-of-contents files is listed in `files:`, because the EPUB has its own table of contents.

### License detection

mdbindery reads the first 6000 characters of `LICENSE`, `LICENSE.md`, `LICENSE.txt`, `LICENCE`, `LICENCE.md`, `COPYING`, or `COPYING.md`, first in the book folder, then at the repository root. The first file with a recognized license sets `rights`:

- An `SPDX-License-Identifier:` line wins. Creative Commons identifiers are shown readably (`CC-BY-4.0` becomes `CC BY 4.0`, `CC0-1.0` becomes `CC0 1.0`); other identifiers are used as written (`MIT`).
- Otherwise the text is matched: CC BY, CC BY-SA, CC BY-NC, CC BY-NC-SA, CC BY-NC-ND, and CC BY-ND with the version found in the text (`CC BY-SA 3.0`; 4.0 when none is found), CC0 1.0, GNU GPL, GNU LGPL, GNU AGPL, GNU FDL, MIT License, Apache License 2.0, BSD License, MPL 2.0, and The Unlicense.

## mdBook books

mdbindery recognizes an [mdBook](https://rust-lang.github.io/mdBook/) project in two ways:

- the folder has a `book.toml`, and the folder named by its `src` key (default `src`) has a `SUMMARY.md`: that folder becomes the book folder;
- the book folder has a `SUMMARY.md`, and `book.toml` is one level up.

`check` reports MB130. The reading order comes from `SUMMARY.md`, and files not listed there are not part of the book. `title`, `authors`, `description`, and `language` from `[book]` in `book.toml` fill the matching `metadata` keys that the configuration does not set. The configuration and `dist/` live next to `book.toml`, as `mdbindery init` writes them. Outside a git checkout, the folder with `book.toml` is the [repository root](#the-repository-root), so `{{#include ../listings/x.rs}}` in a chapter under `src/` works in a plain folder too.

A `SUMMARY.md` without any `book.toml` (GitBook and similar tools) only sets the [reading order](#reading-order): there is no MB130, and Rust code blocks stay as written.

With an external configuration, `source_dir` can point at either folder: the one with `book.toml` or its `src` folder.

mdBook's `{{#include}}` directives and hidden Rust lines are covered in [book-structure.md](book-structure.md#mdbook-books). Other mdBook preprocessors are not run.

## The repository root

`/` at the start of a link or image path means the repository root: the top of the git checkout that contains the book, as on GitHub. For `check` of a URL it is the cloned repository. For a folder that is not in a git checkout, it is the book folder, or for an mdBook the folder with `book.toml`. mdBook `{{#include}}` paths must stay inside the repository root, and a license file there is used when the book folder has none.

## Untrusted repositories

When `mdbindery check` fetches a repository by URL, it treats the clone as untrusted, so the repository cannot make mdbindery read files elsewhere on your machine:

| Path | Rule | When broken |
|---|---|---|
| `source_dir` | must stay inside the repository | MB102 error |
| `options.css`, `options.extra_css`, `options.embed_fonts`, `cover.image` | must be files inside the repository | MB102 error |
| Images in the chapters | must stay inside the repository (`../../x.png` must not climb out of it) | MB406 error |

These rules also apply to a configuration given with `check URL -c FILE`. Its paths are relative to the folder of `FILE`, so a stylesheet, font, or cover kept next to `FILE` is rejected. For books on your own disk, paths may point anywhere; an image outside the book folder gets only an MB406 warning.

## Validation of the configuration file

These problems stop `mdbindery build` with `config error: ...` and exit code 2, and appear in `mdbindery check` as MB102 errors (exit code 1):

- the file given with `-c` does not exist;
- the file is not UTF-8 text, is not valid YAML, or its top level is not a mapping;
- an unknown top-level key;
- `metadata`, `cover`, `options`, or `options.cards` is not a mapping (a section whose lines are all commented out counts as empty and is rejected too; delete the section line);
- a value of the wrong type or outside its range, as listed in the tables above;
- `files` is not a list, or an entry breaks the rules under [files](#files);
- a file named in `options.css`, `options.extra_css`, or `options.embed_fonts` does not exist;
- the book folder does not exist (`source folder not found: ...`);
- a path breaks the rules for [untrusted repositories](#untrusted-repositories).

YAML errors name the file, the line, and the column:

```
config error: invalid YAML in mdbindery.yaml, line 2, column 1: expected ',' or '}', but got '<stream end>'
```

An unknown top-level key is an error, because a typo there would silently drop a whole section:

```
config error: unknown top-level key "metdata" (did you mean "metadata"?): its settings would be ignored
```

Unknown keys below the top level (`metadata.tittle`, `options.toc_dept`, an unknown key in a `files` entry) are warnings. The build prints them as `config warning:` lines, and `check` reports them as MB102 warnings:

```
config warning: unknown config key: options.toc_dept (did you mean "toc_depth"?)
```

Messages for wrong values name the key. Some examples, as `check` prints them:

| Value in the file | Message |
|---|---|
| `title: yes` | `metadata.title must be text, not true (put it in quotes)` |
| `lang: no` | `metadata.lang must be a language code in quotes, e.g. lang: 'no' (YAML reads no as false)` |
| `date: 26.09.2026` | `metadata.date must be 'git' or a date like 2026-09-26` |
| `toc_depth: 9` | `options.toc_depth must be between 1 and 6` |
| `toc_depth: two` | `options.toc_depth must be a number, not 'two'` |
| `toc_depth: 2.5` | `options.toc_depth must be a whole number` |
| `toc: "yes"` | `options.toc must be true or false` |
| `drop_lines: "x"` | `options.drop_lines must be a list` |
| `drop_lines: ['([']` | `options.drop_lines: invalid pattern '([': unterminated character set at position 1` |
| `background: red` | `cover.background must be a color like #1d2330` |
| `mermaid_theme: pink` | `options.mermaid_theme must be one of: default, neutral, dark, forest, base` |
| `citation_labels: words` | `options.citation_labels must be 'numeric' or 'all'` |
| `slug: "my book"` | `slug may use letters, digits, dots, hyphens, and underscores only (it names the EPUB file)` |
| `source_url: github.com/x/y` | `source_url must start with https://` |
| `files: [../x.md]` | `files entry ../x.md: use a path relative to the book folder (no absolute paths, no ..; set source_dir instead)` |
| `files: [a.md, a.md]` | `file listed twice in files: ['a.md']` |
| `css: missing.css` | `options.css: file not found: missing.css` |

## mdbindery init

`mdbindery init [PATH]` writes `mdbindery.yaml` into the book folder (default `.`) from the same inference as above:

```
$ mdbindery init
wrote .../my-book/mdbindery.yaml (reading order from file names)
review the title, authors, and file order, then run: mdbindery check .
```

The file contains `slug`, `output_dir`, `source_url` (from a GitHub `origin` remote and the current branch, plus the book's subfolder; empty otherwise), the metadata (title, subtitle, authors, a quoted `lang`, date, rights, description), a bare `identifier:` line with the comment above it, `cover.image`, the reading order with a comment saying where it came from, and `options` with `citations: refdefs` and `toc_depth: 2`.

| Situation | What `init` does | Exit code |
|---|---|---|
| The folder does not exist | `init error: folder not found: ...` | 2 |
| No Markdown files in the folder or in `chapters/` | `init error: no Markdown files in ... (or in chapters/): nothing to put in the book` | 1 |
| `mdbindery.yaml` exists | refuses: `... already exists (use --force to rewrite it; a backup is kept)` | 1 |
| `mdbindery.yaml` exists, `--force` | rewrites it and saves the old file as `mdbindery.yaml.bak` | 0 |
| The existing file cannot be loaded, `--force` | prints a warning and writes a fresh file from inference (the old one is still saved as `.bak`) | 0 |

With `--force`, values from the existing file are kept: `slug`, `source_dir`, `output_dir`, `source_url`, every metadata key including `identifier`, the cover settings, the `files` list with its per-file settings (including custom `key` values), and `options`. Comments in the old file are not carried over; they remain in `mdbindery.yaml.bak`.

## Example: configuration in the book repository

A book repository on GitHub, with the configuration in its root:

```yaml
# mdbindery.yaml, in the root of the book repository
slug: a-colony-on-mars
output_dir: dist
source_url: https://github.com/you/mars-colony/blob/main/

metadata:
  title: A Colony on Mars
  subtitle: Power, water, and people for the first thousand days
  authors: [Jane Doe]
  lang: en-US
  # empty on purpose: the first build writes a permanent urn:uuid here
  identifier:
  date: git
  rights: Text licensed under CC BY 4.0
  description: How a first settlement on Mars could get its power, water, and food.
  subjects: [Mars, Space colonization, Engineering]

cover:
  image: images/cover.jpg

files:
  - file: README.md
    role: front
    title: About this book
    drop_sections: [Contributing, How to build]
  - 01-site-selection.md
  - 02-power.md
  - file: 03-water.md
    mermaid_alt: "Chart: water loop from the ice mine to the greenhouse"
  - 04-people.md
  - file: appendix-a-data.md
    role: appendix
  - file: appendix-b-glossary.md
    role: appendix

options:
  citations: refdefs
  drop_lines:
    - 'img\.shields\.io'
    - '^\[Back to contents\]'
  toc_depth: 2
  cards:
    files: [appendix-a-data.md]
    title_columns: 2
  highlight_style: monochrome
  ace_waivers: []
```

Run from the repository root:

```
mdbindery check . --build
mdbindery build          # dist/a-colony-on-mars.epub
```

## Example: external configuration with source_dir

The book repository stays untouched; the configuration, a store-specific cover, a font, and the output live next to it:

```
books/
├── mars-colony/                   # clone of the book repository
│   ├── README.md
│   ├── 01-site-selection.md
│   ├── ...
│   └── images/
└── mars-colony-epub/
    ├── mdbindery.yaml             # the file below
    ├── cover-ebook.jpg
    ├── ebook.css
    ├── fonts/Literata-Regular.ttf
    └── dist/                      # written by the build
```

```yaml
# books/mars-colony-epub/mdbindery.yaml
source_dir: ../mars-colony          # relative to this file
output_dir: dist                    # books/mars-colony-epub/dist
slug: a-colony-on-mars
source_url: https://github.com/you/mars-colony/blob/main/

metadata:
  title: A Colony on Mars
  subtitle: Power, water, and people for the first thousand days
  authors: [Jane Doe]
  lang: en-US
  identifier: urn:uuid:5b2f6c1e-3d4a-4f8b-9e0c-7a1d2b3c4e5f
  date: 2026-09-01
  rights: © 2026 Jane Doe. All rights reserved.
  publisher: Example Press
  series: Frontier Engineering
  series_position: 2

cover:
  image: cover-ebook.jpg            # relative to this file, not to source_dir

files:                              # relative to source_dir
  - file: README.md
    title: About this book
    drop_sections: [Contributing]
  - 01-site-selection.md
  - 02-power.md
  - 03-water.md
  - 04-people.md
  - file: appendix-a-data.md
    role: appendix

options:
  drop_lines:
    - 'img\.shields\.io'
  cards:
    files: [appendix-a-data.md]
  extra_css: ebook.css              # relative to this file
  embed_fonts: [fonts/Literata-Regular.ttf]
  accessibility_summary: >-
    This publication has a navigable table of contents and a logical reading order;
    headings, lists, and tables are marked up structurally, and images carry text alternatives.
```

Any of these commands checks or builds it; the EPUB lands in `books/mars-colony-epub/dist/`:

```
mdbindery check books/mars-colony-epub
mdbindery build books/mars-colony-epub/mdbindery.yaml
cd books/mars-colony-epub && mdbindery build
```

If the identifier is left empty here, the build writes it into this external file, not into the book repository.

## PDF page settings

`options.pdf` applies only to `build --format pdf`. Defaults: `page_size: A4`, `margin_mm: 20`, `page_numbers: true`. Page sizes: `A4` or `Letter`; margins: 10 to 40 mm. See [PDF export](pdf.md) for examples, font handling and validation limits. EPUB remains the default output.
