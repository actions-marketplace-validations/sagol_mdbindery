# Contributing

Bug reports and pull requests are welcome. [docs/design.md](docs/design.md) explains how the code works.

## Development setup

With uv:

```
git clone https://github.com/sagol/mdbindery
cd mdbindery
uv venv
uv pip install -e ".[test]"
source .venv/bin/activate          # Windows: .venv\Scripts\activate
mdbindery install-tools
```

Or with the standard library's venv:

```
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[test]"
mdbindery install-tools
```

The commands below assume the environment is active. `install-tools` puts pandoc, EPUBCheck, Java (if needed), Node.js, mermaid-cli, and Ace into the tool home. To share a tool home between checkouts, or to keep it out of your user folder, set `MDBINDERY_HOME` before running any `mdbindery` command. `mdbindery doctor` shows which tools were found.

## Tests

```
python -m pytest                              # skips tests whose tools are missing
MDBINDERY_REQUIRE_TOOLS=1 python -m pytest    # fails them instead, as CI does
python -m pytest tests/test_markdown.py       # pure Python, no tools needed
```

Without pandoc, only the tests that need no external tool run. The build tests also need EPUBCheck; none of them needs Ace. Set `MDBINDERY_REQUIRE_TOOLS=1` before you send a change, so a missing tool cannot turn a failure into a skip.

A build writes into the book (`dist/` and the identifier in `mdbindery.yaml`). Build copies, never the files under `examples/` or `tests/fixtures/`:

```
cp -r examples/sample-book /tmp/sample-book
mdbindery build /tmp/sample-book
mdbindery check tests/fixtures/broken-book     # must exit with 1
```

## Where things are

| Change | Files |
|---|---|
| Command-line options, exit codes | `src/mdbindery/cli.py` |
| Configuration keys, defaults, validation, reading order | `src/mdbindery/config.py`, then `docs/configuration.md` |
| Line-level processing before pandoc (includes, drops, reference list, Mermaid) | `src/mdbindery/markdown.py` |
| HTML, images, titles, citations, links, identifiers | `src/mdbindery/data/book.lua` |
| Build steps and gates | `src/mdbindery/build.py`, then `docs/building.md` |
| Check codes and reports | `src/mdbindery/check.py`, then `docs/checking.md` |
| Tool lookup and versions | `src/mdbindery/tools.py`, `src/mdbindery/installer.py`, `install/`, then `docs/installation.md` |
| Default stylesheet | `src/mdbindery/data/epub.css` |

Keep the book rules in [docs/book-structure.md](docs/book-structure.md), the check codes in [docs/checking.md](docs/checking.md), and the two skills under `skills/` in step with the code. Tool versions and checksums are pinned in `src/mdbindery/installer.py` and `install/`; [docs/design.md](docs/design.md#installer-and-pinned-versions) has the bump procedure.

## Adding a check code

1. Pick the next free number in the right family: MB0xx tools, MB1xx files, configuration, headings, and metadata, MB2xx links, MB3xx citations and footnotes, MB4xx images and cover, MB5xx HTML, MB6xx tables, MB7xx charts, math, and code, MB9xx trial build.
2. Report it in `src/mdbindery/check.py` with `rep.add(severity, code, message, fix, file, line)`: a static check in `_check()` or one of the `check_*` functions, a finding from the analysis pass in `analysis_findings()`, or a trial-build finding in `trial_build()`. Severity is `error` only when the build would fail or the EPUB would be wrong, since errors make `check` exit with 1. Write the fix as an instruction the author can follow.
3. Document it in `docs/checking.md`: a row in the summary table and a `#### MBnnn: title` section in the matching group, with an example and the fix.
4. Add a test: a planted case in `tests/fixtures/broken-book` (and the code in the expected set of `test_check_finds_every_planted_problem`), or a small book built in `tmp_path` as in `tests/test_regressions.py`.
5. Add the code and its fix to `skills/mdbindery-prepare-repo/SKILL.md`.

## Style

- Python 3.9 compatible, standard library plus PyYAML and Pillow. Follow the style of the surrounding code: short functions, no type annotations, single quotes.
- Run external programs through `build.run()` or with an argument list, never through a shell.
- Messages for users are one plain line; errors say what to do next.
- Docs: plain English, short sentences, sentence-case headings, tables for reference material.

## Commit messages

Short and plain, in the imperative, lowercase is fine: `check: report unclosed includes`. One or two lines; add a body only when the reason is not obvious from the diff.

## Releases

Follow the release checklist in [docs/design.md](docs/design.md#release-checklist): a `vX.Y.Z` tag builds the packages and the GitHub release, then the Homebrew formula is updated by hand.
