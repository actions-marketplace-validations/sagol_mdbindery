# Troubleshooting

For PDF failures, start with `reports/pdf/build.json` and `reports/pdf/build.log`. EPUB reports stay under `reports/`. See [PDF export errors](#pdf-export-errors).

When something goes wrong, these four places answer most questions:

1. `mdbindery doctor` shows which tools work and which tool home is in use ([installation.md](installation.md#verifying-the-installation)).
2. `mdbindery check . --build` reports each problem with a code, the file and line, and a fix ([checking.md](checking.md)).
3. `dist/reports/` holds `build.log` (the build log), `build.json` (every gate with details), `epubcheck.json` (all EPUBCheck messages), and `ace/report.html` (the accessibility report). See [building.md](building.md#outputs).
4. `mdbindery build --keep-work` keeps the intermediate files and prints where they are ([building.md](building.md#the-pipeline)).

## Quick reference

| Symptom | Cause | Fix |
|---|---|---|
| `mdbindery: command not found` right after installing | The bin folder is not on `PATH`, or the terminal was open before the install | [The command is not found](#the-command-is-not-found) |
| `doctor` shows `(default; set MDBINDERY_HOME to use another)` and `pandoc     missing` after an install into a custom folder | `MDBINDERY_HOME` is not set in this shell | [A custom tool home is not found](#a-custom-tool-home-is-not-found) |
| ``build error: pandoc not found (or older than 3.8): run `mdbindery install-tools` `` | No pandoc in the tool home, and none (or only an old one) on `PATH` | Run `mdbindery install-tools`; see also [Old pandoc on PATH](#old-pandoc-on-path) |
| `error: uv could not install mdbindery` | uv could not download mdbindery, its packages, or Python | [Python and uv problems](#python-and-uv-problems) |
| `ensurepip is not available` or `externally-managed-environment` | Restrictions of the system Python in a manual install | [Python and uv problems](#python-and-uv-problems) |
| `install failed: checksum mismatch for ...` | The download differs from the pinned file | [Checksum mismatch](#checksum-mismatch) |
| `install failed: <urlopen error ...>` or a certificate error | A proxy or firewall blocks the download | [Corporate proxies](#corporate-proxies) |
| `warning: Node.js tools not installed: ...` | A download for Node.js, npm packages, or headless Chrome failed | Fix the network problem and run `mdbindery install-tools` again |
| `running scripts is disabled on this system` (PowerShell) | The execution policy blocks script files | [Windows paths and spaces](#windows-paths-and-spaces) |
| `EPUBCheck: NOT RUN: Java 11+ or EPUBCheck missing`, then `BUILD FAILED: epubcheck` | No Java 11+, or no EPUBCheck in the tool home | [Missing Java](#missing-java) |
| `EPUBCheck: FAILED to run (exit 1): Error: Invalid or corrupt jarfile ...` | A damaged EPUBCheck download | [Broken EPUBCheck](#broken-epubcheck) |
| `Ace: not run: not installed ...` (the build still passes) | The tools were installed with `--no-node` | Run `mdbindery install-tools` without `--no-node` to get the accessibility check |
| `mermaid    installed but cannot render: ...` in `mdbindery doctor` | Headless Chrome cannot start | [Puppeteer and Chrome launch failures](#puppeteer-and-chrome-launch-failures) |
| `Ace: FAILED to run: ...`, then `BUILD FAILED: ace` | Ace or its Chrome crashed | [Puppeteer and Chrome launch failures](#puppeteer-and-chrome-launch-failures) |
| `UNRESOLVED link in 01-intro.md to 02-body.md#no-such-anchor` | The anchor does not exist in that file | [Unresolved links](#unresolved-links) |
| `LINK to a missing file in 01-intro.md: ghost.md` | A link to a file that does not exist | [Links to files](#links-to-files) |
| `links to files outside the book kept as text (no source_url)` | Links to repository files that are not in the book, with no `source_url` | Set `source_url`; see [Links to files](#links-to-files) |
| `IMAGE missing: images/x.png in 01-intro.md`, or `[image: ...]` text in the EPUB | The path is wrong, or the image is remote | [Images](#images) |
| `INCLUDE in 01-intro.md not expanded (file not found): ...` | An mdBook `{{#include}}` points to a missing file or anchor | [Includes](#includes) |
| `CHART in 02-body.md failed to render (placeholder used)` | Mermaid syntax error | [Charts and Mermaid](#charts-and-mermaid) |
| `warning: 3 chart(s) became placeholders: mermaid-cli is not installed` | Installed with `--no-node` | Run `mdbindery install-tools` without `--no-node` |
| `serious color-contrast x11`, then `BUILD FAILED: ace` | Text and background colors too close | [Ace failures](#ace-failures) |
| `word count: FAILED: text lost or added beyond 2% or 25 words per file` | Text lost or duplicated in conversion | [Word-count gate](#word-count-gate) |
| `build error: pandoc did not finish within 1800 s and was stopped` | A tool hung, or the book is very large for this machine | [Time limits](#time-limits) |
| `install failed: another \`mdbindery install-tools\` is running` | A second install into the same tool home, or a lock file left by a killed install | Wait for the other install, or delete the named lock file |
| `ERROR RSC-032: Fallback must be provided for foreign resources` | Unsupported image format such as BMP | Convert the image to JPEG or PNG |
| `ERROR RSC-006: Remote resource reference is not allowed` | A stylesheet or font loaded from the web | [EPUBCheck messages](#epubcheck-messages) |
| `build error: 03-latin.md is not valid UTF-8 (byte 17); re-save it as UTF-8` | The file uses another encoding | Re-save it as UTF-8 (check code MB105) |
| `config error: ...` | A YAML syntax error, an unknown top-level key, or a wrong value in `mdbindery.yaml` | [Configuration errors](#configuration-errors) |
| `config warning: unknown config key: options.toc_dept (did you mean "toc_depth"?)` | A misspelled key inside a section; it is ignored | Fix the key name ([configuration.md](configuration.md)) |
| `build error: listed file not found: 04-gone.md` | A name under `files:` does not match a file | Fix the name |
| `build error: cover image not found: ...` | `cover.image` is relative to the configuration file's folder | Fix the path |
| `build error: cover image cannot be read (...); save it again as JPEG` | The cover file is damaged or not an image | Save it again as JPEG |
| `build error: output folder is a file: ...` | `-o` (or `output_dir`) names an existing file | Give a folder path |
| `warning: generated identifier ... for this build only` | The configuration has no `identifier:` line | Add an empty `identifier:` line under `metadata:`; the next build fills it in |
| Two builds of the same commit differ | Identifier, fonts, or tool versions differ | [Reproducible output](#reproducible-output) |
| `preview error: preview needs Node.js and Puppeteer` | Installed with `--no-node` | Run `mdbindery install-tools` |
| `preview error: not in the EPUB: ...` | A page path that the EPUB does not contain | Use one of the paths listed after `pages:` in the same message |
| A chapter title you did not write, such as "Power budget" | The file has no heading, so the title was made from its file name | Start the file with `# Title`, or set `title:` for it in `mdbindery.yaml` |
| `check error: repository not found or not accessible: ...` | The repository is private, missing, or needs credentials | Clone it yourself and run `mdbindery check <folder>` |
| `internal error: ...` (exit status 3) | A bug in mdbindery | [Internal errors](#internal-errors) |

## Installation

### The command is not found

The installers put the `mdbindery` command in `~/.local/bin` (Windows: `%USERPROFILE%\.local\bin`), or in `MDBINDERY_BIN` if you set it.

- Linux and macOS: when the folder is not on `PATH`, the installer prints the line to add, for example `echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.profile`. Add it to the profile your shell reads (`~/.profile`, `~/.bashrc`, or `~/.zshrc`), then open a new terminal. Until then, run `~/.local/bin/mdbindery`.
- Windows: the installer adds the folder to the user `PATH`. Terminals that were already open do not see the change; open a new one.

### A custom tool home is not found

mdbindery looks for its tools in `MDBINDERY_HOME` on every run, not only during installation. If you installed with a custom `MDBINDERY_HOME` and a new terminal does not have it set, mdbindery looks in the default folder and finds nothing there:

```
mdbindery 0.2.0
tool home: .../.local/share/mdbindery (default; set MDBINDERY_HOME to use another)
--- tools
pandoc     missing
epubcheck  missing
java       /usr/bin/java (version 25)
node       missing
mermaid    missing
ace        missing
python     3.12.14 (PyYAML 6.0.3, Pillow 12.3.0)

required tools are missing: run `mdbindery install-tools`
if you installed the tools into another folder, set MDBINDERY_HOME to it first
```

A build stops with ``build error: pandoc not found (or older than 3.8): run `mdbindery install-tools` ``. Do not run `install-tools` in this state: it would download everything again into the default folder. Set the variable permanently instead, with the line the installer printed at the end:

```
echo 'export MDBINDERY_HOME="/opt/mdbindery"' >> ~/.profile                  # Linux, macOS
[Environment]::SetEnvironmentVariable('MDBINDERY_HOME', 'C:\mdbindery', 'User')  # PowerShell
```

Open a new terminal and run `mdbindery doctor`.

### Python and uv problems

The installers hide uv's output unless uv fails. Then they print it, followed by `error: uv could not install mdbindery` (on Windows, `uv could not install mdbindery`). The lines above that message name the cause. Common ones:

- uv cannot reach PyPI (for PyYAML and Pillow), GitHub (for the mdbindery archive, and for a Python 3.12 when the machine has none), or a proxy blocks it: see [Corporate proxies](#corporate-proxies).
- `--ref` names a branch, tag, or commit that does not exist, so the archive download fails with 404.

With `--local`, a folder that is not the mdbindery source (no `pyproject.toml` in it, or no such folder) stops `install.sh` before anything is downloaded: `error: --local needs the mdbindery source folder (with pyproject.toml): <folder>`.

For a manual install with the system Python, typical messages are:

- `The virtual environment was not created successfully because ensurepip is not available` (Debian and Ubuntu without the `python3-venv` package).
- `error: externally-managed-environment` (a `pip install` into a system Python that the distribution manages).
- `python3: command not found`, or a Python older than 3.9.

The one-line installer avoids all of them: uv creates the environment without `ensurepip` or `pip`, and downloads its own Python 3.12 into the tool home when the machine has none. Use it unless you need a manual install. For a manual install, use `pipx` or `uv tool install`, or on Debian and Ubuntu install `python3-venv` first. Do not use `pip install --break-system-packages`.

### Corporate proxies

Set the proxy in the environment before running the installer or `mdbindery install-tools`:

```
export HTTPS_PROXY=http://proxy.example.com:8080     # Linux, macOS
export HTTP_PROXY=http://proxy.example.com:8080
```

```
$env:HTTPS_PROXY = 'http://proxy.example.com:8080'   # PowerShell
$env:HTTP_PROXY = 'http://proxy.example.com:8080'
```

Several programs download during installation, and all of them read `HTTPS_PROXY`: curl (uv, on Linux and macOS), uv (mdbindery, its packages, and Python), Python (pandoc, EPUBCheck, the Java runtime, Node.js), npm (mermaid-cli and Ace), and Puppeteer (headless Chrome). `mdbindery check <repository URL>` uses git, which reads it too. On Windows, the first download (uv) uses `Invoke-WebRequest`, which in Windows PowerShell 5.1 takes the proxy from the Windows proxy settings. Hosts listed in `NO_PROXY` are reached directly.

If the proxy inspects TLS traffic with its own certificate, downloads fail with certificate errors. Point the tools at your company's CA bundle: `SSL_CERT_FILE=/path/to/ca.pem` for Python and uv, and `NODE_EXTRA_CA_CERTS=/path/to/ca.pem` for npm and Puppeteer.

If GitHub, nodejs.org, or the npm registry are blocked completely, install on another machine and copy the tools ([installation.md](installation.md#offline-and-air-gapped-machines)).

### Checksum mismatch

`install failed: checksum mismatch for <url>`, followed by the expected and the actual SHA-256, comes from `mdbindery install-tools`. `error: checksum mismatch for uv-x86_64-unknown-linux-gnu.tar.gz` (or the name of another uv archive) comes from the installer itself. Either means the downloaded file is not the pinned one. Common causes are an interrupted download and a proxy that returns an error page instead of the file. Run the command again; if it keeps failing, download the URL by hand and look at what arrives. If the file is correct and the pin is wrong, report it as a bug. Do not edit the checksum to make the error go away.

### Windows paths and spaces

- Execution policy: `irm ... | iex` and the script-block form are not affected, but running `install.ps1` as a file can fail with `running scripts is disabled on this system`. Run it as `powershell -ExecutionPolicy Bypass -File .\install\install.ps1 -Local .`.
- Slashes: write paths in `mdbindery.yaml` and in Markdown links with forward slashes (`chapters/01-intro.md`, `../images/x.png`), as on GitHub. In a double-quoted YAML string, a backslash starts an escape sequence. Backslashes in `files:` entries are turned into slashes.
- Spaces in file names: links must write them as `%20` (`[intro](my%20intro.md)`); renaming files to use hyphens is simpler ([book-structure.md](book-structure.md#1-repository-layout)).
- Tool home path: the default tool home is under your user profile. If a tool fails to start with a path error, or `install-tools` fails with path-too-long errors, move the tool home to a short path without spaces and install the tools again:

  ```
  [Environment]::SetEnvironmentVariable('MDBINDERY_HOME', 'C:\mdbindery', 'User')
  ```

  Open a new terminal, run `mdbindery install-tools`, then `mdbindery doctor`.
- Line endings: CRLF files work; `mdbindery check` notes them (MB105, informational).

## Missing tools

### Missing Java

EPUBCheck is a Java program and needs Java 11 or newer. mdbindery looks for `java` in `<tool home>/tools/jre/` first, then on `PATH`; it does not read `JAVA_HOME`.

Symptoms: `mdbindery doctor` shows `java       missing` (or a version below 11) and `epubcheck  missing` with the note `epubcheck: needs Java 11 or newer`, and the build log shows:

```
  EPUBCheck: NOT RUN: Java 11+ or EPUBCheck missing (run `mdbindery install-tools`, or set options.epubcheck: false to build without validation)
```

followed by `BUILD FAILED: epubcheck`.

Fix: `mdbindery install-tools --java always` downloads an Eclipse Temurin 21 runtime into the tool home, which takes priority over any other Java. Or install Java 11+ yourself, make sure `java -version` works in a new terminal, and run `mdbindery doctor`. `options.epubcheck: false` lets a draft build pass without validation; never release a book built that way.

### Broken EPUBCheck

When the EPUBCheck jar is damaged (an interrupted download, a disk error), Java starts but EPUBCheck does not. `mdbindery doctor` shows `epubcheck  missing` with a note that has Java's message:

```
  epubcheck: installed but does not run: Error: Invalid or corrupt jarfile .../tools/epubcheck/x/epubcheck.jar
```

A build fails the epubcheck gate with the same message, and `build.json` records `EPUBCheck did not produce a report` under `gates.epubcheck.detail`:

```
  EPUBCheck: FAILED to run (exit 1): Error: Invalid or corrupt jarfile .../tools/epubcheck/x/epubcheck.jar
```

Fix: `mdbindery install-tools --force` downloads EPUBCheck again (without `--force`, a component whose version marker is in place is skipped).

### Old pandoc on PATH

mdbindery passes options that pandoc added in version 3.8, so it ignores an older `pandoc` on `PATH`. When the tool home has no pandoc either, `mdbindery doctor` shows `pandoc     missing` with a note:

```
  pandoc: .../bin/pandoc (3.1) on PATH is older than 3.8 and is not used
```

and a build stops with ``build error: pandoc not found (or older than 3.8): run `mdbindery install-tools` ``. Run `mdbindery install-tools`: the pandoc 3.11 it puts in the tool home is used before anything on `PATH`, and your system pandoc stays as it is.

### Puppeteer and Chrome launch failures

mermaid-cli, Ace, and `mdbindery preview` start a headless Chrome from `<tool home>/tools/puppeteer/`. Symptoms:

- `mdbindery doctor`: `mermaid    installed but cannot render: <last error line>`.
- Build log: `Ace: FAILED to run:` followed by the end of Ace's output. Up to 1000 characters of it are in `reports/build.json` under `gates.ace.detail`.
- `preview error:` followed by a Puppeteer message.
- Messages such as `Failed to launch the browser process`, `error while loading shared libraries: libnss3.so`, `Could not find Chrome (ver. ...)`, `Browser was not found at the configured executablePath`, or a `TimeoutError`.

Causes and fixes:

- Missing system libraries (Linux): `error while loading shared libraries` names the first one. Install the set listed in [installation.md](installation.md#headless-chrome) and use the `ldd` command there to find the rest.
- Missing browser build (an interrupted install, or a deleted `tools/puppeteer/`): run `mdbindery install-tools`. The browser step runs every time, even when the npm packages are already installed.
- A different tool home: the tools were installed under one `MDBINDERY_HOME` and mdbindery now runs with another. `mdbindery doctor` prints the one in use.
- Containers: Docker gives containers 64 MB of `/dev/shm` by default, which can crash Chrome. Start the container with `--shm-size=1g`. (`tools/puppeteer-config.json` is rewritten by mdbindery on every run, so extra Chrome flags added there do not last.)
- The Chrome sandbox: mermaid-cli and `preview` keep Chrome's sandbox on where it works. When Chrome fails with a message about the sandbox (common on systems that restrict unprivileged user namespaces), mdbindery retries without it. For charts it logs this and writes `<tool home>/tools/no-sandbox`, so later runs skip the sandbox; `preview` warns and turns the sandbox off for that run only, because it opens EPUBs that may come from someone else; as root, and with `CI` or `MDBINDERY_NO_SANDBOX` set, the sandbox is off from the start. If you suspect the sandbox but the error does not mention it, run once with `MDBINDERY_NO_SANDBOX=1` to compare. Ace always runs its Chrome without the sandbox, so an Ace failure is not a sandbox problem. Delete `tools/no-sandbox` to try the sandbox again.

To get the rest of the build while you fix Ace, build with `--no-ace`.

## Build gates

### Unresolved links

The build log shows `UNRESOLVED link in <file> to <target file>#<anchor> (text: <link text>)`. `mdbindery check` reports the same problem as MB200 with the file and line of the link. The link is pointed at the start of the target chapter so the EPUB stays valid, but the `links` gate fails.

Common causes:

- The heading was edited and its anchor changed. Anchors follow GitHub's rule ([book-structure.md](book-structure.md#4-links)): on GitHub, hover over the heading and copy its link to see the exact anchor.
- The link uses the anchor of a `title:` from `mdbindery.yaml`. A `title:` changes only the heading's text; the anchor stays the one made from the heading in the file. Link to the file without an anchor (`[chapter 1](01-intro.md)`), which always lands on the chapter start.
- The target section was removed with `drop_sections`.

Fixes: correct the link, or add `<a id="old-anchor"></a>` where the link should land; the custom anchor works on GitHub too. A difference in letter case only is fixed silently, as GitHub does. A link that matches only after ignoring ASCII punctuation and spaces works but is logged (MB201 in `check`); make it exact:

```
  link in 02-setup.md to 02-setup.md#install_the_tools matched approximately (anchor is #install-the-tools)
```

`options.strict_links: false` turns link problems into a warning (gate result `warn`). Use it only for drafts.

### Links to files

- `LINK to a missing file in <file>: <path>`: a link to a file that does not exist fails the `links` gate (MB204 in `check`). Fix the path or remove the link. A link to `chapter.html` works when `chapter.md` is in the book, and `folder/index.html` or `folder/` when `folder/README.md` is (MB205).
- `links to files outside the book kept as text (no source_url): [...]`: links to repository files that are not in the reading order, such as `LICENSE` or source code. Without `source_url` the link is removed and its text stays (MB202). Set `source_url` to the online copy of the book folder, and they become web links.
- `<n> link(s) to pages that are not in the repository kept as web links (not checked)`: `source_url` is a website rather than a github.com address, so mdbindery assumes those pages exist on the site (MB203). Check them in a browser.

### Images

- `IMAGE missing: <src> in <file>`: the path is resolved from the folder of the Markdown file (`images/x.png` from a root chapter, `../images/x.png` from `chapters/`), and a path starting with `/` from the repository root. File names are case-sensitive in the EPUB and on GitHub even when your file system is not. Write spaces as `%20`.
- `IMAGE remote: <url>`: an EPUB cannot load images from the web, and mdbindery does not download them. Save the image into the repository and use a relative path. An image URL of the same GitHub repository (`https://github.com/OWNER/REPO/blob/...` or `raw.githubusercontent.com/...`) is replaced by the local file automatically when mdbindery knows the repository (from `source_url` or the git remote).
- Outside the repository: in the trial build of `mdbindery check <URL> --build`, images of the checked repository must stay inside it, and one that does not fails the images gate (MB406 in the report). A normal build of a local folder has no such limit.

Each of these images appears in the EPUB as the text `[image: <alt text>]`, and the `images` gate fails.

BMP, TIFF, HEIC, PSD, AVIF, and PDF images pass the `images` gate but fail EPUBCheck with RSC-032. Convert photos to JPEG and diagrams to PNG. Missing alt text and oversized images do not fail the build; `mdbindery check` reports them (MB402, MB404).

### Includes

The build log shows `INCLUDE in <file> not expanded (<reason>): <directive>`, and the `includes` gate fails. The directive stays in the text as typed. Reasons:

- `file not found`: the path is relative to the Markdown file that holds the directive, not to the book folder.
- `anchor not found: <name>`: the included file has no `ANCHOR: <name>` line, or no lines between it and `ANCHOR_END: <name>`.
- `outside the repository`: the path climbs out of the repository, which mdbindery does not follow.
- `cannot read: ...`: the file is not readable as UTF-8 text.

To show a directive as text, write it as `\{{#include ...}}`. `mdbindery check` reports these as MB131.

### Charts and Mermaid

- `CHART in <file> failed to render (placeholder used): Error: Parse error on line 2: ...`: the chart has a syntax error. Paste it into https://mermaid.live to see the error with context. mdbindery renders with mermaid-cli 12.0.0; GitHub may use a different Mermaid version, so a chart that renders on GitHub can still fail here.
- `warning: <n> chart(s) became placeholders: mermaid-cli is not installed`: the tools were installed with `--no-node`. Charts become a quote ("... This chart is available in the online edition") and the `charts` gate reports `warn`. Run `mdbindery install-tools` without `--no-node` and check that `mdbindery doctor` says `renders PNG`. With `options.mermaid: placeholder`, placeholders are intended and no warning is logged.
- `mdbindery doctor` says `mermaid    missing` and `mermaid-cli is not installed (tools installed with --no-node): charts become placeholders.`: run `mdbindery install-tools` without `--no-node`.
- `mdbindery doctor` says `installed but cannot render`: see [Puppeteer and Chrome launch failures](#puppeteer-and-chrome-launch-failures).
- Size and theme: `mermaid_scale`, `mermaid_font_size`, and `mermaid_theme` ([configuration.md](configuration.md#charts)).

### Ace failures

Only `critical` and `serious` violations fail the gate; `moderate` and `minor` ones are listed in the log and do not. `reports/ace/report.html` shows each violation with the element that caused it.

- `color-contrast` (serious): text and background colors are too close. The default stylesheet passes. Causes are custom colors in `css` or `extra_css`, or a colored `highlight_style` for code. Make the text darker or the background lighter (WCAG AA asks for a contrast ratio of at least 4.5:1 for normal text), or go back to `highlight_style: monochrome`.
- `heading-order` (moderate): a skipped heading level. It does not fail the build; fix it anyway (MB108).
- To accept a rule on purpose, list it: `ace_waivers: [color-contrast]`. The log still shows it, marked `(waived)`.
- `Ace: not run: not installed (tools were installed with --no-node); accessibility not checked.`: the gate is `warn` and the build can pass, but nothing checked accessibility. Install the Node.js tools before a release.

### EPUBCheck messages

The build log shows the first 50 messages as `<SEVERITY> <ID>: <message> [<path>:<line>]`, and `reports/epubcheck.json` has all of them. Only `ERROR` and `FATAL` fail the gate. The path and line refer to a file inside the EPUB, not to your Markdown. To look at the line:

```
unzip -p dist/<slug>.epub EPUB/text/ch001.xhtml | sed -n '20p'
```

`ch001.xhtml`, `ch002.xhtml`, ... follow the reading order, and anchors start with the file key (`k00-`, `k01-`, ...), which is the position of the source file in the reading order.

mdbindery's own gates catch broken links and images before EPUBCheck runs. The EPUBCheck errors left for an mdbindery book usually come from these two:

| ID | Example | Cause | Fix |
|---|---|---|---|
| RSC-032 | `Fallback must be provided for foreign resources, but found none for resource "EPUB/media/file1.bmp" of type "image/x-ms-bmp".` | An image in a format EPUB does not support, such as BMP | Convert to JPEG or PNG |
| RSC-006 | `Remote resource reference is not allowed in this context; resource "https://fonts.example.org/css?family=Serif" must be located in the EPUB container.` | A resource loaded from the web, usually `@import url(https://...)` for a web font in `extra_css` | Put the font in the book with `options.embed_fonts` and `@font-face` |

For any other message, find the element at the reported path and line, then trace it back to the source file. `mdbindery check --build` reports the same messages as MB900 ([checking.md](checking.md)). If EPUBCheck itself does not run, see [Missing Java](#missing-java) and [Broken EPUBCheck](#broken-epubcheck).

### Word-count gate

The gate compares, for each file, the words in the prepared Markdown with the words in the EPUB ([building.md](building.md#wordcount)). A failing log line names up to five files, worst first:

```
  word count: FAILED: text lost or added beyond 2% or 25 words per file: 02-setup.md 44 -> 17 words (-61.4%)
```

The failing files are listed in `reports/build.json` under `gates.wordcount.failing`, and the numbers for every file under `gates.wordcount.files` (`source`, `epub`, `diff`). A negative `diff` means the EPUB has fewer words than the source, a positive one more. `mdbindery check --build` reports the same as MB902.

Causes:

- HTML whose text the conversion drops. In the example above, a `<textarea>` held 27 words that pandoc's HTML reader leaves out; the file's log line also says `HTML removed: <textarea>x1`.
- Raw HTML that is read differently for the two counts, for example a `<div>` without its `</div>`, or an HTML block followed by Markdown without a blank line in between (GitHub's rules then make the Markdown part of the HTML block). `mdbindery check` lists unsupported and removed tags (MB500, MB501).

A chapter with cards fails like any other. For such a file, `build.json` also has `card_labels` (the repeated column labels the gate subtracted) and `compared` (the EPUB count after that), and the log shows `compared`.

To find the difference, build with `--keep-work`, open the prepared file `kNN.md` from the work folder next to the chapter's XHTML from the EPUB, and look for the first place where they differ. `wordcount_tolerance` and `wordcount_min_words` ([configuration.md](configuration.md#validation-gates)) adjust the threshold; raise them only when you know where the difference comes from.

### Time limits

Every external program runs with a time limit ([building.md](building.md#the-pipeline)). When one runs out, mdbindery stops the program and all its child processes and ends the build with exit status 2: `build error: pandoc did not finish within 1800 s and was stopped (set MDBINDERY_TIMEOUT_SCALE=2 or more for very large books or slow machines)`. `reports/build.json` names the stage that stopped (`failed_stage`). A chart that runs out of time becomes a placeholder and fails the charts gate; EPUBCheck or Ace running out of time fails its gate.

If the book is simply large or the machine slow, raise every limit with `MDBINDERY_TIMEOUT_SCALE=3 mdbindery build`. If a tool hangs on a small book, run `mdbindery doctor`: a tool that hangs there is broken or blocked, often by Chrome that cannot start ([Puppeteer and Chrome launch failures](#puppeteer-and-chrome-launch-failures)).

## Reproducible output

The same commit should build to a byte-identical EPUB ([building.md](building.md#reproducible-builds)). When it does not:

- The log shows `warning: generated identifier ... for this build only`: the configuration has no `identifier:` line, so every build gets a random identifier. Add `identifier:` (empty) under `metadata:`; the next build writes a permanent value there.
- The builds ran on two machines: a generated cover depends on the fonts installed, and different versions of pandoc, Pillow, or mermaid-cli produce different bytes. Compare `mdbindery doctor` on both.
- The book folder is a git repository on one machine but not on the other (for example, a copy without `.git`): the timestamp then comes from `metadata.date` or from file modification times. Set `metadata.date` to a fixed `YYYY-MM-DD` value to make the fallback stable.
- Uncommitted changes do not change the git timestamp, so two builds of different text can carry the same date. Commit before a release build.

To see what differs, unzip both files into two folders and compare them with `diff -r`.

## Configuration errors

The build stops with exit status 2 and one line on stderr. Messages you may see, with what to do:

- `config error: invalid YAML in mdbindery.yaml, line 2, column 14: mapping values are not allowed here`: a YAML syntax error at that place. Quote values that contain `: ` or start with a special character (`title: "Mars: the plan"`).
- `config error: unknown top-level key "metdata" (did you mean "metadata"?): its settings would be ignored`: a misspelled section name. Unknown keys inside a section only give a `config warning:` line, with the same "did you mean" hint, and are ignored.
- `config error: mdbindery.yaml must contain a mapping of keys to values`: the file is not a set of `key: value` lines.
- `config error: metadata must be a mapping of keys to values` (also for `cover` and `options`), or `options.cards must be a mapping (files, min_columns, title_columns)`: a section written as a single value.
- `config error: files must be a list`, `options.drop_lines must be a list` (also `embed_fonts`, `ace_waivers`, `reference_headings`): a list is written as `[a, b]` or as lines starting with `- `.
- `config error: files entry 1 has no "file:" key`, `files entry ../01-one.md: use a path relative to the book folder (no absolute paths, no ..; set source_dir instead)`, `file listed twice in files: ['01-one.md']`, or `files entry 01-one.md: key must use letters, digits, and underscores`: fix the entry in `files:`.
- `config error: metadata.lang must be a language code in quotes, e.g. lang: 'no' (YAML reads no as false)`: YAML reads `no`, `yes`, `on`, and `off` as true or false.
- `config error: options.toc_depth must be between 1 and 6`, `options.ace must be true or false`, `options.citations must be 'refdefs' or 'none'`, `options.mermaid_theme must be one of: default, neutral, dark, forest, base`: a value of the wrong kind or out of range. [configuration.md](configuration.md#validation-of-the-configuration-file) lists the rules.
- `config error: options.drop_lines: invalid pattern '(x': missing ), unterminated subpattern at position 0`: a regular expression that does not compile.
- `config error: options.extra_css: file not found: nothere.css` (also `css` and `embed_fonts`): the path is relative to the configuration file's folder.
- `config error: slug may use letters, digits, dots, hyphens, and underscores only (it names the EPUB file)`.
- `config error: source_url must start with https://`.
- `config error: source folder not found: <path>`: `source_dir`, or the folder given on the command line, does not exist (`source_dir` is relative to the configuration file).
- `config error: config file not found: <path>`: the file given with `--config` does not exist.

`mdbindery check` reports configuration problems as MB102.

## Internal errors

Problems with the book, the configuration, or the tools end with a one-line `config error:`, `build error:`, `check error:`, `init error:`, or `preview error:` message (exit status 2) or with failed gates (exit status 1). Any other failure inside mdbindery is a bug. It ends with exit status 3 and a short report on stderr instead of a bare Python traceback:

```
internal error: <exception type>: <message>
please report it with the text below: https://github.com/sagol/mdbindery/issues
```

The last lines of the traceback follow. Report the problem at the address shown, with the command you ran, the whole message, and `mdbindery doctor` output. If the message makes the cause clear (a path that is not what mdbindery expects, a file it cannot read), you can often work around it until it is fixed.


## PDF export errors

- `unrecognized arguments: --format pdf`: installed release lacks PDF support. Upgrade to version `0.2.0` or newer with the `pdf` extra.
- `PDF needs pypdf`: install `mdbindery[pdf]` in the same Python environment as the CLI.
- Missing Node/Puppeteer: run `mdbindery install-tools` without `--no-node`. `doctor` does not check pypdf.
- `PDF resources or internal links failed`: check images, anchors and CSS. Browser requests allow only staged assets and data URLs. List CSS fonts in `options.embed_fonts` and reference those exact paths. Remote CSS resources and unstaged files are blocked.
- Browser sandbox cannot start: PDF does not retry without it. On a trusted CI/container host, explicitly set `MDBINDERY_NO_SANDBOX=1`. See [PDF resource handling](pdf.md#checks-and-failures).
- `gates.pdf.result: fail`: inspect missing-word counts, fonts and CSS that hides text. The generated PDF remains for inspection; renderer errors preserve an older output instead. Do not increase tolerances merely to hide content loss.

For page settings and visual checks, see [PDF export](pdf.md). EPUB preview does not accept PDF files.
