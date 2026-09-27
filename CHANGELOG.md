# Changelog

## 0.1.1 (2026-09-26)

Fixes from an external audit of 0.1.0.

- A repository checked by URL can no longer read files outside its checkout through symlinks. Symlinks that point outside are removed after the fetch (new warning MB407), and chapters, the configuration file, `files:` entries, the cover, license files, and images are all checked after following links. Same-repository image URLs get the same check.
- Cards keep every table row: header rows after the first, rows in body heads, and footer rows were lost before. Files with cards are no longer exempt from the word count; the gate subtracts the labels cards repeat and compares the rest exactly.
- Alt text is judged per image in HTML blocks, so one `<img alt>` no longer vouches for its neighbors. The default accessibility summary now says when some images have no text alternative, matching the `alternativeText` feature.
- `metadata.date` must be a real calendar date (`YYYY`, `YYYY-MM`, or `YYYY-MM-DD`), and numeric options reject `.nan` and `.inf`.
- mdBook includes report cycles (`include cycle: a.md -> b.md -> a.md`), nesting deeper than 10 levels, more than 5000 includes, or more than 20 MB of included text in one file, instead of stopping silently.
- A build that stops with an error still writes `reports/build.json` (`failed_stage`, `error`, and whether the EPUB in the folder is stale) and `build.log`. Every `build.json` records `provenance` (tool versions, source commit, options), `timings`, `skipped_gates`, and `warning_gates`.
- Every external program runs with a time limit and is stopped together with its child processes on timeout or Ctrl+C. `MDBINDERY_TIMEOUT_SCALE` raises all limits.
- `check --build` reuses its analysis for the trial build, so each file is converted and each chart rendered once.
- `preview` treats the EPUB as untrusted: scripts are off, pages load only the EPUB's own files, oversized archives are refused, and a sandbox failure is no longer remembered for later runs.
- `install-tools` updates each tool through a staging folder and keeps the working version until the new one starts; one install runs at a time per tool home.
- The word-count log states what it checks: `every file within 2% or 25 words of its source`.
- Releases are published only after the full CI suite passes on the tag and the built wheel installs and builds the sample book on Linux, macOS, and Windows.
- The content tests run with pandoc alone; only the EPUBCheck integration test needs EPUBCheck.
- HTML `id` attributes that pandoc's HTML reader drops (for example on `<pre>`) stay reachable as link targets.

## 0.1.0 (2026-09-26)

First public release.

- `mdbindery build`: turns a folder or GitHub repository of Markdown chapters into an EPUB 3, one chapter per file. Supports links between files with GitHub anchors, numbered citations linked to a generated reference list, footnotes as numbered endnotes, figures and full-page images, a supplied or generated cover, Mermaid charts rendered to PNG, wide tables as cards, GitHub alerts, math as MathML, code highlighting, and GitHub-style HTML.
- Repairs for common repository layouts: a chapter title for files without a level-1 heading, content above the title moved below it, anchors moved out of headings, links to files outside the book pointed at `source_url` (or kept as text), `.html` links resolved to `.md` files, and image URLs of the same repository replaced by the local files.
- Reading order from `files:` in `mdbindery.yaml`, or inferred from a table of contents file, the README's links, or the file names (with front and back matter recognized).
- mdBook books: `book.toml`, `SUMMARY.md`, `{{#include}}` and related directives, and hidden lines in Rust code.
- Gates that fail the build: links, images, charts, includes, EPUBCheck, DAISY Ace, and a per-file word count that catches lost or duplicated text. Output is reproducible, and the EPUB carries accessibility metadata.
- `mdbindery check`: a dry run for a local folder, a GitHub URL, or another git URL, with a Markdown or JSON report (MB codes, file, line, and a fix for each finding), a suggested configuration, and an optional trial build.
- `mdbindery init`, `install-tools`, `doctor`, and `preview` (phone-size screenshots).
- Installers for Linux, macOS, and Windows that need nothing preinstalled and no admin rights. uv, pandoc, EPUBCheck, and Node.js downloads are pinned and checksum-verified.
- Packages on PyPI, a Homebrew tap (`sagol/tap`), and a GitHub Action (`uses: sagol/mdbindery@v0.1.0`) that installs mdbindery and its tools with caching.
- Agent skills for running mdbindery and for preparing a repository for it.
