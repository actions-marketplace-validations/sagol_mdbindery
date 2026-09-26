# Changelog

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
