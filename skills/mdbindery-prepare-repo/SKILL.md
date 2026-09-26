---
name: mdbindery-prepare-repo
description: Prepare a GitHub or local repository of Markdown chapters so that mdbindery builds a correct, validated EPUB 3 from it while the book stays readable on GitHub. Covers the reading order, mdbindery.yaml, headings, links and GitHub anchors (../ and / paths, .html links, source_url for a published website), citations and footnotes, images and the cover, wide tables, Mermaid charts, math and dollar signs, raw HTML, mdBook books, license and metadata, and a check-and-fix loop that ends when every build gate passes and the phone-size screenshots look right. Use when the user asks to prepare a repo for an ebook or EPUB, make this repo an ebook, turn a Markdown repository or mdBook into a book, fix the chapter order, links, citations, or images for an EPUB, fix mdbindery check errors or warnings, fix failed build gates, or get a repository to pass `mdbindery check` and `mdbindery build`. To only run the tool (install, check, build, preview), use the mdbindery skill.
---

# Prepare a repository for mdbindery

mdbindery builds an EPUB 3 from Markdown written the GitHub way: one file per chapter, relative links between files, images inside the repository, citations as `[1]` with reference definitions. This skill brings an existing repository into that shape and loops on `mdbindery check` and `mdbindery build` until every gate passes. The same files must keep rendering well on github.com.

The authoritative rules are in `docs/book-structure.md`, `docs/checking.md`, and `docs/configuration.md` of the mdbindery repository. This skill adds the procedure, a fix for every check code, and the tool's limits, verified against mdbindery 0.1.0.

## When to use

- A repository or folder of Markdown files should become an ebook and has never passed `mdbindery check`.
- The user wants the reading order, headings, links, citations, images, tables, charts, or HTML fixed for an EPUB.
- A build fails a gate (links, images, charts, includes, EPUBCheck, Ace, word count) and the cause is in the Markdown or the configuration.

Use the `mdbindery` skill instead when the book is already clean and the task is only to install, check, build, or preview. This skill does not cover editing prose (style, grammar, facts) or converting Word, LaTeX, or AsciiDoc to Markdown.

## Ground rules

1. Never change facts, numbers, names, quotations, or the meaning of the author's text. Change the author's text only as far as a fix needs it: a heading level, a link target, an image path, an escaped character, HTML replaced by Markdown that renders the same.
2. Prefer configuration to editing files. `files:`, `title:`, `drop_sections`, `drop_lines`, `source_url`, and `options` change the EPUB without touching the Markdown.
3. Show the plan before you change anything: what you will change, in which files, and why; which findings you will leave and why. Wait for approval. Renames, splits, and deletions always need it.
4. Do editorial work only when asked. Rewording, cutting, splitting or merging chapters, and switching citation styles are the author's decisions. Propose them in the final report.
5. Keep the book readable on GitHub: relative links, relative image paths, Markdown before HTML.
6. Ask before deleting or hiding content: sections, paragraphs, images, badges, reference definitions, footnotes, HTML blocks that contain text.
7. Commit nothing unless the user asks. Never commit `dist/`, check reports, or screenshots; write reports outside the repository.
8. Rename and move files with `git mv` so history follows them. After every rename, update every link and image path that points to the old name, in Markdown, in HTML attributes, and in `mdbindery.yaml`: `git grep -n -F "old name.md"` and `git grep -n -F "old%20name.md"`.
9. List every piece of text you wrote yourself (alt text, headings, reference titles, a References heading, footnote text the author gave you) in the final report for review.
10. Do not write a title page or a table of contents; mdbindery generates both. Do not edit anything under `dist/`.
11. Rerun `mdbindery check` after each batch of fixes and work from its report, not from memory.

| Do it after the plan is approved | Ask the author first |
|---|---|
| Fix link targets and anchors; add `<a id>` anchors | Delete or hide any text, image, badge, footnote, or reference definition |
| Fix heading levels when the intended hierarchy is clear | Change heading wording or chapter numbering |
| Replace HTML with Markdown that renders the same | Split or merge chapter files; rename chapter files |
| Move images, convert formats, scale down | Download third-party images (license) |
| Write alt text (then list it for review) | Choose between two URLs for one citation label |
| Write and complete `mdbindery.yaml` | Authors, rights, and anything else that must not be guessed |
| Re-save files as UTF-8 | Remove YAML front matter a site generator may use |
| Copy reference titles from the cited source | Write footnote text, captions, or attribution lines |

## The target shape

```
my-book/
├── mdbindery.yaml          # configuration, with the identifier the first build writes
├── README.md               # front matter: what the book is (optional)
├── 01-first-chapter.md     # chapters, one "#" heading each, in reading order
├── 02-second-chapter.md
├── appendix-a-glossary.md  # appendices after the chapters
├── images/                 # every image the book uses
│   └── cover.jpg           # 1600x2560 px
└── LICENSE
```

How mdbindery reads it:

- Each file in the reading order is one chapter. Its first `#` heading is the chapter title and starts a new file inside the EPUB. The build repairs files without one (MB106) and moves content above the title below it (MB110), but a clean file says what the author means.
- Headings get GitHub-style anchors. Links between files become internal EPUB links; a link to a missing anchor or file fails the build.
- Reference definitions with numeric labels (`[1]: URL "Title"`) become a visible numbered list under the file's References heading, and every `[1]` links to its entry.
- Images are embedded. Where an image sits (inside a sentence or alone in a paragraph) and its title decide whether it becomes an inline icon, a block image, a figure with a caption, or a full-page image.
- Gates: links, images, charts, includes, EPUBCheck, Ace, and a per-file word count. The book is done when `mdbindery build` prints `BUILD OK` with no gate skipped or at `warn`.

## Procedure

### 1. Install and verify the tool

```
mdbindery --version
mdbindery doctor
```

`doctor` prints the tool home and one line per tool: `pandoc`, `epubcheck`, `java`, `node`, `mermaid`, `ace`, `python`. It exits with 1 when pandoc or EPUBCheck is missing; run `mdbindery install-tools` then (it also downloads a Java runtime when no Java 11 or newer is found). `mermaid` must say `renders PNG`, or charts become placeholders. Without `ace` the accessibility gate only warns, and `preview` does not work.

If `mdbindery` is not installed, ask the user before installing software, then:

```
# Linux, macOS
curl -fsSL https://raw.githubusercontent.com/sagol/mdbindery/main/install/install.sh | bash
# Windows PowerShell
irm https://raw.githubusercontent.com/sagol/mdbindery/main/install/install.ps1 | iex
```

The installer needs no admin rights. The command goes to `~/.local/bin` (`MDBINDERY_BIN` overrides it) and the tools to the tool home (`MDBINDERY_HOME` overrides it; keep it set afterwards). Options: `--no-node` (no Mermaid, Ace, or preview), `--java auto|always|never`, `--no-tools`, `--local PATH`, `--ref REF`, `--uninstall`; in PowerShell `-NoNode`, `-Java`, `-NoTools`, `-Local`, `-Ref`, `-Uninstall`. To add or repair tools later: `mdbindery install-tools [--no-node] [--java auto|always|never] [--force]`.

For image work, check what is available: `python3 -c "import PIL; print(PIL.__version__)"` (Pillow; install with `python3 -m pip install --user pillow`), `magick -version` (ImageMagick 7), `convert -version` (ImageMagick 6).

### 2. Run the check and read it

Keep report files outside the repository (in PowerShell, use `$env:TEMP\mdb-check.json`).

```
mdbindery check . --json "${TMPDIR:-/tmp}/mdb-check.json" --report "${TMPDIR:-/tmp}/mdb-check.md" -q
```

Before cloning, or to look at another branch, check the repository URL. mdbindery clones it into a temporary folder and deletes it afterwards, so to fix anything, clone the repository and work in the clone.

```
mdbindery check https://github.com/OWNER/REPO --json "${TMPDIR:-/tmp}/mdb-check.json" -q
mdbindery check https://github.com/OWNER/REPO/tree/BRANCH/FOLDER
mdbindery check https://github.com/OWNER/REPO --ref v2
```

Exit codes: 0 no errors (warnings allowed), 1 errors, 2 the target cannot be read (`check error: folder not found: ...`, `repository not found or not accessible: ...`, `branch or tag not found: ...`). `--no-render` skips the test rendering of Mermaid charts (faster while iterating; run without it before you finish). `-c FILE` uses another config file. `check` applies `drop_sections` and `drop_lines`, so content the build removes is not reported.

Read the Markdown report top down:

- Result: `ready to build` or `needs fixes before a correct EPUB can be built`, with the counts.
- Book: title and language, config, file count, references, footnotes, charts, includes, images by kind, and the trial build result.
- Summary: a table with the count per code and severity, shown when there are more than 10 findings. Start here on a large repository: one cause often produces dozens of findings of one code.
- Errors, Warnings, Notes: one entry per finding with `file:line` and a fix. More than three findings of one code in one file are grouped into one entry with the line numbers (`lines 934, 937, ...`); the JSON report has every one.
- Reading order: the files in the order the book will use.
- Suggested mdbindery.yaml: present when there is no config.

The JSON report has `ok`, `counts`, `by_code`, `facts`, and `findings` (each with `severity`, `code`, `file`, `line`, `message`, `fix`):

```
jq '.counts' "${TMPDIR:-/tmp}/mdb-check.json"
jq -r '.by_code[] | "\(.code) \(.severity) x\(.count)"' "${TMPDIR:-/tmp}/mdb-check.json"
jq -r '.findings[] | "\(.severity)\t\(.code)\t\(.file):\(.line // "")\t\(.message)"' "${TMPDIR:-/tmp}/mdb-check.json"
jq -r '.findings[] | select(.code=="MB200") | "\(.file):\(.line)\t\(.message)"' "${TMPDIR:-/tmp}/mdb-check.json"
```

Without jq: `python3 -c "import json,sys; [print(f['severity'], f['code'], f'{f[\"file\"]}:{f[\"line\"] or \"\"}', f['message']) for f in json.load(open(sys.argv[1]))['findings']]" mdb-check.json`.

Read the facts first:

- `facts.files`: the reading order. Translations, navigation files, notes, or a wrong order mean step 3.
- `facts.inferred`: what was guessed (`config (no mdbindery.yaml found)`, `files (reading order)`, `metadata.title`, `metadata.lang`, `metadata.rights`, `cover.image`, `source_dir (book.toml)`).
- `facts.totals.images`: counts of `inline`, `block`, `figure`, and `full-page` images, estimated line by line. A real picture counted as `inline` shares its line with text, another image, or a link, and would render one line tall (8.2), unless it sits in an HTML `<figure>` (the build makes that a figure).
- `facts.github`: owner, repo, branch, and folder of a URL check.
- `facts.suggested_config`: a starter config, present when there is no `mdbindery.yaml`.

Then plan the fixes in this order: configuration and files (MB1xx), encoding, headings, links, citations, images, HTML, charts and math. The trial-build codes MB900 to MB904 appear only with `--build` (step 15). Read "Known limitations" below before chasing a finding that looks wrong.

### 3. Decide the reading order

Inventory the Markdown files (`git ls-files '*.md'`) and read each one's first heading. Sort them into:

- Book: front matter (usually `README.md`), chapters, appendices, back matter.
- Skipped automatically by base name (any case): `CHANGELOG`, `CONTRIBUTING`, `CODE_OF_CONDUCT`, `SECURITY`, `LICENSE`, `LICENCE`, `AUTHORS`, `SUPPORT`, `GOVERNANCE`, `CITATION`, `FUNDING`, `MAINTAINERS`, `CODEOWNERS`, the pull request and issue templates, and table of contents files (`SUMMARY`, `toc`, `contents`, `table-of-contents`).
- Not book, but not skipped: translations (`README-de.md`, `README.ru.md`), navigation files (`_sidebar.md`), notes, drafts, TODO lists, tooling docs. Leave them out of `files:`. Build each translation as its own book with its own config file (`mdbindery build -c mdbindery-de.yaml`).

`files:` in `mdbindery.yaml` decides the order. Without it, mdbindery infers one and says where it came from (MB125; `init` writes the same as a comment):

1. The first table of contents file in the book folder (`SUMMARY.md`, `toc.md`, `TOC.md`, `contents.md`, `CONTENTS.md`, `table-of-contents.md`) that links to local `.md` files (`SUMMARY.md` needs one link, the others two): the links in order. With `SUMMARY.md` (mdBook, GitBook), files it does not list are left out, the README included; with the others, the rest follow by name.
2. Else, only when the chapter file names are not all numbered: the README's links to local `.md` files, if they cover at least half of the files.
3. Else file names: `README.md` first; unnumbered front matter names (`title-page`, `half-title`, `dedication`, `epigraph`, `foreword`, `preface`, `prologue`, `introduction`, `intro`, and the Russian equivalents); chapters in natural order (`2-...` before `10-...`); appendices (names containing `appendix` or `приложение`, or `ap`/`app` plus one letter from a to h, such as `apA.md` or `app-b.md`); then back matter (`afterword`, `epilogue`, `conclusion`, `glossary`, `bibliography`, `references`, `acknowledgments`, `about-the-author`, `colophon`, `index`, and Russian equivalents).

When a `chapters/` folder exists, discovery reads `chapters/*.md` plus the root README; other root `.md` files are left out and listed as MB104. Deeper folders (`part-1/01-x.md`) work only when listed in `files:`. A table of contents file listed in `files:` gives MB126: remove it, because the EPUB has its own navigation.

Write the order into `files:` explicitly, even when the inferred one is right: it is then stable and reviewable.

Naming conventions to propose (renames need approval):

- `NN-short-slug.md` with a zero-padded number that matches the reading order: `01-introduction.md`, `02-site-selection.md`. Use three digits for 100 or more files. Lowercase ASCII letters, digits, and hyphens link most easily; a space must be written `%20` in links.
- Appendices: `appendix-a-glossary.md`. The word `appendix` sorts them after the chapters.
- `README.md` as the opening section; in the config give it `title:` ("About this book") and `drop_sections:` for GitHub-only sections such as "Contributing".
- mdbindery has no part level; each file is a top-level entry in the table of contents. Keep part names in chapter titles, or give each part a short file with its own `#` heading (ask the author).
- A book that is one long `README.md` becomes one EPUB chapter. Propose splitting it at `##` headings into chapter files; the former `##` becomes the new file's `#`, the headings below move up one level, and links to old anchors (`README.md#power`) change to `05-power.md` or `05-power.md#anchor`.

Present the plan as a table (old name, new name, position; files left out; splits) and wait for approval. Then:

```
git mv "Chapter 1.md" 01-beginnings.md
git grep -n -F "Chapter 1.md"; git grep -n -F "Chapter%201.md"   # fix every hit, including mdbindery.yaml
```

Anchors inside renamed files stay valid because the headings did not change. Links to the old file names from outside the repository (other sites, bookmarks) break; say so in the report.

### 4. Write mdbindery.yaml

```
mdbindery init            # writes mdbindery.yaml inferred from the repository
mdbindery init --force    # rewrite it; keeps metadata, identifier, cover, files, and options; old file saved as mdbindery.yaml.bak
```

`init` fills in the title, language, rights (from a LICENSE file), cover, reading order, and `source_url` (from a GitHub `origin` remote and the current branch). Then complete it:

1. `identifier:`: leave it as `init` wrote it, empty. The first `mdbindery build` writes a permanent `urn:uuid:...` there (`check --build` does not). Never change it afterwards: stores use it to recognize new versions. If the book already has an identifier, such as `urn:isbn:...`, put that in. `identifier: ~` counts as empty.
2. `metadata`: `title`, `subtitle`, `authors` (a list), `lang` (quoted, for example `"en-US"`; an unquoted `no` is read as false and rejected), `date` (`git` for the last commit date, or `YYYY-MM-DD`), `rights`, `publisher`, `description`, `subjects`, `series`, `series_position`. Values are written into the EPUB literally, never parsed as Markdown. Take authors and rights from the repository (LICENSE, README credits, `book.toml`) and confirm them with the user; never guess.
3. `slug`: the output file name (`dist/<slug>.epub`). The default comes from the title and keeps non-Latin letters; set an ASCII slug if the author wants one. Letters, digits, `.`, `-`, and `_` only.
4. `source_url`: the online copy of the book folder, with a trailing `/` (added if missing). Links to files outside the book and chart placeholders point there. Either the GitHub folder (`https://github.com/OWNER/REPO/blob/BRANCH/FOLDER/`), or, when the book is published as a website (mdBook, a docs site), the web address of the book folder (step 6).
5. `cover`: `image` is relative to the config file. Leave it empty to use an auto-detected `cover.jpg`, `cover.jpeg`, or `cover.png` in the book folder or in `images/`, `image/`, `img/`, `assets/`, `media/`, `figures/`, or `cover/`, or else a generated cover styled by `background`, `foreground`, and `accent` (`#rgb` or `#rrggbb`). `embed_height` (default 1000, 200 to 10000) sets the size of the copy inside the EPUB.
6. `files`: the reading order from step 3. A plain string, or a mapping with `file`, `role` (`front`, `chapter`, `appendix`, `back`; informational), `title` (replaces the chapter's `#` heading text in the EPUB only; the heading keeps its anchor), `drop_sections` (headings whose sections are removed from the EPUB), `mermaid_alt` (alt text for every chart in that file), `key` (internal; leave it out). Paths are relative to the book folder, with no `..` and no absolute paths; a file listed twice is an error.
7. `options`: see the table.

| Key | Default | Set it when |
|---|---|---|
| `citations` | `refdefs` | `none`: the book has no source lists; no reference lists are generated |
| `citation_labels` | `numeric` | `all`: named labels such as `[Smith2020]` are citations too (step 7) |
| `reference_headings` | References, Sources, Notes, Bibliography, Works cited, Литература, Источники, Примечания, Список литературы | the book uses another heading; the list replaces the default, so include every heading in use |
| `reference_heading_new` | `References` | the heading added when a file has citations but no reference heading; set it for non-English books |
| `drop_lines` | `[]` | regular expressions; matching lines outside code are removed from every file in the EPUB (badges, repeated headings) |
| `toc`, `toc_depth` | `true`, `2` (1 to 6) | the table of contents should show deeper levels |
| `split_level` | `1` (1 to 6) | the author wants each section in its own EPUB file; leave it otherwise |
| `cards.files` | `[]` | files whose wide tables become cards (step 9) |
| `cards.min_columns`, `cards.title_columns` | `9`, `1` | cards for narrower tables; the first N cells as the card heading |
| `wide_table_warn` | `9` | column count that triggers MB600 |
| `mermaid` | `png` | `placeholder` (a note with a link to the online edition) or `keep` (leave the code block) |
| `mermaid_alt_prefix` | `Chart` | non-English books (`Схема`, `Diagramm`) |
| `mermaid_theme`, `mermaid_font_size`, `mermaid_scale` | `neutral`, `18`, `2` | charts need tuning after the preview |
| `mermaid_today_marker` | `false` | a Gantt chart should show today's line (makes builds date-dependent) |
| `highlight_style` | `monochrome` | another pandoc highlight style, or `none` |
| `css`, `extra_css`, `embed_fonts` | empty | the author supplies styling or fonts (paths relative to the config; they must exist) |
| `accessibility_summary` | built-in English or Russian text, by `lang` | books in other languages |
| `conformance_claim` | empty | the author has an accessibility conformance statement |
| `strict_links`, `epubcheck`, `ace` | `true` | never turn these off to get a pass |
| `ace_waivers` | `[]` | only with the author's approval, rule by rule |
| `wordcount_tolerance`, `wordcount_min_words` | `0.02`, `25` | never loosen them to hide lost text |

Other top-level keys: `output_dir` (default `dist`), `source_dir` (only when the config lives outside the book folder). An unknown top-level key is a config error (MB102 error; `build` stops); an unknown nested key is an MB102 warning with a "did you mean" hint. Invalid values (wrong type, out of range, a `drop_lines` pattern that does not compile, a missing `css` file) are MB102 errors that name the key.

### 5. Fix headings

Target: every book file starts with exactly one `#` heading; sections use `##`, subsections `###`; levels never skip. ATX (`#`), setext (underlined with `===` or `---`), and HTML (`<h1>`) headings all count.

- MB106, no level-1 heading. The build repairs it, and the message says how: it promotes the first heading when nothing visible stands above it (and moves the file's other headings up by the same number of levels, never above `##`), or makes a title from the file name (the book title for `README.md`). Fix it properly: if every heading in the file is one level too deep, promote all of them by one level; otherwise add `# Title` as the first line, with the title from the README's table of contents or the author. Without editing the file, set `title:` for it in `files:`.
- MB110, content above the chapter title (badges, a logo, text). The build moves it below the title. Move the `#` heading to the top, or remove the badges from the EPUB with `drop_lines` (8.5). Anchors and comments above the title do not count.
- MB107, several `#` headings in one file: each starts its own EPUB section and table of contents entry. When every file repeats the book title as a first `#` line, the book-level MB107 note gives a ready `drop_lines` pattern; the pattern also removes that heading from the README, so give the README a `title:` as well. Otherwise demote the second and later `#` headings, with everything under them, by one level, or propose a split.
- MB108, skipped level (`##` then `####`): raise the deeper heading to the missing level and shift its subheadings with it.
- MB109, empty file: remove it from `files:`; delete the file only with approval.
- MB111, YAML front matter (a `---` block at the top, from Jekyll or Hugo): the build ignores it, and invalid YAML there stops the build (MB903 in check). If it carries the only title, add `# <that title>` below it or set `title:`. Ask before removing front matter: a site generator may need it.
- Emoji in headings: pandoc writes the emoji's name into the anchor (`## Emoji 🚀 launch` becomes `#emoji-rocket-launch`) while GitHub drops it (`#emoji--launch`), so no link can work in both places. Remove emoji from headings that are link targets, or put an `<a id>` anchor on the line before the heading and link to that.
- Keep the author's wording and numbering style (`# 3. Power`, `# Chapter 3: Power`).
- Changing heading text changes its anchor. After any heading edit, search for the old anchor (`git grep -n -F "#old-anchor"`) and fix the links, or keep it alive with `<a id="old-anchor"></a>` on the line before the heading. A `title:` in the config does not change the anchor.

### 6. Fix links and anchors

How an anchor is built (GitHub's rule; pandoc produces the same ids):

1. Take the heading's visible text: link markup and backticks removed, their text kept.
2. Lowercase it.
3. Delete every character except letters of any script, digits, spaces, hyphens, and underscores.
4. Replace each space with a hyphen. Runs are not collapsed: `C++ & Rust` gives `c--rust`.
5. A repeated heading in the same file gets `-1`, `-2`, and so on.

| Heading | Anchor |
|---|---|
| `## Water budget: ample ice` | `#water-budget-ample-ice` |
| `## 3.1 Power and heat` | `#31-power-and-heat` |
| `## C++ & Rust` | `#c--rust` |
| `## Snake_case heading` | `#snake_case-heading` |
| ``## `code` in heading`` | `#code-in-heading` |
| `## [Linked](x.md) heading` | `#linked-heading` |
| `## Выбор материала` | `#выбор-материала` |
| `## Café & crème` | `#café--crème` |
| second `## Duplicate` in a file | `#duplicate-1` |
| `## Emoji 🚀 launch` | GitHub `#emoji--launch`, EPUB `#emoji-rocket-launch` (avoid) |

The anchors script under Snippets lists them for a file. After a build, the authoritative list is in the EPUB, where every id carries the file's key (`k00-` for the first file in the reading order, `k01-` for the second):

```
unzip -p dist/<slug>.epub 'EPUB/text/*.xhtml' | grep -o 'id="k[0-9]*-[^"]*"' | sort -u
```

mdbindery matches anchors case-insensitively, as GitHub does, and fixes a case-only difference silently. When a link differs from exactly one anchor of the target file only by ASCII punctuation or spaces, it repairs the link and reports MB201; fix the link anyway so it works on GitHub.

Link forms:

| Target | Markdown | EPUB result |
|---|---|---|
| Another chapter | `[chapter 5](05-power.md)` | internal link to the chapter start |
| A section in another chapter | `[the storm case](02-baseline.md#the-storm-case)` | internal link |
| A section in the same file | `[see above](#water-budget-ample-ice)` | internal link |
| From `chapters/` to the front matter | `[about the book](../README.md)` | internal link |
| A path from the repository root | `[chapter 5](/book/05-power.md)` | `/` is the root of the git checkout, as on GitHub; in a folder that is not a git checkout, the book folder (for an mdBook, the folder with `book.toml`) |
| A file outside the book | `[license](../LICENSE)`, `[code](src/main.py)` | with `source_url`: a web link to that file; without: plain text (MB202) |
| An mdBook or web-style link | `[chapter 5](05-power.html)`, `[part 2](part-2/)`, `[part 2](part-2/index.html)` | the matching `05-power.md`, or the folder's `README.md` or `index.md`, when it is in the book (MB205) |
| A file name with spaces | `[x](my%20file.md)` | internal link; better, rename the file |
| A custom anchor | `<a id="r07"></a>` at the target, `[row R07](04-data.md#r07)` | internal link |

Links outside the book:

- Paths may climb out of the book folder (`../preface.md`, `../src/code.py`); they are resolved correctly.
- An existing file that is not in the book: with `source_url`, the link points to `source_url` resolved like a relative URL (`../preface.md` against `.../blob/main/get-started/` gives `.../blob/main/preface.md`); without it, the link becomes plain text and `check` reports MB202 with the `source_url` to set.
- A file that does not exist: MB204, an error, and the links gate fails. This holds without `source_url` and with a GitHub `source_url`.
- Website mode: when `source_url` is not on github.com (for example `https://doc.rust-lang.org/book/`), links to pages that are not in the repository stay web links against that address and are not checked: MB203 (warning) in `check`, a `kept as web links (not checked)` line in the build log, no gate failure. Use it for mdBook and docs-site books whose links point to other parts of the published site (`../std/index.html`). Check a few such URLs by hand. Links to `.md` files outside the book then point to the published pages: `preface.md` becomes `.../preface.html`, and `README.md` becomes `.../index.html`.

Custom anchors: put `<a id="name"></a>` on its own line directly before the target heading or block, or at the start of the target line or table cell. Use lowercase ASCII ids, unique within the file. `<a name="name"></a>` works too. An anchor inside a heading line also works (the EPUB moves it below the heading), but the line before is cleaner. On GitHub the id is prefixed with `user-content-`, and GitHub's page scripts still resolve `#name`.

Fixes:

- MB200 (link to a missing anchor): find the heading the link means in the target file, compute its anchor, and fix the fragment. If the heading was renamed, use the new anchor or add `<a id="old-anchor"></a>` before the heading. Links into a section removed by `drop_sections`, or to a line removed by `drop_lines`, also give MB200: point them at content that stays.
- MB201 (matched approximately): replace the fragment with the anchor named in the message.
- MB202 (file not part of the book): set `source_url` (the fix text gives the value), or add the file to `files:` if it belongs in the book. On a URL check without `source_url` in the config, MB202 is a note that the link will point to the online repository.
- MB203 (web link not checked): confirm that the URL in the message exists on the site.
- MB204 (link to a missing file): find where the file went (`git log --all --oneline --stat -- "old.md"`, `git log --diff-filter=R --name-status`) and fix the path. For `.html` targets of a published website, set `source_url` to the site. If the file is gone for good, ask whether to point the link somewhere else or remove the link and keep its text.
- MB205 (web-style links resolved to book files): nothing to do.
- Absolute links to chapters of the same repository (`https://github.com/OWNER/REPO/blob/main/03-power.md#grid`) work, but lead out of the EPUB to the browser. Replace them with relative links (`03-power.md#grid`).
- In tables rendered as cards, the first `<a id>` of a row's first cell becomes the card's id; further anchors in that cell survive too.

### 7. Fix citations and footnotes

How `citations: refdefs` (the default) works:

- A reference definition `[label]: URL "Title"` (titles in `'...'` or `(...)` work too) whose label is a number is a source. With `options.citation_labels: all`, every label is. The definition lines stay in the file; they are invisible when rendered.
- In each file with sources, mdbindery generates a visible list: numeric labels first in numeric order, then named labels in order of appearance. Each entry reads `[label] Title. URL`. The list goes right after the last heading whose text is in `options.reference_headings` (exact text, any level, also setext), or under a new `## References` (`reference_heading_new`) at the end of the file.
- A link whose text is a citation label and whose URL is that label's URL becomes a citation `[1]` linked to its entry: `[1]`, `[1][]`, and `[1](same URL)`. `[the spec][1]` stays an ordinary link, `![alt][logo]` an ordinary image, and code, math, and URLs are never touched.
- With `citation_labels: numeric`, named labels (`[GitHub]`, `[Smith2020]`) stay ordinary reference-style links to their URL, with no list entry.
- A definition used by an image (`![Logo][logo]`, `![logo]`) is never a source, and neither is a named label pointing to an image file (`.png`, `.jpg`, `.svg`, and so on), so reference-style images keep working.
- Definitions are per file. A number cited in chapter 3 must be defined in chapter 3.
- With `citations: none`, no lists are generated and MB300 to MB303 and MB306 are not reported.

The title in quotes is what readers see. Write it as `"Author, Title, Publisher or site, year"`. If the title contains double quotes, delimit it with single quotes or parentheses: `[3]: https://example.org/x 'NASA, "Mars Fact Sheet", 2024'`.

Fixes:

- MB306 (citation without a title): open the cited page and copy author, title, publisher or site, and year as the page states them. If the page is unreachable or lacks the data, use what you can verify (page title and site name) and list the entry in the report. Never invent authors or years.
- MB302 (`[3]` in the text, no `[3]:` in this file): look for the definition elsewhere with `git grep -n '^\[3\]:'`. If the book numbers sources globally (each number has the same URL in every file that defines it), copy the definition line into this file. If numbering restarts per chapter, you cannot know which source is meant: ask. If `[3]` is not a citation (an array index or a literal bracketed number), escape it: `\[3\]`. `[0]` is never reported.
- MB300 (defined, never used in any form): the citation marker may be missing from the text (the author decides where it goes), the label may have a typo, or the definition may be a leftover. Report it; delete the line only with approval.
- MB301 (one label, two URLs): if both URLs are the same resource (http and https, a trailing slash, tracking parameters), keep one. Otherwise ask which source each citation means.
- MB303 (citations but no reference heading): the list will be added at the end under `## References`. To control the position, add the heading (or the book-language equivalent listed in `reference_headings`) above the definitions.
- MB304 (footnote without a definition): if a definition exists under a slightly different label (`[^note-1]` and `[^note1]`), fix the label. Otherwise ask the author for the note text.
- MB305 (footnote defined, never used): the marker was probably lost; ask where it belongs.

Footnotes are written `Text.[^1]` with `[^1]: The note.` anywhere in the same file; labels are per file. They become numbered endnotes at the end of each chapter, linked back to the text. Use one citation style per book, and do not convert between footnotes and numbered references unless asked.

### 8. Fix images and the cover

#### 8.1 Location and paths

- Keep every image inside the repository, usually in `images/`, and reference it with a path relative to the Markdown file: `images/x.png` from a root chapter, `../images/x.png` from `chapters/`. A path starting with `/` is relative to the repository root.
- Paths are case-sensitive on GitHub. Match the file name's case exactly, even if a local macOS or Windows file system forgives it.
- Name files in lowercase with hyphens, no spaces. Move and rename with `git mv`, then update every reference (`git grep -n -F "old-name.png"`).
- MB406 (image outside the book folder): a local build embeds it anyway, but keep book images inside the book folder. For a repository checked by URL, an image outside the repository is an error and fails the images gate.
- MB401 as a note (an image URL of this repository, such as `https://github.com/OWNER/REPO/blob/main/images/x.png?raw=true` or `raw.githubusercontent.com/...`): the build uses the local file. Replace the URL with the relative path given in the fix text.

#### 8.2 Kinds of images

| What | Markdown or HTML | EPUB result |
|---|---|---|
| Icon inside a sentence | `text ![Markdown icon](images/icon.png) text` | inline image, about one line tall |
| Block image, no caption | `![Alt text](images/photo.jpg)` alone in its paragraph | centered image |
| Figure with caption | `![Alt text](images/chart.png "Caption text")` alone in its paragraph | image with the caption below it |
| Full-page image | `![Alt text](images/plate.jpg "full-page")` or `"full-page: Caption"` alone in its paragraph | image on its own page, scaled to fit |
| HTML block image or figure | `<img src="images/x.png" alt="Alt text" title="Caption">` alone on its line, or wrapped alone in `<p align="center">` or `<div>` | the same as the Markdown forms; `title` is the caption, `full-page` works too |
| HTML `<figure>` | `<figure><img src="images/x.png" alt="Alt text"><figcaption>Caption</figcaption></figure>` (the `<figcaption>` is optional) | a figure with the `<figcaption>` as its caption |
| Cover | `images/cover.jpg`, or `cover.image` in the config | the book's cover |

"Alone in its paragraph" means a blank line before and after and nothing else on the line. The `full-page` prefix may be written in any case, and `fullpage` works; `"full page"` with a space becomes an ordinary caption.

These make a large picture render one line tall:

- text on the same line (`Figure 1: ![...](...)`);
- two or more images in one paragraph (a side-by-side row on GitHub);
- an image wrapped in a link (`[![Alt](images/x.png)](images/x.png)`);
- an image in a table cell or a tight list item.

Put each picture alone in its own paragraph without a link around it. Splitting a side-by-side row changes the GitHub layout; mention it in the report. `facts.totals.images` estimates the kinds line by line, so it can differ from the build: an `<img>` inside `<figure>` is counted as `block` or `inline`, although it builds as a figure. The preview decides.

Captions: GitHub shows an image title only as a hover tooltip. Leave an existing visible caption line where it is. Turning it into a title (and removing the visible line) is a content move: do it only if the author wants EPUB figures with captions.

#### 8.3 Alt text (MB402)

- Markdown `![](x.png)` has no alt text. HTML `<img>` without an `alt` attribute has none either. HTML `alt=""` marks a decorative image and is allowed; Markdown has no decorative form. The EPUB declares `alternativeText` only when every image has alt text.
- Open the image and look at it before writing. Describe what it shows that matters at this point of the text: the subject; for charts and diagrams, the type and what the axes, boxes, or arrows represent, and the main point visible in the picture.
- Use only what is visible in the image or stated in the surrounding text. Add no numbers, names, or claims.
- One or two sentences, usually under 150 characters. Write in the book's language. Do not start with "Image of", and do not repeat the caption word for word.
- Screenshots: name the program and what is on screen. People: name them only if the text does. Inline icons: the word the icon stands for ("Markdown icon").
- List every alt text you wrote in the report.

#### 8.4 Formats and sizes

Supported: JPEG for photos, PNG for diagrams and screenshots, SVG for vector art (text as real text, no scripts), GIF, WebP. Errors (MB403): BMP, TIFF, HEIC, HEIF, PSD, AVIF, ICO, EPS, PDF. Other extensions give a warning.

Size: MB404 warns above 3200 px on the long side or 5 MB per file. Scale to at most 3200 px; never upscale.

Pillow (usually available):

```python
from PIL import Image
im = Image.open("images/photo.bmp")
im.thumbnail((3200, 3200))                                       # keeps the ratio, only shrinks
im.save("images/photo.png", optimize=True)                       # diagrams, screenshots, transparency
# im.convert("RGB").save("images/photo.jpg", quality=85, optimize=True)   # photos
```

ImageMagick 7 (`magick`; with ImageMagick 6 use `convert`):

```
magick in.bmp out.png                                             # lossless
magick in.tif -quality 88 out.jpg                                 # photo
magick -density 200 "in.pdf[0]" out.png                           # first PDF page, needs Ghostscript
magick in.jpg -resize "3200x3200>" -quality 85 -strip out.jpg     # shrink only if larger
magick identify -format "%m %wx%h %[colorspace]\n" images/*       # format, size, colorspace
```

After converting, update every reference to the new file name (`git grep -n -F "photo.bmp"`). Remove the old file only when nothing references it any more, and mention it in the report.

- MB405 (info, animated GIF): readers show the first frame. Check that it makes sense alone, or ask for a still image.
- MB405 (warning, SVG with `<script>` or `<foreignObject>`): many readers drop them. Exports from diagrams.net and Mermaid often put text in `foreignObject`. Re-export as PNG, or as SVG with plain text elements.

#### 8.5 Remote images (MB401) and badges

An EPUB cannot load images from the web. The build puts a text placeholder `[image: alt]` in their place and fails the images gate. Decide per image:

1. A file of this repository: use its relative path (8.1).
2. The author's own uploads (`https://github.com/user-attachments/assets/...`, `https://user-images.githubusercontent.com/...`): download them into `images/` with descriptive names.
3. Third-party images: download only when the license allows reuse in a book (public domain, CC0, CC BY, CC BY-SA, most works of US federal agencies such as NASA, or explicit permission). Note the source and license in the report. If the license requires attribution and there is no credit line near the image, ask the author how to credit it. Unknown license: do not download; ask.
4. Badges (shields.io, CI status, chat, download counters): they mean nothing in an ebook. Keep them on GitHub and remove them from the EPUB with `drop_lines` (see Snippets), or delete them if the author agrees. `drop_lines` removes whole lines, so badges must sit on lines of their own.

```
curl -fL --retry 3 -o images/fig-03-dust-storm.jpg "https://example.org/storm.jpg"
file images/fig-03-dust-storm.jpg      # the real format must match the extension
```

Then replace the URL with the relative path and keep the alt text.

#### 8.6 Cover (MB410 to MB412)

- JPEG or PNG, RGB, 1600x2560 px (ratio 1.6). `check` warns (MB411) below 1400 px on the short side, outside a 1.4 to 1.7 height-to-width ratio, or for a CMYK file (the build converts it). Other readable formats (GIF, WebP) are converted to JPEG with an MB412 warning; a missing or unreadable file is an MB412 error. Transparent PNGs are flattened onto white, and EXIF rotation is applied.
- Put it at `images/cover.jpg`, where it is found automatically, or set `cover.image`.
- Fit the author's artwork: `magick art.png -resize "1600x2560^" -gravity center -extent 1600x2560 -quality 90 images/cover.jpg`. This crops; check that no title text is cut off, and ask the author when the artwork's ratio is far from 1.6.
- No artwork: leave `cover.image` empty. The build generates a typographic cover from the title, subtitle, and authors, styled by `cover.background`, `cover.foreground`, and `cover.accent`, and saves it as `dist/<slug>-cover.jpg` (1600x2560). Do not create artwork or use stock images without the author's approval.
- `dist/<slug>-cover.jpg` is always the full-size cover for store uploads; the EPUB embeds a copy scaled to `cover.embed_height`.

### 9. Fix wide tables

- Use GitHub pipe tables with a header row.
- Up to about 6 columns read well on a phone. MB600 fires at 9 or more (`wide_table_warn`) unless the file is a card file.
- Cards: list the file under `options.cards.files`, spelled as in `files:`. Every table in that file with at least `cards.min_columns` (default 9) columns becomes cards: one block per row, the first `title_columns` cells joined as the card heading, every other non-empty cell as a "Column: value" line. Lower `min_columns` (for example to 7) to card narrower tables; it applies to all listed files.
- Row anchors: write `<a id="r07"></a>R07` in the first cell; the first anchor becomes the card's id.
- Card files are exempt from the word-count gate.
- The author may prefer to split, transpose, or move a table to an appendix. Offer these; do not do them unasked.
- Layout tables (images in a grid, badges in cells) turn into data tables with icon-sized images. Propose separate figures instead.

### 10. Fix charts

- Mermaid blocks (```` ```mermaid ````) are rendered to PNG images (theme `neutral`, 18 px font, scale 2). GitHub renders the same blocks natively.
- Alt text comes from a `title` line (`title Build plan`) or `title:` front matter in the chart, or, without one, from node labels (`A[Draft] --> B[Check]` gives "Chart: Draft, Check"), after `mermaid_alt_prefix`. A chart with neither gets only "Chart". `mermaid_alt:` in `files:` sets one alt text for every chart in that file, so use it only in files with a single chart.
- `mdbindery check .` test-renders every chart; a failure is MB701 with the parse error. Paste the chart into https://mermaid.live to debug. Fix syntax only; keep the chart's content.
- Without mermaid-cli (MB700, or `doctor` says it cannot render), charts become a quoted note that links to the online edition through `source_url`; the charts gate reports `warn`, not a pass.
- After building, look at the chart pages in the preview. Wide left-to-right flowcharts shrink to unreadable on a phone (`flowchart TB` helps); Gantt charts with daily ticks become a smear (`axisFormat`, `tickInterval`). These are presentation changes: make them only if the author agrees.
- Gantt charts get `todayMarker off` automatically, so builds are reproducible.
- Other diagram fences (`plantuml`, `dot`, `geojson`, `topojson`, `stl`) are not rendered; they appear as code. Ask the author for exported PNG or SVG files.

### 11. Math and dollar signs

- `$...$` in text and ```` ```math ```` blocks become MathML (MB710 counts them). Some readers show MathML poorly; check the preview.
- Dollar signs in prose can pair up into a "formula": in ``*$HOME/.cargo/bin*. Ensure that this directory is in your `$PATH` `` everything between the two dollar signs becomes math. MB711 (warning) shows such text, and the trial build adds MB711 for pandoc's `Could not convert TeX math` warnings. Escape the literal dollar signs (`\$HOME`), or put each shell variable or path in backticks (`` `$HOME/.cargo/bin` ``); a code span after the first dollar sign does not stop the formula.
- Prices such as `$5 and $10` are not math (a closing `$` must follow a non-space character), so leave them.

### 12. Clean up HTML

Markdown first. Replace HTML only where the table says so, and keep GitHub rendering equivalent. HTML is converted at any depth: in block quotes, list items, and divs too. Tags in code and in comments are never touched.

| HTML | What mdbindery does | Action |
|---|---|---|
| `<br>`, `<br/>` | line break | keep |
| `<sup>`, `<sub>`, `<b>`, `<strong>`, `<i>`, `<em>` | superscript, subscript, bold, italic | keep, or use `**` and `*` |
| `<u>`, `<ins>`, `<s>`, `<del>`, `<strike>` | underline, strikethrough | keep |
| `<kbd>`, `<code>` | code span; tags inside are flattened to text | keep |
| `<q>`, `<small>`, `<mark>` | quoted text, smaller text, highlighted text | keep |
| `<a href="...">` | link, resolved like a Markdown link | keep, or `[text](href)` |
| `<a id="x"></a>`, `<a name="x"></a>` | anchor | keep |
| `<img src alt title>` | image (step 8); entities in attributes are decoded; `width` is kept only on a block image | keep with a local `src` and an `alt` |
| `<p align="center">`, `<center>`, `<span>`, `<font>`, `<abbr>`, `<cite>`, `<dfn>`, `<time>`, `<var>`, `<samp>`, `<big>`, `<tt>` | tag removed, content kept | nothing required |
| `<div class="x">` alone on a line, Markdown inside, `</div>` alone on a line | a styled block with class `x` | keep |
| other `<div>` wrappers | content kept | keep |
| `<details>`, `<summary>` | content always shown; the summary becomes a loose line of text | replace with a heading or a bold lead-in; ask whether hidden content (answers, spoilers) belongs in the book |
| `<figure>`, `<figcaption>` | a figure: the image as a block, the `<figcaption>` as its caption | keep; the `<img>` needs a local `src` and an `alt` |
| `<picture>`, `<source>` | the fallback `<img>` is used | make sure the `<img>` has a local `src` and an `alt` |
| `<table>`, `<ul>`, `<ol>`, `<li>`, `<blockquote>`, `<pre>`, `<dl>`, `<hr>`, `<h1>` to `<h6>` | converted to the same structure | keep, or convert to Markdown when simple |
| `<!-- comments -->` | ignored everywhere, with their contents | keep |
| `<script>`, `<iframe>`, `<object>`, `<embed>`, `<form>`, `<input>`, `<button>`, `<select>`, `<textarea>`, `<style>`, `<video>`, `<audio>`, `<canvas>` | removed; MB500 error | remove; replace an embedded video or map with a link, a canvas or inline media with a still image (ask about the wording) |
| any other tag (`<Listing>`, or `Box<T>` in prose) | tag removed, content kept; MB500 warning | when the tag is meant as text, put it in backticks or write `&lt;T&gt;`; otherwise nothing required |
| `<YOUR_NAME>` and other names with `_` | not a tag: stays as text | nothing required |

MB501 (info, after analysis) lists the tags that will be dropped per file. Unclosed `<div>` or other broken HTML blocks can swallow the Markdown that follows them; that shows up as MB902 (text lost) in the trial build.

### 13. mdBook books

mdbindery recognizes an mdBook (MB130): a `book.toml` in the book folder or the folder `source_dir` names (its `src`, default `src/`, becomes the book folder) or a `SUMMARY.md` with `book.toml` one level up. Title, authors, description, and language come from `book.toml`, and the reading order from `SUMMARY.md`; files it does not list are left out. Check and build from the folder that holds `book.toml`. A `SUMMARY.md` without any `book.toml` (GitBook and similar tools) only sets the reading order: no MB130, and Rust code stays as written.

- `{{#include}}` paths may leave `src/` (`../listings/...`) but must stay inside the repository: the git checkout, or outside git the folder with `book.toml`.
- Directives are expanded in every file: `{{#include path}}`, with `:N`, `:N:M`, `:N:`, `::M`, or `:anchor` (the lines between `ANCHOR: anchor` and `ANCHOR_END: anchor`); `{{#rustdoc_include ...}}` and `{{#playground ...}}` like `include`; `{{#title ...}}` is dropped; `\{{#include ...}}` stays as literal text. Paths are relative to the Markdown file. A missing file or anchor is MB131 (error) and fails the `includes` gate: fix the path, or ask the author what the listing should contain.
- In `rust` code blocks, lines starting with `# ` are hidden and `##` becomes `#`, as mdBook does.
- `.html` links between chapters resolve to the `.md` files (MB205).
- Links to other published books and API docs (`../std/io/index.html`, `../reference/...`) are MB204 errors with a GitHub `source_url`. Set `source_url` to the published book (`https://doc.rust-lang.org/book/` for the Rust book) so they stay web links (MB203).
- mdBook-specific tags such as `<Listing>` are dropped with their content kept (MB500 warning); nothing to do.
- Other mdBook preprocessors are not run. Their syntax stays in the text; tell the author.

### 14. License, metadata, and language

- Rights: `metadata.rights` is filled from a LICENSE, LICENSE.md, LICENSE.txt, LICENCE, or COPYING file in the book folder, then at the repository root. Recognized: SPDX lines, Creative Commons licenses with version and variant (CC BY, BY-SA, BY-NC, BY-NC-SA, BY-ND, BY-NC-ND, CC0), GNU GPL, LGPL, AGPL, FDL, MIT, Apache 2.0, BSD, MPL 2.0, The Unlicense. MB123 means none was found: ask the author, and never choose a license yourself. A code license (MIT) may not cover the text; ask when in doubt.
- MB121 (no author): take the name from `book.toml`, the README, or the LICENSE, and confirm it with the user.
- MB120 and MB122 (title and language inferred): set `metadata.title` and `metadata.lang` explicitly. `lang` is a BCP 47 tag (`en-US`, `en-GB`, `ru`, `de`, `pt-BR`, `ja`) that drives hyphenation and the reader's dictionary; without it mdbindery guesses only between `ru` and `en-US`.
- Non-English books: set `options.mermaid_alt_prefix`, `options.accessibility_summary` (built in only for English and Russian), `options.reference_headings` and `options.reference_heading_new` if the reference heading is not in the default list, and `slug` if the author wants an ASCII file name.
- `description` and `subjects` help store listings; propose them, and let the author decide.
- Typography stays exactly as written: quotes, «guillemets», dashes, non-breaking spaces. mdbindery never changes them, and neither should you unless the author asks.
- Encoding (MB105 error): UTF-8 is required, and the build stops on any other encoding. Find the real encoding (`file -i ch.md`), convert (`iconv -f WINDOWS-1252 -t UTF-8 ch.md > ch.tmp && mv ch.tmp ch.md`, with the encoding the file actually has), and check that accented letters read correctly. A byte order mark and CRLF line endings are handled (info only); leave them.
- Code blocks: tag fences with a language for highlighting. Long lines (MB720) wrap on phones; code is content, so leave it unless the author wants it reflowed.

### 15. Trial build, build, preview

1. Rerun the check after each batch of fixes until it has 0 errors, and 0 warnings where feasible. Every warning that remains needs a reason in the report: an author decision, or a known limitation.
2. Run the trial build (EPUBCheck, Ace, word count, and every other gate; codes MB900 to MB904). It builds in a temporary folder, never writes into the config, and runs only when the static check has no errors:

   ```
   mdbindery check . --build --json "${TMPDIR:-/tmp}/mdb-check.json" -q
   jq -r '.facts.trial_build' "${TMPDIR:-/tmp}/mdb-check.json"      # passed (N KB) / failed: <gates> (N KB)
   ```

3. Build for real:

   ```
   mdbindery build                 # dist/<slug>.epub, dist/<slug>-cover.jpg, dist/reports/
   mdbindery build --no-ace        # faster while iterating; the final build runs Ace
   mdbindery build --keep-work     # keeps intermediate files (path printed) for debugging
   ```

   Exit codes: 0 prints `BUILD OK`; 1 prints `BUILD FAILED: <gates>`; 2 is a configuration or input error (`config error:` or `build error:` on stderr). The first build writes the identifier into `mdbindery.yaml`. Details are in `dist/reports/build.json` (`failed_gates`, `gates`), `dist/reports/build.log`, `dist/reports/epubcheck.json`, and `dist/reports/ace/report.html`.

4. When a gate fails:

   | Gate | Where to look | What to do |
   |---|---|---|
   | `links` | `UNRESOLVED link in A to B#x`, `LINK to a missing file in A: path` | step 6 |
   | `images` | `IMAGE missing: ...`, `IMAGE remote: ...`, `IMAGE outside: ...` | step 8 |
   | `charts` | `CHART in ... failed to render` | step 10 |
   | `includes` | `INCLUDE in ... not expanded (...)` | step 13 |
   | `epubcheck` | the message id and the path inside the EPUB (`EPUB/text/chNNN.xhtml`; with one `#` heading per file and `split_level: 1`, `ch001` is the first file of the reading order); `NOT RUN` means no Java 11+ | fix the source at that place; `mdbindery install-tools` for Java |
   | `ace` | `dist/reports/ace/report.html` | fix the source (alt text, headings, language); waive a rule in `ace_waivers` only with approval |
   | `wordcount` | `word count: FAILED: ... FILE A -> B words (+x%)` | text was lost (negative) or duplicated (positive): run `mdbindery build --keep-work`, compare `kNN.md` in the printed folder (the prepared source of the file with key `kNN`) with the chapter in the EPUB; usual causes are unclosed HTML, a tag that swallows text, or HTML around Markdown |

5. Take phone-size screenshots and look at every one:

   ```
   mdbindery preview dist/<slug>.epub "${TMPDIR:-/tmp}/mdb-shots"
   mdbindery preview dist/<slug>.epub "${TMPDIR:-/tmp}/mdb-shots" text/ch003.xhtml "text/ch004.xhtml#k03-the-storm-case" --full
   ```

   Without page arguments it captures the cover, title page, table of contents (`nav.xhtml`), `text/ch001.xhtml`, and `text/ch002.xhtml`. With one `#` heading per file and `split_level: 1`, `text/ch001.xhtml` is the first file of the reading order, `ch002` the second, and so on; ids carry the `kNN-` prefix of the file's position. `--full` captures the whole page; `--width` and `--height` set the viewport (default 412x915). A page that does not exist is an error that lists the pages.

6. Suggest adding `dist/` to `.gitignore`.

### 16. Final verification

Before you report the book as done, confirm each point:

- [ ] `mdbindery check .` exits with 0; every remaining warning has a reason in the report.
- [ ] `mdbindery check . --build` reports `Trial build: passed (N KB)`.
- [ ] `mdbindery build` (with Ace) prints `BUILD OK`, and `build.json` has no gate at `skipped` or `warn` (a `warn` on `charts` or `ace` means a missing tool).
- [ ] `mdbindery.yaml` has the identifier the first build wrote, and the title, authors, language, and rights the author confirmed.
- [ ] The reading order in `files:` matches the book's intended order; nothing that belongs in the book is left out, and no navigation or translation file is in.
- [ ] The screenshots show the cover, one table of contents entry per chapter with its sections, figures at full width with captions, cards, readable charts, reference lists and citation links, endnotes, and no raw Markdown or HTML and no icon-sized pictures.
- [ ] The files still render on GitHub: links and images are relative, and nothing GitHub-only was deleted without approval.
- [ ] Nothing was committed, and `dist/` and the reports are not staged.

## Check codes and fixes

Severity: E error, W warning, I info (note). Only errors make `check` exit with 1.

| Code | Sev. | Meaning | Fix |
|---|---|---|---|
| MB001 | W | pandoc not installed (or older than 3.8); links were not verified | `mdbindery install-tools`, then check again |
| MB100 | E | no Markdown files | chapters as `.md` in the book folder or `chapters/`, or list them under `files:` |
| MB101 | I | no `mdbindery.yaml` | `mdbindery init`, then complete it (step 4) |
| MB102 | E | config cannot be loaded: invalid YAML, unknown top-level key, invalid value, a path outside the repository (URL check) | fix the key or value named in the message |
| MB102 | W | unknown nested config key, or unknown key in a `files:` entry | correct the spelling ("did you mean" hint) |
| MB103 | E | a file in `files:` does not exist | fix the name, or remove the entry |
| MB104 | I | a Markdown file is not in the reading order | add it to `files:` if it belongs in the book |
| MB105 | E | file is not valid UTF-8; the build stops on it | convert to UTF-8 (step 14) |
| MB105 | I | byte order mark, or CRLF line endings | nothing needed |
| MB106 | W | no level-1 heading; the message says which title the build will use | add or promote a `#` heading, or set `title:` (step 5) |
| MB107 | W | several `#` headings in one file | demote the extra ones, or propose a split |
| MB107 | I | several files start with the same heading | use the `drop_lines` pattern from the fix text, and give the README a `title:` |
| MB108 | W | a heading level is skipped | raise the heading to the missing level |
| MB109 | W | empty file | remove it from `files:` |
| MB110 | W | content above the chapter title (moved below it by the build) | move the `#` heading to the top, or drop badges with `drop_lines` |
| MB111 | W | YAML front matter is ignored | move the title into the file or the config; ask before removing |
| MB120 | I | title inferred | set `metadata.title` |
| MB121 | W | no author | set `metadata.authors` after asking the user |
| MB122 | I | language inferred | set `metadata.lang` |
| MB123 | W | no license or rights statement | set `metadata.rights` or add a LICENSE (the author chooses) |
| MB124 | I | no identifier yet | keep the empty `identifier:` line; the first build fills it |
| MB125 | I | reading order inferred (the message says from what) | check it, then write it into `files:` |
| MB126 | W | a table of contents file is in the reading order | remove it from `files:` |
| MB130 | I | mdBook layout recognized | see step 13 |
| MB131 | E | mdBook directive not expanded (file or anchor missing, or outside the repository) | fix the path or anchor (step 13) |
| MB200 | E | link to an anchor that does not exist | fix the fragment, or add `<a id>` at the target |
| MB201 | W | anchor matched only approximately | use the anchor named in the message |
| MB202 | W | link to a file that is not in the book; it becomes plain text | set `source_url`, or add the file to `files:` |
| MB202 | I | URL check: the link will point to the online repository | set the `source_url` given in the fix text |
| MB203 | W | link to a page that is not in the repository; with a website `source_url` it stays a web link, not checked | make sure the page exists on the site |
| MB204 | E | link to a file that does not exist | fix the path; for web pages set `source_url` to the site; ask before removing the link |
| MB205 | I | web-style links (`.html`, `index.html`, a folder with `/`) resolved to book files | nothing needed |
| MB300 | W | reference defined but never used | report; delete only with approval |
| MB301 | E | one label defined twice with different URLs | keep one when they are the same resource; otherwise ask |
| MB302 | W | `[n]` looks like a citation, but this file has no `[n]:` | copy the definition if numbering is global; otherwise ask; escape `\[n\]` if it is not a citation |
| MB303 | I | citations but no reference heading; `## References` will be added at the end | add the heading above the definitions to control the position |
| MB304 | E | footnote reference without a definition | fix the label typo, or ask for the note text |
| MB305 | W | footnote defined but never used | ask where the marker belongs |
| MB306 | I | citation without a title | add `"Author, Title, Publisher, year"` from the source |
| MB400 | E | image file not found, or empty source | fix the path (relative to the file, exact case) |
| MB401 | E | remote image, or an unsupported image URL | local copy, download with license check, or `drop_lines` for badges (8.5) |
| MB401 | I | image URL of this repository; the build uses the local file | use the relative path from the fix text |
| MB402 | W | image without alt text | write alt text (8.3) |
| MB403 | E | unsupported format (BMP, TIFF, HEIC, HEIF, PSD, AVIF, ICO, EPS, PDF) | convert to JPEG or PNG (8.4) |
| MB403 | W | unusual image extension | use JPEG, PNG, GIF, SVG, or WebP |
| MB404 | W | image over 3200 px or over 5 MB | scale to 3200 px on the long side, JPEG quality 85 |
| MB405 | I | animated GIF | make sure the first frame works alone |
| MB405 | W | SVG with scripts or `foreignObject` | re-export as PNG or plain SVG |
| MB406 | W | image outside the book folder | move it into the book's `images/` |
| MB406 | E | URL check: image outside the repository | move it into the repository |
| MB410 | I | no cover image; one will be generated | add `images/cover.jpg` (1600x2560), or accept the generated cover |
| MB411 | W | cover under 1400 px on the short side, ratio outside 1.4 to 1.7, or CMYK | resize or crop to 1600x2560, RGB (8.6) |
| MB412 | E | cover file not found, or cannot be read | fix `cover.image`, or save the cover again as JPEG |
| MB412 | W | cover is not JPEG or PNG; it will be converted | provide a JPEG to control the result |
| MB500 | E | `<script>`, `<iframe>`, `<object>`, `<embed>`, `<form>`, `<input>`, `<button>`, `<select>`, `<textarea>`, `<style>`, `<video>`, `<audio>`, `<canvas>` | remove; replace with a link or a still image (step 12) |
| MB500 | W | unknown tag: dropped, content kept | backticks or `&lt;...&gt;` when the tag is meant as text |
| MB501 | I | HTML without an EPUB equivalent will be dropped | confirm nothing readers need is lost |
| MB600 | W | table with 9 or more columns | list the file under `options.cards.files`, or propose a split (step 9) |
| MB700 | W | mermaid-cli missing; charts would be placeholders | `mdbindery install-tools` (without `--no-node`) |
| MB701 | E | a Mermaid chart failed to render | fix the syntax (https://mermaid.live) |
| MB710 | I | math found; MathML varies between readers | check it in the preview |
| MB711 | W | text between dollar signs is read as a formula, or pandoc could not convert TeX math | escape literal dollar signs as `\$` (step 11) |
| MB720 | I | code lines over 90 characters | usually nothing; code is content |
| MB900 | E/W | EPUBCheck message (ERROR and FATAL are errors) | read the id and path; the path is inside the EPUB (`EPUB/text/chNNN.xhtml`) |
| MB901 | E/W/I | Ace violation (critical or serious are errors, waived rules are notes) | open `dist/reports/ace/report.html`; fix the source; waive a rule only with approval |
| MB902 | E | text lost or added in conversion; the message names the files | step 15, `wordcount` row |
| MB903 | E | analysis or trial build failed | read the message; common causes are invalid YAML front matter and malformed HTML; rerun `mdbindery build --keep-work` for the full error |
| MB904 | E | a trial-build gate failed (for example `epubcheck` when Java is missing) | read the gate name and detail; step 15 |

## Known limitations

Verified in mdbindery 0.1.0. Keep them in mind so you do not chase phantom problems or miss real ones.

- MB106 and MB110 are warnings because the build repairs these files; fix them anyway, since the repaired titles come from file names or promoted headings the author did not choose. MB107 is a warning because the book still builds, with one more table of contents entry for each extra `#` heading.
- `facts.totals.images` estimates image kinds line by line (8.2); the preview decides.
- An image outside the book folder is only a warning for a local book, and the build embeds it.
- Outside a git checkout, `/` in links and images means the book folder (for an mdBook, the folder with `book.toml`), and mdBook includes cannot leave that folder.
- Headings with emoji cannot be link targets on GitHub and in the EPUB at the same time.
- MB302 and MB711 are heuristics: bracketed numbers in prose and dollar signs can trigger them.
- `check --no-render` also makes the trial build use chart placeholders; run once without it.
- The word-count gate compares per-file counts: text moved within a file is not detected.
- A private repository can be checked by URL only with your own git credentials; git never prompts.
- mdBook preprocessors other than the built-in directives are not run.

## Snippets

Config template (`init` writes the same shape; the first build fills `identifier:`):

```yaml
slug: my-book
output_dir: dist
source_url: https://github.com/OWNER/REPO/blob/main/

metadata:
  title: My Book
  subtitle: A subtitle, or leave empty
  authors: [First Last]
  lang: en-US
  # identifier: left empty, a permanent urn:uuid is written here on the first build
  identifier:
  date: git
  rights: Text licensed under CC BY 4.0
  description: One or two sentences for store listings.
  subjects: [Topic one, Topic two]

cover:
  image: images/cover.jpg

files:
  - file: README.md
    role: front
    title: About this book
    drop_sections: [Contributing]
  - 01-first-chapter.md
  - 02-second-chapter.md
  - file: appendix-a-glossary.md
    role: appendix

options:
  citations: refdefs
  toc_depth: 2
  drop_lines:
    - '^\s*\[!\[[^\]]*\]\(https?://'                    # linked badges: [![...](https://...)](...)
    - '^\s*!\[[^\]]*\]\(https://img\.shields\.io/'      # plain shields.io badges
  cards:
    files: [appendix-a-glossary.md]
    min_columns: 9
    title_columns: 1
```

Non-English additions (German example; `reference_headings` replaces the default list):

```yaml
slug: mein-buch
metadata:
  lang: de
options:
  mermaid_alt_prefix: Diagramm
  reference_headings: [Quellen, Literatur, Anmerkungen]
  reference_heading_new: Quellen
  accessibility_summary: Diese Publikation hat ein navigierbares Inhaltsverzeichnis und eine logische Lesereihenfolge; Überschriften, Listen und Tabellen sind strukturell ausgezeichnet, Bilder haben Textalternativen.
```

Citations and footnotes:

```markdown
Solar power at Mars is 43% of Earth's [1]. The handbook [Milchin] covers this.[^scale]

## References

[1]: https://nssdc.gsfc.nasa.gov/planetary/factsheet/marsfact.html "NASA NSSDC, Mars Fact Sheet"
[Milchin]: https://example.org/milchin "Milchin A. E., Handbook for Publishers and Authors, 2014"

[^scale]: At the mean orbital distance.
```

`[Milchin]` becomes a citation only with `citation_labels: all`; otherwise it is a plain link.

Images:

```markdown
The icon ![Markdown icon](images/icon.png) sits in the sentence.

![Four boxes joined by arrows: Markdown, Checks, Pandoc, EPUB 3](images/pipeline.png)

![Dust storm over a habitat, seen from orbit](images/storm.jpg "The 2031 storm, day 12")

![A desk under a night sky full of stars](images/night-desk.jpg "full-page: Writing at night")

<p align="center"><img src="images/logo.png" alt="Project logo: a bound book with a gear on the cover" width="300"></p>
```

Anchors:

```markdown
<a id="r07"></a>
## R07. Water recycling

| ID | Item | ... |
|---|---|---|
| <a id="r08"></a>R08 | Power margin | ... |

See [row R08](04-data.md#r08) and [recycling](04-data.md#r07).
```

GitHub anchors for every heading of a file (skips code fences, numbers duplicates; emoji follow GitHub, not pandoc). Save it outside the repository, for example as `/tmp/anchors.py`, and run `python3 /tmp/anchors.py 02-baseline.md`:

```python
import re, sys, unicodedata

def anchor(text):
    t = re.sub(r'!?\[([^\]]*)\]\([^)]*\)', r'\1', text).replace('`', '').lower()
    t = ''.join(c for c in t if c in ' -_' or unicodedata.category(c)[0] in 'LMN')
    return t.replace(' ', '-')

seen, fence = {}, None
for line in open(sys.argv[1], encoding='utf-8'):
    m = re.match(r'^ {0,3}(`{3,}|~{3,})', line)
    if m:
        fence = None if fence and m.group(1)[0] == fence else (fence or m.group(1)[0])
        continue
    h = None if fence else re.match(r'^ {0,3}#{1,6}\s+(.*?)\s*#*\s*$', line)
    if h:
        a = anchor(h.group(1))
        n = seen.get(a, 0); seen[a] = n + 1
        print(f"#{a}{'-' + str(n) if n else ''}\t{line.strip()}")
```

## Final report template

Give the user this report at the end, filled in. Keep it factual; list only what happened.

```markdown
## mdbindery preparation report

Check: N errors, N warnings, N notes (at the start: N, N, N).
Trial build: passed (N KB). Build: BUILD OK, or failed gates: ...
EPUB: dist/<slug>.epub (N KB). Screenshots reviewed: <folder>.

### What changed
- Files and order: <old name> -> <new name>, ...; left out of the book: ...
- Configuration: mdbindery.yaml created or updated; keys set: ...
- Headings: <file>: ...
- Links and anchors: N links fixed in <files>; anchors added: ...
- Citations: ...
- Images: moved ..., converted ..., scaled ..., downloaded <url> (license, source) ...
- Cover: ...
- Tables, charts, math, HTML: ...

### Needs your decision
1. <question>, options: <a> / <b>. Until you decide: <current state>.

### Please review text I wrote
- Alt text: <file>:<line> "<text>"
- Headings added: ...
- Reference titles added from the sources: ...

### Findings left as they are
| Code | File:line | Why |
|---|---|---|

### Not committed
All changes are in the working tree. Suggested commits: renames; links and headings; images; configuration.
```
