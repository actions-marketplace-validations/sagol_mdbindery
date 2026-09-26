# Book structure rules

These rules describe a Markdown repository that mdbindery turns into a correct EPUB without manual fixes. They also keep the book readable on GitHub, so the same files serve both. Run `mdbindery check` at any time to see which rules a repository breaks.

Each rule gives the reason and, where it matters, the check code that reports it (see [checking.md](checking.md)). Settings mentioned here are described in [configuration.md](configuration.md).

## 1. Repository layout

```
my-book/
├── mdbindery.yaml          # configuration (recommended)
├── README.md               # front matter: what the book is (optional)
├── preface.md              # front matter, placed before the chapters
├── 01-first-chapter.md     # chapters, numbered in reading order
├── 02-second-chapter.md
├── ...
├── appendix-a-glossary.md  # appendices after the chapters
├── images/                 # every image the book uses
│   ├── cover.jpg           # the cover, 1600x2560 px
│   └── ...
└── LICENSE                 # the book's license
```

- Chapters are `.md` files in the book folder, or in a `chapters/` folder (then only `chapters/` is searched, and `README.md` still comes from the book folder). One chapter per file. Files in other subfolders are included only when `files:` or a table-of-contents file lists them.
- Repository files are not part of the book and are skipped by name: `CHANGELOG`, `CONTRIBUTING`, `CODE_OF_CONDUCT`, `SECURITY`, `LICENSE`, `AUTHORS`, `SUPPORT`, `GOVERNANCE`, `CITATION`, `FUNDING`, `MAINTAINERS`, `CODEOWNERS`, issue and pull request templates, and table-of-contents files (`SUMMARY`, `toc`, `contents`, `table-of-contents`).
- File names with lowercase letters, digits, and hyphens are easiest to link (`03-site-selection.md`). Spaces work but must be written as `%20` in links.
- Save files as UTF-8. A byte order mark is removed and Windows line endings are handled; a file that is not valid UTF-8 stops the build (MB105).

### Reading order

| Rule, first that applies | Order |
|---|---|
| `files:` in `mdbindery.yaml` | exactly as listed |
| `SUMMARY.md` with at least one link, or another table-of-contents file (`toc.md`, `TOC.md`, `contents.md`, `CONTENTS.md`, `table-of-contents.md`) with at least two links to chapter files | the link order; with `SUMMARY.md`, unlisted files (`README.md` too) are left out; with the other files, unlisted chapters follow by name |
| Chapter files that are not all numbered, and a `README.md` that links to at least two of them and at least half | the README's link order, then the other files by name |
| Otherwise | by file name (below) |

`README.md` comes first unless the order comes from `SUMMARY.md`. By file name, the order is: `README.md`, front matter, numbered chapters in natural order (`2-...` before `10-...`), other unnumbered files, appendices, back matter. The front, appendix, and back matter names are in [section 2](#2-front-matter-and-appendices).

Give chapter files a zero-padded number prefix (`01-`, `02-`): GitHub then lists them in the same order, and when every chapter file is numbered, the numbers win over the order of links in the README. `mdbindery check` says which rule it used (MB125), and `mdbindery init` writes the result into `files:` for you to review.

### mdBook books

An [mdBook](https://rust-lang.github.io/mdBook/) project works as it is (MB130):

- `book.toml` next to a `src/` folder with `SUMMARY.md` (or the folder named by `src` in `book.toml`): `src/` is the book folder. Put `mdbindery.yaml` next to `book.toml`; an external configuration's `source_dir` may point at either folder.
- The reading order comes from `SUMMARY.md`; files it does not list, `README.md` included, are not part of the book.
- `title`, `authors`, `description`, and `language` come from `book.toml` unless the configuration sets them.
- Links to `chapter.html` resolve to `chapter.md`, and `folder/index.html` to `folder/README.md` (MB205).
- In Rust code blocks, lines starting with `# ` are hidden and `##` becomes `#`, as mdBook does.
- Other mdBook preprocessors are not run.

A `SUMMARY.md` without any `book.toml` (GitBook and similar tools) only sets the reading order: there is no MB130, and Rust code blocks stay as written.

These directives are expanded in every file, mdBook or not:

| Directive | Inserts |
|---|---|
| `{{#include path}}` | the whole file |
| `{{#include path:N}}` | line N |
| `{{#include path:N:M}}`, `path:N:`, `path::M` | lines N to M, N to the end, the start to M (1-based) |
| `{{#include path:name}}` | the lines between `ANCHOR: name` and `ANCHOR_END: name` |
| `{{#rustdoc_include ...}}` | the same as `{{#include ...}}` |
| `{{#playground path}}` | the whole file |
| `{{#title ...}}` | nothing (removed) |
| `\{{#include ...}}` | the directive as literal text |

Paths are relative to the Markdown file and must stay inside the repository: the git checkout that contains the book. Outside git, the limit is the book folder, or for an mdBook the folder with `book.toml`, so `{{#include ../listings/x.rs}}` from `src/` works in a plain folder too. A missing file or anchor is an MB131 error in `check` and fails the build's `includes` gate.

## 2. Front matter and appendices

- `README.md` is usually written for GitHub visitors. In the book it becomes the opening section. Rename its heading with `title:` (for example "About this book") and remove repository-only sections with `drop_sections:` (for example "Contributing"). Both are set per file in `mdbindery.yaml`.
- Without `files:`, unnumbered files are placed by name (any letter case; a name also matches when the word is followed by `-` or `_`, as in `preface-2.md`):

| Placement | Names |
|---|---|
| Front matter, before the chapters, in this order | `title-page`, `titlepage`, `half-title`, `dedication`, `epigraph`, `foreword`, `preface`, `prologue`, `introduction`, `intro`, `посвящение`, `предисловие`, `пролог`, `введение` |
| Appendices, after the chapters | a name containing `appendix` or `приложение`; `ap` or `app` plus one letter from `a` to `h` (`apA`, `app-b`, `apC-data`; `api` is a chapter) |
| Back matter, last, in this order | `afterword`, `epilogue`, `conclusion`, `glossary`, `bibliography`, `references`, `acknowledgments`, `acknowledgements`, `about-the-author`, `about-the-authors`, `colophon`, `index`, `послесловие`, `эпилог`, `заключение`, `глоссарий`, `библиография`, `благодарности` |

- A numbered file is always a chapter: `01-preface.md` stays in numeric order.
- `role: appendix` in `files:` is only a label; the position in `files:` decides the order.
- The title page and table of contents are generated from the metadata and headings. Do not write them by hand; a table-of-contents file listed in `files:` gets MB126.

## 3. Headings

Each chapter file starts with exactly one level-1 heading: `# 3. Power`. It becomes the chapter title in the table of contents and starts a new file inside the EPUB. Sections use `##`, subsections `###`.

When a file breaks this rule, the build still produces a valid book:

| Situation | What the build does | Code |
|---|---|---|
| No `#`, `title:` set for the file | inserts a level-1 heading with that title at the top | none |
| No `#`, the file starts with a heading (anchors and comments above it are fine) | promotes that heading to level 1 and moves the file's other headings up by the same number of levels, but never above `##` (a closing `## Summary` stays inside the chapter) | MB106 |
| No `#`, text before the first heading, or no headings | makes a title from the file name: number prefix removed, hyphens and underscores become spaces, first letter capitalized (`03-site-selection.md` becomes "Site selection"); `README.md` gets the book title | MB106 |
| Content above the `#` heading (badges, logos, text) | moves it below the heading | MB110 |
| Several `#` headings | each starts a new EPUB file and table-of-contents entry | MB107 |
| A skipped level (`##` straight to `####`) | nothing; screen readers and the table of contents rely on the hierarchy, so fix it | MB108 |
| YAML front matter (`---` block) at the top | ignores it and leaves it out of the book | MB111 |
| An empty file | a chapter with only a title made from the file name | MB109 |

- Underlined headings (`===` for level 1, `---` for level 2) and HTML `<h1>` to `<h6>` lines count as headings.
- `title:` in `files:` replaces the text of the `#` heading and keeps its anchor, and any `<a id>` anchors inside it, so links to the old heading still work.
- An `<a id>` anchor written inside a heading line is moved just below the heading, because navigation entries must be plain text.
- A closing `#` needs a space before it, so `# Learning C#` keeps its `#`.
- The table of contents shows levels 1 and 2 by default (`toc_depth`).
- Keep heading text short and informative; it doubles as the link anchor.

## 4. Links

| Link | Example | In the EPUB |
|---|---|---|
| To another chapter | `[chapter 5](05-power.md)` | internal link |
| To a section | `[the storm case](02-baseline.md#the-storm-case)`, `[above](#water-budget)` | internal link to the heading or anchor |
| Web-style link to a chapter | `[chapter 5](05-power.html)`, `[part 2](part2/)`, `[part 2](part2/index.html)` | internal link to `05-power.md`, or to `part2/README.md` (or `readme.md`, `index.md`) when it is in the book (MB205) |
| To a file outside the book | `[license](../LICENSE)`, `[code](/src/main.py)`, a `.md` file that is not in the reading order | with `source_url`: a web link to the online copy (to the `.html` page for a `.md` file when `source_url` is a website); without it: plain text, the link is removed (MB202) |
| To a file that does not exist | `[old](04-old-name.md)` | error MB204, the build's links gate fails; with a website `source_url`: a web link that is not checked (MB203) |
| To a web page | `https://...` | kept; characters that are illegal in URLs (`[`, `]`, spaces, double quotes, `<>{}\|\^` and backtick) are percent-encoded |

- Use relative paths, exactly as on GitHub. `../` may climb out of the book folder, for example to a file at the repository root.
- `/` at the start of a path means the repository root, as on GitHub: the top of the git checkout that contains the book (for `check` of a URL, the cloned repository; for a folder that is not in git, the book folder, or for an mdBook the folder with `book.toml`). A `/` path to a chapter is an internal link even when the book sits in a subfolder: from a book in `book/`, `/book/02-power.md` is the chapter `02-power.md`.
- Anchors follow GitHub's rule: the heading text in lowercase, spaces become hyphens, punctuation is removed, letters of any script are kept (`## Water budget: ample ice` gives `#water-budget-ample-ice`; `## Выбор материала` gives `#выбор-материала`). Case does not matter, as on GitHub.
- A link that differs from an anchor only in ASCII punctuation or spaces, with exactly one candidate in the target file, is fixed and reported (MB201). Any other missing anchor is an error (MB200) and fails the build.
- For a custom anchor, put `<a id="r07"></a>` (or `<a name="r07"></a>`) where a link should land: table rows, old heading names after a rename. Links to `#r07` then work on GitHub and in the EPUB.
- Pandoc and GitHub make different anchors from headings with emoji. Avoid linking to such headings, or add a custom anchor.
- `source_url` is the online copy of the book folder: a GitHub address such as `https://github.com/you/book/blob/main/`, or the book's website. Links to files outside the book are resolved against it: `../preface.md` from a book in `get-started/` with `source_url: https://github.com/you/repo/blob/main/get-started/` becomes `https://github.com/you/repo/blob/main/preface.md`. A website `source_url` gets the published page instead: `preface.html`, and `index.html` for a `README.md`. Details in [configuration.md](configuration.md#source_url).

## 5. Citations and references

Cite with a number in square brackets and define each source once, in the same file:

```markdown
Solar power at Mars is 43% of Earth's [1].

## References

[1]: https://nssdc.gsfc.nasa.gov/planetary/factsheet/marsfact.html "NASA NSSDC, Mars Fact Sheet"
```

On GitHub the definitions are invisible and `[1]` becomes a link. In the EPUB, mdbindery builds a visible list, `[1] NASA NSSDC, Mars Fact Sheet. https://...`, and each `[1]` links to its entry.

- Definitions are per file: every chapter defines the numbers it uses; a bracketed number without a definition in the file is reported (MB302).
- The title in quotes is what readers see, so write `"Author, Title, Publisher, year"` (MB306).
- Only numeric labels are citations by default. A named label such as `[GitHub]` or `[Smith2020]` stays an ordinary reference link to its URL, as on GitHub. Set `citation_labels: all` to make named labels citations too; then every definition in the file is listed. Definitions used by images (`![alt][label]`) are never citations, and neither is a named label whose URL points to an image file.
- `[1]` and `[1][]` become citations; `[text][1]` stays a normal link to the URL.
- The conversion works on pandoc's document tree, so `[1]` in code blocks, inline code, math, and URLs is never touched.
- Remove definitions nobody uses (MB300) and never define one label twice with different URLs (MB301).
- The list shows numeric labels in numeric order, then named labels in the order they are defined.
- The list goes directly under the last heading in the file named References, Sources, Notes, Bibliography, Works cited, Литература, Источники, Примечания, or Список литературы (exact text, any level; for an underlined heading, after the underline). Text you write under that heading follows the list. Without such a heading, `## References` is added at the end of the file (MB303).
- `citations: none` turns all of this off: definitions stay invisible and `[1]` is a plain link to the URL.

### Footnotes

Write `Text.[^1]` and define `[^1]: The note.` anywhere in the same file; indent continuation lines by four spaces. Labels are per file.

In the EPUB, footnotes become numbered endnotes at the end of each chapter (the numbering starts again in every chapter). Each note begins with its number, which links back to the place in the text. A reference without a definition is an error (MB304); a definition nobody uses is a warning (MB305).

## 6. Images

Keep every image inside the repository, usually in `images/`, and reference it with a relative path from the Markdown file (`images/x.png` from a chapter in the book folder, `../images/x.png` from `chapters/`). A path starting with `/` means the repository root. A query (`?raw=true`) or fragment in a local path is ignored.

| What you want | Markdown | HTML | EPUB result |
|---|---|---|---|
| Image inside a sentence | `text ![Short alt](images/icon.png) text` | `<img>` inside text, in a table cell, or in a tight list | inline image with class `inline`, at most 1.4 em tall (about one line) |
| Block image, no caption | `![Alt text](images/photo.jpg)` alone in its paragraph | `<img>` alone on its line, or alone in `<p align="center">`, `<div>`, `<center>`, or `<picture>` | centered image, at most the screen width |
| Figure with caption | `![Alt text](images/chart.png "Caption text")` alone in its paragraph | the same, with `title="Caption text"`; or `<img>` inside `<figure>`, with the caption in an optional `<figcaption>` | image with the caption below it |
| Full-page image | title `"full-page"` or `"full-page: Caption"` (any letter case) | `title="full-page: Caption"` | image on its own page, at most 92% of the screen height |

- An image counts as "alone" when nothing but spaces and line breaks share its paragraph. This also works inside quotes and loose lists; in table cells and tight lists an image stays inline.
- Reference-style images (`![alt][label]` with `[label]: images/x.png`) work too.

Alt text is required for every image except purely decorative ones: describe what the image shows. The caption is extra, not a substitute. The EPUB declares that images have text alternatives only when every image has alt text.

| Source | Alt text |
|---|---|
| `![What it shows](x.png)` | present |
| `![](x.png)` | missing (MB402); Markdown has no decorative form |
| `<img src="x.png">` without `alt` | missing (MB402) |
| `<img src="x.png" alt="">` | decorative, allowed |

Formats and sizes:

| Rule | Check |
|---|---|
| JPEG for photos, PNG for diagrams and screenshots, SVG for vector art, GIF and WebP also work | other extensions: MB403 warning |
| BMP, TIFF, HEIC, HEIF, PSD, AVIF, ICO, EPS, and PDF do not work in EPUB | MB403 error |
| At most 3200 px on the long side and 5 MB per file; readers never show more | MB404 warning |
| Animated GIF: most readers show only the first frame | MB405 note |
| SVG with scripts or `foreignObject`: many readers drop them; keep text as real SVG text | MB405 warning |

Missing and remote images are replaced in the EPUB by a text placeholder, `[image: alt]`, and the images gate fails:

- a file that does not exist: MB400 error;
- a web address such as `https://example.org/x.png`, because an EPUB cannot load images from the web: download the image into `images/` (MB401 error).

An image URL that points to a file of the same GitHub repository (`https://github.com/OWNER/REPO/blob/BRANCH/images/x.png?raw=true`, `https://raw.githubusercontent.com/OWNER/REPO/BRANCH/images/x.png`) uses the local file instead; `check` notes it (MB401) with the relative path to write. mdbindery knows the repository from `source_url`, the git remote, or the URL given to `check`.

Images outside the book folder (for example `../shared/x.png`) are embedded, with an MB406 warning. In a repository checked by URL they must also stay inside the repository; one that climbs out of it is an MB406 error.

### The cover

| Rule | Check |
|---|---|
| Name it `cover.jpg`, `cover.jpeg`, or `cover.png` and put it in the book folder or in `images/`, `image/`, `img/`, `assets/`, `media/`, `figures/`, or `cover/`; or set `cover.image` | no cover: MB410 note, a typographic cover is generated from the title, subtitle, and authors |
| 1600x2560 px: at least 1400 px on the short side, height about 1.6 times the width (1.4 to 1.7) | MB411 warning |
| JPEG or PNG; other readable formats (GIF, WebP, ...) are converted to JPEG | MB412 warning; an unreadable file is an MB412 error |
| RGB; CMYK is converted | MB411 warning |

Transparent areas are filled with white, and EXIF rotation is applied. The full-size JPEG goes to `<slug>-cover.jpg` in the output folder for store uploads; the copy inside the EPUB is scaled to `cover.embed_height` (1000 px by default).

## 7. Tables and cards

- Use GitHub pipe tables with a header row. HTML tables work too.
- Tables up to about 6 columns read well on phones. From 9 columns (`wide_table_warn`) `check` reports MB600.
- Wide tables can be rendered as cards: list the file under `options.cards.files`. Every table in it with at least `cards.min_columns` (9) columns becomes one block per row; the first `cards.title_columns` columns (1) form the card heading, and every other non-empty cell appears as "Column header: value".
- `<a id="r07"></a>` anchors in the first cell move to the card, so links to rows keep working.
- Files rendered as cards never fail the word-count gate, because the column labels add words.

## 8. Charts

- Mermaid diagrams in ```` ```mermaid ```` blocks are rendered to PNG images (neutral grayscale theme, readable on e-ink). GitHub renders the same blocks natively.
- Give each chart a `title` line (or `title:` in its front matter) or clear node labels: they become the image's alt text, prefixed with `mermaid_alt_prefix` ("Chart: ..."). `mermaid_alt:` per file overrides it.
- Gantt charts get `todayMarker off` (unless `mermaid_today_marker: true`), so the image does not depend on the build date.
- A chart that fails to render fails the build (MB701); test the syntax at https://mermaid.live.
- Without mermaid-cli, charts become a quote with the alt text and "This chart is available in the online edition", plus a link when `source_url` is set; the build still passes (MB700).

## 9. Math, code, and other Markdown

- Math: `$E = mc^2$` and `$$ ... $$` become MathML. Some readers show MathML poorly (MB710); keep formulas simple.
- Dollar signs: text between two `$` is read as a formula when the first `$` is followed by a non-space, the second is preceded by a non-space, and the second is not followed by a digit. So `$20 per person, $35 with lunch` is safe, but `PATH=$HOME/bin:$PATH` becomes a formula (MB711). Write `\$` for a literal dollar sign when in doubt.
- Code blocks with a language (```` ```python ````) are highlighted in monochrome (`highlight_style`). Keep lines under about 90 characters, or they wrap on small screens (MB720). Nothing inside code is changed: links, citations, and HTML tags in code stay as written.
- GitHub alerts (`> [!NOTE]`, `[!TIP]`, `[!IMPORTANT]`, `[!WARNING]`, `[!CAUTION]`) become labeled boxes.
- Task lists (`- [x] done`) keep their checkboxes.
- Block quotes, lists, emphasis, and strikethrough work as on GitHub.
- A line with `***` becomes a scene-break ornament (useful for fiction). Prefer `***` to `---`: a `---` directly under a line of text turns that line into a heading.

## 10. HTML

Prefer Markdown. HTML is converted at every depth (inside quotes, list items, table cells, and divs), and the rules below apply everywhere. HTML inside code is left alone.

| HTML | In the EPUB |
|---|---|
| `<b>`, `<strong>`, `<i>`, `<em>` | bold, italic |
| `<u>`, `<ins>`, `<s>`, `<del>`, `<strike>` | underline, strikethrough |
| `<sup>`, `<sub>` | superscript, subscript |
| `<code>`, `<kbd>` | inline code |
| `<q>`, `<small>`, `<mark>` | quoted text, smaller text, highlighted text |
| `<br>` | line break |
| `<a href="...">` | link, with the same rules as Markdown links |
| `<a id="...">`, `<a name="...">` | anchor |
| `<img>` | image (section 6) |
| `<figure>` with an `<img>` and an optional `<figcaption>` | a figure like the Markdown form (section 6), with the `<figcaption>` text as its caption |
| HTML blocks with `<h1>` to `<h6>`, `<table>`, `<ul>`, `<ol>`, `<li>`, `<blockquote>`, `<pre>`, `<dl>` | headings, tables, lists, quotes, code, definition lists |
| `<div class="name">` on its own line, Markdown after it, `</div>` on its own line | a `div` with that class, which `extra_css` can style |

- Wrappers lose their markup and keep their content: `<p align>`, other `<div>` forms, `<span>`, `<font>`, `<center>`, `<abbr>`, `<cite>`, `<dfn>`, `<time>`, `<var>`, `<samp>`, `<details>` and `<summary>` (the content is always shown), `<picture>`, `<big>`, `<tt>`.
- Unknown tags (for example mdBook's `<Listing>`) are dropped and their content kept: MB500 warning in `check`, MB501 note listing what the build drops. If a tag is meant as text, write `&lt;name&gt;` or put it in backticks. A name with an underscore, such as `<YOUR_NAME>`, is not a tag and stays as text.
- Tags that cannot work in an ebook are errors in `check` (MB500), and the build removes them: `<script>`, `<style>`, `<iframe>`, `<object>`, `<embed>`, `<form>`, `<input>`, `<button>`, `<select>`, `<textarea>`, `<video>`, `<audio>`, `<canvas>`.
- Entities in `<img>` and `<a>` attributes are decoded once: `alt="R&amp;D"` becomes "R&D".
- `<https://example.org>` and `<user@example.org>` are autolinks, not HTML.

### Comments

`<!-- ... -->` comments, including multi-line ones, are ignored everywhere: headings, reference definitions, images, and tags inside them are neither checked nor built. Use them for notes to yourself.

## 11. Language and typography

- Set `metadata.lang` (`en-US`, `ru`, `de`, ...). It drives hyphenation and the reader's dictionary. Without it, mdbindery guesses `ru` or `en-US` from the text (MB122).
- Typography is kept as written: curly quotes, «guillemets», em and en dashes, non-breaking spaces. mdbindery never "smartens" or changes punctuation.
- For non-English books also set `options.mermaid_alt_prefix` (for example `Схема`) and, except for Russian, `options.accessibility_summary` in the book's language; the built-in summary exists only in English and Russian. Russian reference headings (Литература, Источники, Примечания, Список литературы) are recognized by default.

## 12. Metadata and license

- In `mdbindery.yaml`: `title`, `subtitle`, `authors`, `lang`, `rights`, `description`. Metadata is written literally, so Markdown or HTML in it appears as typed. Leave `identifier:` empty on its own line: the first build writes a permanent `urn:uuid` there, which stores use to recognize new versions of the same book (MB120 to MB124).
- Keep a `LICENSE` file in the book folder or at the repository root. When `rights` is empty, mdbindery reads it: an `SPDX-License-Identifier:` line works best; Creative Commons, GNU, MIT, Apache 2.0, BSD, MPL, and Unlicense texts are recognized too. The details are in [configuration.md](configuration.md#license-detection).

## 13. Checklist

- [ ] One `#` heading at the top of every chapter; no skipped levels
- [ ] Reading order in `files:`, or numbered file names that sort correctly
- [ ] Links between chapters are relative paths; anchors match headings
- [ ] Every `[n]` citation has a definition in the same file, with a title
- [ ] Footnote references and definitions match
- [ ] Every image is local, has alt text, and is JPEG, PNG, SVG, GIF, or WebP up to 3200 px
- [ ] `images/cover.jpg` at 1600x2560 px
- [ ] Wide tables listed under `cards`
- [ ] Dollar signs that are not math escaped as `\$`
- [ ] No `<script>`, `<iframe>`, or other interactive HTML
- [ ] `mdbindery.yaml` with title, authors, lang, rights, an empty `identifier:`, and `source_url`
- [ ] `mdbindery check . --build` reports no errors
