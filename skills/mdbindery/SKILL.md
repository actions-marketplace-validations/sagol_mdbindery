---
name: mdbindery
description: Operate mdbindery, the CLI that turns a folder or GitHub repository of Markdown chapters into a validated EPUB 3. Install it, verify its tools with `mdbindery doctor`, run `mdbindery check` on a local folder or a repository URL, write a config with `mdbindery init`, build with `mdbindery build`, take phone-size screenshots with `mdbindery preview`, and read the check and build reports, the gates (links, images, charts, includes, EPUBCheck, Ace, word count), and the exit codes. Use when the user asks to build an EPUB, make an ebook, export Markdown to EPUB, convert a repo or book folder to an ebook, check whether a repository can become an EPUB, validate an ebook with EPUBCheck or Ace, preview the ebook, or install, update, or troubleshoot mdbindery. When the repository itself needs work (reading order, headings, links, citations, images, tables, HTML), switch to the mdbindery-prepare-repo skill.
---

# Run mdbindery

mdbindery turns a folder or GitHub repository of Markdown chapters (one file per chapter, relative links, local images, `[1]` citations with reference definitions) into an EPUB 3. It validates the result with its own gates (links, images, charts, includes, word count), EPUBCheck, and DAISY Ace. The build fails if any gate fails.

This skill covers running the tool. Fixing the repository belongs to the `mdbindery-prepare-repo` skill; switch to it as soon as `check` reports problems in the Markdown.

## Rules

- Do not edit the author's Markdown here. Configuration is fine; content fixes follow the ground rules of `mdbindery-prepare-repo`.
- Never loosen a gate to get a pass: keep `strict_links: true`, `epubcheck: true`, and `ace: true`; leave `wordcount_tolerance` and `wordcount_min_words` alone; add `ace_waivers` only with the author's approval. `--no-ace` is for iterating, not for the final build.
- Keep build output out of Git: `dist/`, report files, screenshots. Write check reports outside the repository. Commit nothing unless the user asks.
- The first build writes a permanent identifier into `mdbindery.yaml`. Tell the user: it belongs in the repository with the config and must never change.
- Ask the user before installing software.

## Install

```
# Linux, macOS
curl -fsSL https://raw.githubusercontent.com/sagol/mdbindery/main/install/install.sh | bash
# Windows PowerShell
irm https://raw.githubusercontent.com/sagol/mdbindery/main/install/install.ps1 | iex
```

The installer needs nothing preinstalled and no admin rights. It fetches uv, installs mdbindery in an isolated environment (with its own Python 3.12 if needed), then runs `mdbindery install-tools`. That downloads pandoc 3.11, EPUBCheck 5.4.0, Node.js, mermaid-cli, and Ace with headless Chrome, plus a Java runtime when no Java 11 or newer is found. It needs the mdbindery repository on GitHub to be public.

- The command goes to `~/.local/bin` (`%USERPROFILE%\.local\bin` on Windows; set `MDBINDERY_BIN` to change it). If the shell cannot find `mdbindery`, add that folder to `PATH`; the Windows installer adds it to the user `PATH` itself.
- The tools go to the tool home: `~/.local/share/mdbindery` on Linux, `~/Library/Application Support/mdbindery` on macOS, `%LOCALAPPDATA%\mdbindery` on Windows. Set `MDBINDERY_HOME` to use another folder, and keep it set afterwards: mdbindery finds its tools only there. The installer prints the line to add to your profile.
- `install.sh` options: `--no-node` (no Node.js, mermaid-cli, or Ace: charts become placeholders, no accessibility check, no `preview`), `--java auto|always|never`, `--no-tools` (command only), `--local PATH` (install from a checkout), `--ref REF` (branch, tag, or commit), `--uninstall`, `--help`. PowerShell: `-NoNode`, `-Java`, `-NoTools`, `-Local`, `-Ref`, `-Uninstall`. Pass options through the pipe with `curl -fsSL .../install.sh | bash -s -- --no-node`.
- Update mdbindery: run the installer again. Add or repair tools: `mdbindery install-tools [--no-node] [--java auto|always|never] [--force]`. `install-tools` exits with 1 when pandoc or EPUBCheck is still missing; Node.js, mermaid-cli, and Ace failures are only warnings.
- The full install takes about 1.5 GB; with `--no-node`, about 370 MB including uv and Python (measured sizes are in `docs/installation.md`). Building works offline afterwards.
- Other channels install the same command; run `mdbindery install-tools` after them: `pipx install mdbindery` or `uv tool install mdbindery` (PyPI), `brew install sagol/tap/mdbindery` (Homebrew). Pin with `mdbindery==X.Y.Z`, or with `--ref vX.Y.Z` on the installer taken from that tag.
- In GitHub Actions, `- uses: sagol/mdbindery@vX.Y.Z` installs mdbindery and its tools (cached between runs) and puts `mdbindery` on `PATH`; inputs `node` (`'false'` skips Node.js, mermaid-cli, and Ace), `java`, `version`, `cache`.

## Verify with doctor

```
mdbindery --version
mdbindery doctor
```

`doctor` prints the version, the tool home, and one line per tool:

```
mdbindery 0.1.1
tool home: /home/you/.local/share/mdbindery (default; set MDBINDERY_HOME to use another)
--- tools
pandoc     pandoc 3.11
epubcheck  EPUBCheck v5.4.0
java       /usr/bin/java (version 25)
node       v24.21.0
mermaid    renders PNG
ace        1.4.6
python     3.12.14 (PyYAML 6.0.3, Pillow 12.3.0)
```

| Line | Needed for | If missing or failing |
|---|---|---|
| `pandoc` | everything (3.8 or newer; an older one on `PATH` is ignored) | `mdbindery install-tools` |
| `epubcheck` | the EPUBCheck gate; needs Java 11 or newer | `mdbindery install-tools` (it downloads Java when needed); a note below the tool lines names the cause |
| `java` | EPUBCheck | as above |
| `node` | Mermaid, Ace, `preview` | `mdbindery install-tools` without `--no-node` |
| `mermaid` | charts; must say `renders PNG` | `installed but cannot render: ...` names the cause; try `mdbindery install-tools --force` |
| `ace` | the accessibility gate and `preview` | `mdbindery install-tools` |
| `python` | always present | |

`doctor` exits with 1 and prints ``required tools are missing: run `mdbindery install-tools` `` when pandoc or EPUBCheck is missing: the build fails without them. It exits with 0 when only Node.js tools are missing, and prints a note for each: `mermaid-cli is not installed (tools installed with --no-node): charts become placeholders.` and ``Ace is not installed: builds skip the accessibility check, and `preview` does not work``. Without Ace the build passes with the accessibility gate at `warn`.

## Check

A dry run. It reports every problem with a code, file, line, and fix, and changes nothing in the book.

```
mdbindery check                                   # the current folder
mdbindery check path/to/book --json "${TMPDIR:-/tmp}/mdb-check.json" --report "${TMPDIR:-/tmp}/mdb-check.md" -q
mdbindery check https://github.com/OWNER/REPO
mdbindery check https://github.com/OWNER/REPO/tree/BRANCH/FOLDER
mdbindery check https://github.com/OWNER/REPO --ref v2
mdbindery check git@github.com:OWNER/REPO.git      # SSH, with your own keys
mdbindery check https://gitlab.com/team/book.git   # other git URLs need git
mdbindery check . --build                          # plus a trial build with all gates
```

| Option | Effect |
|---|---|
| `-c FILE`, `--config FILE` | use this config file |
| `--ref REF` | branch or tag of a repository URL |
| `--build` | also run a trial build in a temporary folder; it runs only when the static check found no errors |
| `--no-render` | do not test-render Mermaid charts (faster; the trial build then uses chart placeholders too) |
| `--report FILE` | write the Markdown report to a file (missing folders are created) |
| `--json FILE` | write the JSON report to a file (missing folders are created) |
| `-q`, `--quiet` | no progress lines; with `--report` or `--json`, print nothing |

Exit codes: 0 no errors (warnings and notes allowed), 1 errors found (a broken config is an MB102 error), 2 the target could not be read or a report file could not be written (one line on stderr starting with `check error:`).

Notes:

- A URL is cloned with `git clone --depth 1` (or, for GitHub without git, downloaded as a ZIP) into a temporary folder that is deleted afterwards. git never asks for a password: a private repository needs your SSH keys or credential helper, or clone it yourself and check the folder. To fix anything, clone the repository and check the local folder.
- Accepted targets: a folder; `https://github.com/OWNER/REPO` (also without `https://`, with `www.`, or with `/tree/BRANCH/FOLDER`); `git@github.com:OWNER/REPO.git`; other `https://`, `ssh://`, `git://`, `file://`, or `*.git` URLs. A `/blob/...` URL points at one file and is refused.
- A repository fetched by URL is untrusted: config paths and images must stay inside it.
- For a GitHub URL without `source_url` in the config, the check assumes `https://github.com/OWNER/REPO/blob/BRANCH/<book folder>/` and puts it into the suggested config.
- `check` applies `drop_sections` and `drop_lines`, so dropped content is not reported.
- `check . --build` never writes into the config: it uses a temporary identifier in memory.
- Without `mdbindery.yaml`, the report ends with a suggested config; `mdbindery init` writes the same file.

## Read the check report

The Markdown report has these sections: the title (with the branch for a GitHub URL), Result, Book (title and language, config, file count, references, footnotes, charts, includes, images by kind, trial build), Summary (a count per code, when there are more than 10 findings), Errors, Warnings, Notes, Reading order, and, without a config, Suggested mdbindery.yaml. More than three findings of one code in one file are grouped into one entry with the line numbers.

The JSON report:

| Field | Contents |
|---|---|
| `ok` | true when there are no errors |
| `counts` | `error`, `warning`, `info` |
| `by_code` | `[{code, severity, count}]` |
| `facts.files` | the reading order used |
| `facts.inferred` | what was guessed, such as `config (no mdbindery.yaml found)`, `files (reading order)`, `metadata.title`, `metadata.lang`, `metadata.rights`, `cover.image`, `source_dir (book.toml)` |
| `facts.totals` | `refs`, `footnotes`, `charts`, `math`, `includes`, and `images` split into `inline`, `block`, `figure`, `full-page` |
| `facts.github` | `owner`, `repo`, `branch`, `subdir` of a GitHub URL check |
| `facts.trial_build` | `passed (N KB)`, `failed: <gates> (N KB)`, `failed: <error>`, or `skipped: fix the errors first` |
| `facts.suggested_config` | starter config when none exists |
| `findings[]` | `severity`, `code`, `file`, `line`, `message`, `fix` |

```
jq '.counts' mdb-check.json
jq -r '.by_code[] | "\(.code) \(.severity) x\(.count)"' mdb-check.json
jq -r '.findings[] | "\(.severity)\t\(.code)\t\(.file):\(.line // "")\t\(.message)"' mdb-check.json
```

Code families: MB0xx tools; MB1xx files, configuration, encoding, headings, metadata, reading order, mdBook; MB2xx links; MB3xx citations and footnotes; MB4xx images and cover; MB5xx HTML; MB6xx tables; MB7xx charts, math, code; MB9xx trial build (EPUBCheck MB900, Ace MB901, word count MB902, failed analysis or build MB903, any other failed gate MB904). `mdbindery-prepare-repo` has the fix for every code.

## Init

```
mdbindery init              # writes mdbindery.yaml for the current folder
mdbindery init path/to/book
mdbindery init --force      # rewrite: keeps metadata, identifier, cover, files, and options; old file saved as mdbindery.yaml.bak
```

`init` writes the inferred title, language, rights, cover, reading order (with a comment saying where the order came from), and `source_url` from the git remote when it is on GitHub. It leaves `identifier:` empty on its own line; the first build fills it. Exit codes: 0 written; 1 the file exists (without `--force`) or there are no Markdown files; 2 folder not found, or a `config error:` while inferring. With `--force`, an existing config that cannot be loaded is replaced by a fresh one after a warning.

## Build

```
mdbindery build                        # the book in the current folder
mdbindery build path/to/book
mdbindery build path/to/other.yaml     # the path can also be a config file
mdbindery build -c mdbindery-de.yaml -o out/de
mdbindery build --no-ace               # skip Ace while iterating
mdbindery build --keep-work            # keep intermediate files; the folder is printed
mdbindery build -q                     # print only the final line
```

With `-c FILE` and no path, the book is the config file's folder (or its `source_dir`).

Output (in `output_dir`, default `dist/`, or the `-o` folder):

| File | Contents |
|---|---|
| `<slug>.epub` | the book |
| `<slug>-cover.jpg` | full-size cover for store uploads (the supplied cover, or a generated 1600x2560 one) |
| `reports/build.json` | gates, per-file statistics, link report, pandoc warnings, `ok`, `failed_gates`, `skipped_gates`, `warning_gates`, `provenance` (tool versions, source commit, options), `timings`; after a build error also `failed_stage`, `error`, and `artifact` |
| `reports/build.log` | the console log |
| `reports/epubcheck.json` | EPUBCheck's messages |
| `reports/ace/report.html`, `reports/ace/report.json` | the Ace accessibility report |

Each build replaces only these files in `reports/`; other files there are kept.

Exit codes: 0 with `BUILD OK`; 1 with `BUILD FAILED: <gates> (details: .../build.json)`; 2 with `config error: ...` or `build error: ...` on stderr (invalid config, missing pandoc, a listed file not found, a file that is not UTF-8, no Markdown files, an unreadable cover); 3 `internal error: ...` (a bug: report it); 130 interrupted. After a build error that happened once the build started, `reports/build.json` still says which stage stopped (`failed_stage`) and whether the EPUB in `dist/` is stale (`artifact`); read it before rebuilding. Every external tool has a time limit; `build error: <tool> did not finish within N s` on a huge book or slow machine means rerun with `MDBINDERY_TIMEOUT_SCALE=3`.

The first build writes a permanent `urn:uuid` into the empty `identifier:` line (`generated identifier ... (saved in mdbindery.yaml)`). If the config has no `identifier:` line, or there is no config file, the log says `warning: generated identifier ... for this build only`, and every build gets a new identifier: add `identifier:` under `metadata:`.

Builds are reproducible: the same sources give a byte-identical EPUB. Timestamps come from the last git commit, else a fixed `metadata.date`, else the newest source file.

## Gates

| Gate | Fails when | Look at | Usual fix |
|---|---|---|---|
| `links` | a link points to an anchor that does not exist, or to a file that does not exist | log lines `UNRESOLVED link in ...` and `LINK to a missing file in ...`; `build.json` `links.unresolved` | fix the link or add `<a id>` at the target (prepare-repo, links) |
| `images` | an image is missing, remote, has an empty source, or (for a repository fetched by URL) lies outside the repository; a `[image: ...]` placeholder is shown in its place | log lines `IMAGE missing: ...`, `IMAGE remote: ...` | a local path relative to the Markdown file |
| `charts` | a Mermaid chart fails to render | log line `CHART in ... failed to render` | fix the chart syntax |
| `includes` | an mdBook `{{#include}}` directive could not be expanded | log line `INCLUDE in ... not expanded` | fix the path or anchor |
| `epubcheck` | EPUBCheck reports ERROR or FATAL, cannot run (no Java 11+), or writes no report | log, `reports/epubcheck.json` | read the message id and path |
| `ace` | Ace reports a critical or serious violation not listed in `options.ace_waivers`, or Ace is installed but writes no report | `reports/ace/report.html` | fix the source (alt text, headings, language) |
| `wordcount` | a file's word count in the EPUB differs from the source by more than 2% and more than 25 words (for card files, after subtracting the labels cards repeat) | log line `word count: FAILED: ...` naming the files; `build.json` `gates.wordcount` | broken HTML, text lost or duplicated in conversion; compare with `--keep-work` |

Results other than `pass` and `fail`:

- `warn` (the build passes): `charts` when mermaid-cli is not installed and charts became placeholders; `ace` when Ace is not installed (`check --build` reports it as an MB901 warning); `links` with `strict_links: false`. Say so when you report a build as validated.
- `skipped`: `ace` with `--no-ace` or `options.ace: false`; `epubcheck` with `options.epubcheck: false`.
- With a website `source_url` (not github.com), links to pages that are not in the repository stay web links and are not checked: the log line says `kept as web links (not checked)`. Links to `.md` files outside the book point to the published `.html` pages (`README.md` to `index.html`).

## Preview

```
mdbindery preview dist/<slug>.epub "${TMPDIR:-/tmp}/mdb-shots"
mdbindery preview dist/<slug>.epub "${TMPDIR:-/tmp}/mdb-shots" text/ch003.xhtml "text/ch003.xhtml#k02-some-heading" nav.xhtml --full
```

- Needs Node.js and Puppeteer from `mdbindery install-tools` (not available after `--no-node`).
- Without page arguments it captures `text/cover.xhtml`, `text/title_page.xhtml`, `nav.xhtml` (the table of contents), `text/ch001.xhtml`, and `text/ch002.xhtml`.
- Pages are paths inside the EPUB's `EPUB/` folder (`EPUB/text/...` is accepted too), optionally with `#id` to scroll to. With one `#` heading per file and `split_level: 1`, `ch001` is the first file in the reading order, `ch002` the second, and so on. Ids carry the file's key: `k00-` for the first file, `k01-` for the second.
- A page that is not in the EPUB stops the command with `preview error: not in the EPUB: ...` and the list of pages. An id that is not found prints `WARN no element with id ...` and captures the top of the page.
- Options: `--width` (default 412, 200 to 4000), `--height` (default 915, 200 to 8000), `--full` (whole page instead of one screen; adds `_full` to the file name). Screenshots are PNG files named after the page (`text_ch003_k02-some-heading.png`); the command prints their paths.
- Open every screenshot and look: cover, table of contents, figures at full width with captions, full-page images, tables or cards, charts, reference lists, footnotes, and no raw Markdown or HTML.

## Common failures

| Symptom | Cause | Fix |
|---|---|---|
| `mdbindery: command not found` | `~/.local/bin` not on `PATH` | add it, or open a new terminal (Windows) |
| ``required tools are missing: run `mdbindery install-tools` `` | pandoc or EPUBCheck (or Java 11+) missing, or `MDBINDERY_HOME` not set to the folder the tools went to | `mdbindery install-tools`, or set `MDBINDERY_HOME` |
| `check error: repository not found or not accessible: ...` | wrong URL, or a private repository | fix the URL; for a private repository clone it yourself and check the folder |
| `check error: branch or tag not found: X` | wrong `--ref` or `/tree/BRANCH` | use an existing branch or tag |
| `check error: this is a link to a single file; ...` | a `/blob/` URL | use the repository URL or `/tree/BRANCH/FOLDER` |
| `check error: folder not found: X`, `subfolder not found in repository: X` | typo in the path or folder | fix it |
| `config error: invalid YAML in mdbindery.yaml, line N, column M: ...` | YAML syntax | fix that line |
| `config error: unknown top-level key "metdata" (did you mean "metadata"?): ...` | a misspelled top-level key | correct it; misspelled nested keys are warnings (MB102) |
| `config error: options.X must be ...` | invalid value | use an allowed value (the message lists them) |
| `build error: X is not valid UTF-8 (byte N); re-save it as UTF-8` | a file in another encoding | convert it to UTF-8 |
| `build error: listed file not found: X` | a wrong name under `files:` | fix the entry |
| `build error: pandoc not found (or older than 3.8): ...` | pandoc missing | `mdbindery install-tools` |
| `build error: output folder is a file: ...` | `-o` names an existing file | give a folder |
| `EPUBCheck: NOT RUN: Java 11+ or EPUBCheck missing` | no usable Java or EPUBCheck | `mdbindery install-tools` |
| `Ace: not run: not installed` | tools installed with `--no-node` | `mdbindery install-tools` |
| `Ace: FAILED to run: ...` | Ace or its headless Chrome is broken | `mdbindery install-tools --force`; `--no-ace` while iterating |
| `warning: N chart(s) became placeholders: mermaid-cli is not installed` | no mermaid-cli | `mdbindery install-tools`, then `mdbindery doctor` |
| `CHART in ... failed to render` | Mermaid syntax error | fix it; `check` shows the parse error as MB701 |
| `word count: FAILED: text lost or added beyond 2% or 25 words per file` | unclosed HTML, text inside dropped tags, or a converter problem | compare the prepared file in the `--keep-work` folder with the EPUB file (prepare-repo) |
| `preview error: preview needs Node.js and Puppeteer: ...` | tools installed with `--no-node` | `mdbindery install-tools` |
| `internal error: ...` (exit 3) | a bug in mdbindery | report it with the printed lines |

## Configuration at a glance

`mdbindery init` writes a starter `mdbindery.yaml`. Top-level keys: `slug`, `source_dir`, `output_dir`, `source_url`, `metadata` (`title`, `subtitle`, `authors`, `lang`, `identifier`, `date`, `rights`, `publisher`, `description`, `subjects`, `series`, `series_position`), `cover` (`image`, `embed_height`, `background`, `foreground`, `accent`), `files` (strings, or mappings with `file`, `role`, `title`, `drop_sections`, `mermaid_alt`, `key`), and `options`. An unknown top-level key is an error; an unknown nested key is a warning.

Without a config, mdbindery infers the reading order: from `SUMMARY.md` or another table of contents file; else, when the chapter file names are not all numbered, from the README's links (when they cover at least half of the chapter files); else from file names (README first, front matter such as a preface, numbered chapters in natural order, appendices, back matter), with `chapters/` used when present. mdBook books (a `book.toml` with `SUMMARY.md`) are recognized; a `SUMMARY.md` alone only sets the reading order. The title, language, license, and cover are inferred too. The full key table and every fix are in `mdbindery-prepare-repo`.
