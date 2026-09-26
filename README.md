# mdbindery

Turn a folder or GitHub repository of Markdown chapters into a validated EPUB 3 ebook.

mdbindery is built for books written the GitHub way: one Markdown file per chapter, relative links between files, images in the repository, citations as `[1]` with reference definitions. The book stays readable on GitHub, and the EPUB passes EPUBCheck and the DAISY Ace accessibility check without hand editing.

```
mdbindery check https://github.com/OWNER/REPO     # what to fix, file by file and line by line
mdbindery build path/to/your-book                 # dist/<slug>.epub, validated
```

## What it does

- Links between chapters, including links to headings in other files and custom `<a id>` anchors, become internal EPUB links. A link that has no target fails the build.
- Citations written as `[1]` with `[1]: url "Title"` definitions (invisible on GitHub) become visible numbered reference lists with working links.
- Images become inline icons, block images, figures with captions (the image title), or full-page images (`"full-page"` title). The cover can be any common image format, or mdbindery generates a typographic one. Missing and remote images fail the build.
- Mermaid charts become PNG images with alt text taken from the chart.
- Wide tables can become cards (one block per row), so they read on a phone.
- Footnotes become numbered endnotes; math becomes MathML; GitHub alerts, task lists, and code blocks (with monochrome highlighting) are supported.
- Raw HTML from GitHub READMEs (`<br>`, `<sup>`, `<img>`, `<p align>`, `<details>`, and more) becomes valid EPUB markup; tags with no EPUB equivalent are removed and reported.
- mdBook books work as they are: `book.toml` gives the metadata, `SUMMARY.md` the reading order, and `{{#include}}` directives are expanded.
- The book gets its title, subtitle, authors, language, rights, a permanent identifier, and schema.org accessibility metadata.
- Builds are reproducible: the same commit built twice with the same tools gives byte-identical files.

## Checking and validation

`mdbindery check` is a dry run on a local folder or a repository URL. It changes nothing and prints a Markdown report: every problem with its code, severity (error, warning, or note), file, line, and fix; the reading order and where it came from; and, for a book without one, a suggested `mdbindery.yaml`. `--build` adds a trial build with all the gates, and `--json FILE` writes the same report as JSON. The exit status is 0 when there are no errors, 1 when there are, and 2 when the target cannot be read.

`mdbindery build` writes the EPUB and then runs the gates: links, images, charts, mdBook includes, EPUBCheck, Ace, and a word count that catches text lost in conversion. If any gate fails, the build ends with `BUILD FAILED` and exit status 1; the EPUB is still written so you can inspect it. A missing Ace (after an install with `--no-node`) is a warning, not a failure.

## Supported inputs

- A folder of Markdown files, one per chapter. The reading order comes from `files:` in `mdbindery.yaml`, or else from a `SUMMARY.md` or other table-of-contents file, from the README's links when the chapter file names are not all numbered, or from the file names.
- A GitHub repository. `mdbindery check` accepts `https://github.com/OWNER/REPO`, `.../tree/BRANCH/FOLDER` for a book in a subfolder, and other git URLs. To build it, clone it and build the folder.
- An mdBook book, found by its `book.toml`.

## Install

Linux and macOS:

```
curl -fsSL https://raw.githubusercontent.com/sagol/mdbindery/main/install/install.sh | bash
```

Windows (PowerShell):

```
irm https://raw.githubusercontent.com/sagol/mdbindery/main/install/install.ps1 | iex
```

These commands download from the public GitHub repository `sagol/mdbindery`. From a checkout of the repository, run `bash install/install.sh --local .` (on Windows, `powershell -ExecutionPolicy Bypass -File .\install\install.ps1 -Local .`) instead.

The installer needs nothing preinstalled. It fetches [uv](https://github.com/astral-sh/uv), installs mdbindery in an isolated environment (with its own Python if needed), then downloads pandoc, EPUBCheck, a Java runtime if none is present, Node.js, mermaid-cli, and Ace into a per-user folder. pandoc, EPUBCheck, Node.js, and uv are pinned to exact versions and verified against SHA-256 checksums; the Java runtime comes from Eclipse Temurin's API with its published checksum; mermaid-cli and Ace are pinned by version. Nothing needs administrator rights. Details, options, manual installation, and uninstalling: [docs/installation.md](docs/installation.md).

## Quick start

```
mdbindery doctor                                  # which tools are installed and working
cd your-book
mdbindery init                                    # write mdbindery.yaml from what it finds
mdbindery check .                                 # fix what it reports
mdbindery build                                   # dist/<slug>.epub and dist/reports/
mdbindery preview dist/<slug>.epub shots          # phone-size screenshots
```

To try it on the sample book in this repository:

```
git clone https://github.com/sagol/mdbindery
cd mdbindery/examples/sample-book
mdbindery check . --build
mdbindery build
mdbindery preview dist/writing-a-book-in-markdown.epub shots
```

The full walk-through is in [docs/tutorial.md](docs/tutorial.md).

## Requirements

- Linux (x64 or arm64, glibc-based), macOS (Intel or Apple silicon), or Windows 10/11 (x64 or arm64).
- About 1.5 GB of disk for the full tool set; mermaid-cli, Ace, and their two headless Chrome builds take most of it. With `--no-node` (no charts, no Ace, no `preview`), a whole install including uv and Python took about 370 MB. A downloaded Java runtime adds about 130 MB.
- An internet connection to install. Building works offline.

## Documentation

| Document | Contents |
|---|---|
| [Tutorial](docs/tutorial.md) | From an existing repository to a validated EPUB, step by step |
| [Book structure rules](docs/book-structure.md) | Files, headings, links, citations, images (cover, inline, figures, full-page), tables, charts |
| [Configuration](docs/configuration.md) | Every `mdbindery.yaml` key |
| [Checking](docs/checking.md) | `mdbindery check`, the report, and every check code with its fix |
| [Building](docs/building.md) | The pipeline, outputs, gates, reproducibility, covers, preview, uploading to stores |
| [Installation](docs/installation.md) | Linux, macOS, Windows, manual and offline setups, updating, uninstalling |
| [Troubleshooting](docs/troubleshooting.md) | Common errors and what to do |
| [Design](docs/design.md) | How it works inside, for contributors |

## For AI coding agents

[`skills/mdbindery-prepare-repo/SKILL.md`](skills/mdbindery-prepare-repo/SKILL.md) teaches an LLM agent (Claude Code, Codex, Cursor, and similar) how to restructure a repository for mdbindery and loop on `mdbindery check` until it is clean. [`skills/mdbindery/SKILL.md`](skills/mdbindery/SKILL.md) covers running the tool: installing, checking, building, previewing, and reading the reports. Both are plain Markdown and can be copied into any agent's skill or rules folder.

## Credits

mdbindery orchestrates [pandoc](https://pandoc.org), [EPUBCheck](https://www.w3.org/publishing/epubcheck/), [DAISY Ace](https://daisy.github.io/ace/), [mermaid-cli](https://github.com/mermaid-js/mermaid-cli), [Eclipse Temurin](https://adoptium.net), and [uv](https://github.com/astral-sh/uv). Each keeps its own license.

## License

MIT. See [LICENSE](LICENSE).
