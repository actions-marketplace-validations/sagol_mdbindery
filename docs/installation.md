# Installation

mdbindery is a Python command that drives external tools: pandoc for the conversion, EPUBCheck (a Java program) for validation, and Node.js with mermaid-cli and DAISY Ace for charts, the accessibility check, and EPUB screenshots. Optional PDF export uses the installed Chromium with pypdf from the `pdf` extra; see [PDF setup](pdf.md#install-pdf-dependencies). The installers set all of this up in a per-user folder. No administrator rights are needed, and the system Python is left alone.

## Requirements

- Linux (x64 or arm64, glibc-based distributions), macOS (Intel or Apple silicon), or Windows 10/11 (x64 or arm64).
- Linux and macOS: `bash`, `curl`, `tar`, and `sha256sum` or `shasum`. Windows: PowerShell 5.1 or 7+.
- About 1.5 GB of free disk space for the full tool set, or about 370 MB without the Node.js tools (see [Disk space](#disk-space)).
- An internet connection while installing. Building a book works offline; `mdbindery check <URL>` needs the network to fetch the repository.

## One-line install

The one-line commands download the installer from `raw.githubusercontent.com` and the mdbindery source from `github.com/sagol/mdbindery`, so they work only while that repository is public and reachable. From a checkout, use `--local` (`-Local` on Windows) instead; nothing is then fetched from the mdbindery repository.

### Linux and macOS

```
curl -fsSL https://raw.githubusercontent.com/sagol/mdbindery/main/install/install.sh | bash
```

To pass options through the pipe, put them after `bash -s --`:

```
curl -fsSL https://raw.githubusercontent.com/sagol/mdbindery/main/install/install.sh | bash -s -- --no-node
```

From a checkout of the repository:

```
bash install/install.sh --local .
```

### Windows

In PowerShell:

```
irm https://raw.githubusercontent.com/sagol/mdbindery/main/install/install.ps1 | iex
```

`iex` cannot pass parameters. To use them, run the downloaded text as a script block:

```
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/sagol/mdbindery/main/install/install.ps1))) -NoNode
```

Or save the script and run it as a file:

```
irm https://raw.githubusercontent.com/sagol/mdbindery/main/install/install.ps1 -OutFile install.ps1
powershell -ExecutionPolicy Bypass -File .\install.ps1 -NoNode
```

From a checkout of the repository:

```
powershell -ExecutionPolicy Bypass -File .\install\install.ps1 -Local .
```

When the installer finishes, open a new terminal and run `mdbindery doctor` (see [Verifying the installation](#verifying-the-installation)).

### A fixed version

The commands above install the latest code on `main`. To install a release, take the installer from its tag and pass the same tag as `--ref` (`-Ref` on Windows):

```
curl -fsSL https://raw.githubusercontent.com/sagol/mdbindery/v0.1.1/install/install.sh | bash -s -- --ref v0.1.1
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/sagol/mdbindery/v0.1.1/install/install.ps1))) -Ref v0.1.1
```

The installers never ask questions and exit with a non-zero status when a step fails, so they can run unattended in provisioning scripts and CI.

## Package managers and CI

Every channel installs the same `mdbindery` command. The external tools always come from `mdbindery install-tools`, which puts them in the tool home described above; the one-line installers run it for you, the other channels leave it to you.

| Channel | Install | Update |
|---|---|---|
| PyPI with pipx | `pipx install mdbindery` | `pipx upgrade mdbindery` |
| PyPI with uv | `uv tool install mdbindery` | `uv tool upgrade mdbindery` |
| PyPI with pip | `python -m pip install mdbindery` (in a virtual environment) | `python -m pip install -U mdbindery` |
| Homebrew (macOS, Linux) | `brew install sagol/tap/mdbindery` | `brew upgrade mdbindery` |
| A release's files | the wheel or source archive from the [releases page](https://github.com/sagol/mdbindery/releases): `pipx install ./mdbindery-0.1.1-py3-none-any.whl` | install the newer file |

After any of these, run:

```
mdbindery install-tools
mdbindery doctor
```

To pin a version: `pipx install mdbindery==0.1.1`, `uv tool install mdbindery==0.1.1`.

### GitHub Actions

The repository is also a GitHub Action. It installs mdbindery with uv, runs `mdbindery install-tools`, puts `mdbindery` on `PATH`, sets `MDBINDERY_HOME`, and caches the tools between runs, on Linux, macOS, and Windows runners:

```yaml
jobs:
  ebook:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: sagol/mdbindery@v0.1.1
      - run: mdbindery check . --build
      - run: mdbindery build
      - uses: actions/upload-artifact@v4
        with:
          name: epub
          path: dist/
```

| Input | Default | Meaning |
|---|---|---|
| `version` | the ref in `uses:` | Another mdbindery to install: a PyPI version such as `0.1.0`, or a git ref of `sagol/mdbindery` such as `main`. |
| `node` | `true` | Install Node.js, mermaid-cli, and Ace. `false` is faster; charts then become placeholders, the Ace gate warns, and `preview` does not work. |
| `java` | `auto` | Passed to `install-tools --java`: `auto`, `always`, or `never`. GitHub's runners have Java, so `auto` downloads nothing. |
| `cache` | `true` | Cache `<tool home>/tools` with `actions/cache`, keyed by runner OS, architecture, mdbindery version, and the two inputs above. |

The output `home` is the tool home (`$RUNNER_TOOL_CACHE/mdbindery`). The build's exit status fails the job when a gate fails (1) or the input is wrong (2).

## What the installer does

`install.sh` and `install.ps1` follow the same steps.

1. They pick the folders. The tool home is `MDBINDERY_HOME`, or the per-system default listed under [Environment variables](#environment-variables). The `mdbindery` command goes to `MDBINDERY_BIN`, by default `~/.local/bin` (Windows: `%USERPROFILE%\.local\bin`). Both folders are created if they do not exist.
2. They get uv. If `uv` is on `PATH`, or a copy from an earlier run is in `<tool home>/uv/`, that copy is used. Otherwise the installer downloads [uv](https://github.com/astral-sh/uv) 0.12.19 from its GitHub releases, compares the SHA-256 of the archive with the value written in the script, stops on a mismatch, and puts the binary in `<tool home>/uv/`.
3. They install mdbindery in an isolated environment. The installer points uv at the tool home (`UV_TOOL_DIR=<tool home>/uv-tools`, `UV_PYTHON_INSTALL_DIR=<tool home>/python`, `UV_TOOL_BIN_DIR=<bin folder>`) and runs `uv tool install --force --python 3.12` on either the local folder (`--local`) or `https://github.com/sagol/mdbindery/archive/<ref>.zip`, so git is not needed. uv uses a Python 3.12 already on the machine or downloads one into `<tool home>/python`, creates a private environment with mdbindery, PyYAML, and Pillow, and links the `mdbindery` command into the bin folder. uv's output is shown only when it fails, followed by `uv could not install mdbindery`.
4. They run `mdbindery install-tools` (skipped with `--no-tools`), described in the next section. The Windows installer always passes `--java` with the chosen mode (default `auto`). If `install-tools` fails, the installer stops with its error.
5. They check `PATH`. On Linux and macOS, if the bin folder is not on `PATH`, the installer prints the line to add to your shell profile; it does not edit profile files. On Windows it adds the bin folder to the user `PATH` (the value is kept unexpanded, so entries such as `%USERPROFILE%\bin` stay as they are) and prints `added <folder> to your user PATH (open a new terminal to use it)`.
6. When the tool home is not the default one, they print the line that sets `MDBINDERY_HOME` permanently, because every later `mdbindery` command must find the same tool home.

A run of `install.sh` from a checkout with a custom tool home and bin folder (paths shortened):

```
getting uv 0.12.19 (uv-x86_64-unknown-linux-gnu.tar.gz)
installing mdbindery from .../mdbindery
mdbindery tool home: .../inst/home
pandoc 3.11: downloading pandoc-3.11-linux-amd64.tar.gz
EPUBCheck 5.4.0: downloading
Java: using /usr/bin/java (version 25)
--- tools
pandoc     pandoc 3.11
epubcheck  EPUBCheck v5.4.0
java       /usr/bin/java (version 25)
node       missing
mermaid    missing
ace        missing
python     3.12.14 (PyYAML 6.0.3, Pillow 12.3.0)

add .../inst/bin to your PATH, e.g.:
  echo 'export PATH=".../inst/bin:$PATH"' >> ~/.profile

the tools are in .../inst/home; mdbindery finds them only with MDBINDERY_HOME set, e.g.:
  echo 'export MDBINDERY_HOME=".../inst/home"' >> ~/.profile

done: run 'mdbindery doctor' to confirm, then 'mdbindery check <book-folder-or-repo-url>'
```

That run used `--no-node`, so the Node.js tools are `missing`. On Windows the `MDBINDERY_HOME` hint is a PowerShell line: `[Environment]::SetEnvironmentVariable('MDBINDERY_HOME', '<folder>', 'User')`.

### What `mdbindery install-tools` does

```
mdbindery install-tools [--no-node] [--java {auto,always,never}] [--force]
```

The command installs into `<tool home>/tools/`, in this order. Each component folder holds a `.mdbindery-version` marker; a component whose marker matches the pinned version is skipped (`pandoc 3.11: already installed`) unless you pass `--force`. The pinned versions and SHA-256 checksums live in `src/mdbindery/installer.py`.

1. pandoc 3.11 from the pandoc GitHub releases into `tools/pandoc/`, SHA-256 checked. Required.
2. EPUBCheck 5.4.0 from the EPUBCheck GitHub releases into `tools/epubcheck/`, SHA-256 checked. Required.
3. Java, according to `--java`:
   - `auto` (default): an existing Java 11 or newer is used, first a runtime in `tools/jre/`, then `java` on `PATH` (`Java: using /usr/bin/java (version 25)`). Only when no Java 11+ is found does the command download the latest Eclipse Temurin 21 JRE through the Adoptium API into `tools/jre/`, checked against the SHA-256 that the API returns. With `--force`, a runtime downloaded earlier into `tools/jre/` is downloaded again.
   - `always`: download the Temurin JRE even when another Java is present (skipped if `tools/jre/` already holds it, unless `--force`).
   - `never`: do nothing. EPUBCheck then needs a Java 11+ on `PATH` (or a runtime installed earlier in `tools/jre/`).
4. Unless `--no-node`, the optional Node.js tools:
   - Node.js 24.21.0 from nodejs.org into `tools/node/`, SHA-256 checked.
   - `npm install -g --prefix tools/.staging-npm @mermaid-js/mermaid-cli@12.0.0 @daisy/ace@1.4.6`, swapped into `tools/npm` when both packages are there, with Puppeteer's and Electron's own browser downloads turned off. npm's cache is pointed at `tools/npm-cache/` during the install and deleted afterwards, so nothing is left in `~/.npm`. The two packages are pinned by version; their dependencies are resolved by npm at install time.
   - For every copy of Puppeteer inside those packages, `puppeteer browsers install chrome-headless-shell` into `tools/puppeteer/`. mermaid-cli and Ace bring different Puppeteer versions, so two headless Chrome builds are installed. This step runs on every `install-tools` call, so it also restores a deleted browser.

   These steps are best effort. If one fails, the command prints `warning: Node.js tools not installed: <reason>` and `charts become placeholders, Ace and preview are unavailable; run install-tools again later`, the tool table gets a `node: install failed: ...` note, and the command still succeeds when pandoc and EPUBCheck work.
5. `tools/puppeteer-config.json`, the Chrome launch flags for mermaid-cli, is written. mdbindery rewrites it on every run to match the sandbox setting (see [Headless Chrome](#headless-chrome)), so edits to it do not last.
6. The same self-test as `mdbindery doctor` runs and prints the tool table.

Every archive is unpacked safely: an entry whose path or link target would land outside the target folder, or a special file such as a device, stops the install with `install failed: unsafe path in archive: ...` (or `unsafe link`, `unsupported member`).

Updates are transactional. Each component is unpacked into a staging folder next to its final place (`tools/.staging-pandoc`), started once to prove it runs (`pandoc --version`, `java -version`, `node --version`; for EPUBCheck, its jar must be there; for the npm packages, both must be installed), and only then swapped in. The previous version waits as `tools/.old-<name>` until the new one passes, so a failed download, extraction, or check leaves the working version in place with its marker, and the next `install-tools` starts clean. One `install-tools` runs at a time per tool home: a second one stops with `another \`mdbindery install-tools\` is running (lock file .../tools/.install.lock)`. A lock file older than three hours counts as abandoned; delete it yourself if an install was killed.

Exit status: 0 when pandoc and EPUBCheck work afterwards; 1 when either is missing (`required tools are missing: ...`, for example with `--java never` and no Java); 2 when a required step failed (the message starts with `install failed:`, for example a download error or a checksum mismatch).

## Installer options

| `install.sh` | `install.ps1` | Effect |
|---|---|---|
| `--local PATH` | `-Local PATH` | Install mdbindery from a local folder (a checkout) instead of GitHub |
| `--ref REF` | `-Ref REF` | Branch, tag, or commit to install from GitHub; default `main` |
| `--no-node` | `-NoNode` | Skip Node.js, mermaid-cli, Ace, and headless Chrome. Mermaid charts become placeholders (the charts gate warns), the Ace gate warns that accessibility was not checked, and `mdbindery preview` does not work |
| `--java MODE` | `-Java MODE` | `auto` (default), `always`, or `never`, as described above |
| `--no-tools` | `-NoTools` | Install only the `mdbindery` command; run `mdbindery install-tools` later |
| `--uninstall` | `-Uninstall` | Remove mdbindery, its tools, and its Python (see [Uninstalling](#uninstalling)) |
| `-h`, `--help` | none | Print the option summary; also works as `curl ... \| bash -s -- --help` |

Wrong arguments stop `install.sh` before it changes anything:

| Input | Message | Exit status |
|---|---|---|
| `--local` or `--ref` without a value, or followed by another option | `--local needs a value` (or `--ref needs a value`) | 2 |
| `--local` with a folder that has no `pyproject.toml` (not the mdbindery source, or no such folder) | `error: --local needs the mdbindery source folder (with pyproject.toml): <folder>` | 2 |
| `--java` without `auto`, `always`, or `never` | `--java needs auto, always, or never` | 2 |
| Any other option | `unknown option: <option>` | 2 |

`install.ps1` uses PowerShell's own parameter checks: an unknown parameter or a `-Java` value outside the three modes is rejected by PowerShell before the script runs.

You can run `mdbindery install-tools` again at any time with different options, for example to add Node.js after an install with `--no-node`.

## Environment variables

| Variable | Read by | Meaning |
|---|---|---|
| `MDBINDERY_HOME` | the installers and every `mdbindery` command | Tool home. mdbindery looks for its tools here on every run, so if you install with a custom value, set it permanently (in your shell profile, or as a Windows user environment variable). The installers print the line to use |
| `MDBINDERY_BIN` | the installers | Folder for the `mdbindery` command. Default `~/.local/bin`; Windows `%USERPROFILE%\.local\bin` |
| `MDBINDERY_NO_SANDBOX` | `mdbindery` | Any non-empty value starts Chrome without its sandbox (mermaid-cli and `preview`) |
| `MDBINDERY_TIMEOUT_SCALE` | `mdbindery` | Multiplies every time limit for external programs (see [building.md](building.md#the-pipeline)); `3` triples them for a slow machine or a very large book |
| `CI` | `mdbindery` | Any non-empty value, as set by CI services, has the same effect as `MDBINDERY_NO_SANDBOX` |
| `XDG_DATA_HOME` | `mdbindery` and `install.sh` on Linux | Base folder of the default tool home |
| `LOCALAPPDATA` | `mdbindery` and `install.ps1` on Windows | Base folder of the default tool home |
| `HTTPS_PROXY`, `HTTP_PROXY`, `NO_PROXY` | the downloaders | Proxy settings; see [Corporate proxies](troubleshooting.md#corporate-proxies) |

Default tool home:

| System | Default |
|---|---|
| Linux | `$XDG_DATA_HOME/mdbindery`, or `~/.local/share/mdbindery` when `XDG_DATA_HOME` is not set |
| macOS | `~/Library/Application Support/mdbindery` |
| Windows | `%LOCALAPPDATA%\mdbindery` |

`mdbindery doctor` prints the tool home in use and adds `(default; set MDBINDERY_HOME to use another)` when `MDBINDERY_HOME` is not set.

The installers set `UV_TOOL_DIR`, `UV_TOOL_BIN_DIR`, and `UV_PYTHON_INSTALL_DIR` for their own run, so values you use for uv elsewhere are ignored during installation and are not changed. When mdbindery starts a tool, it puts the folder of the Node.js it uses first on `PATH` and sets `PUPPETEER_CACHE_DIR` to `<tool home>/tools/puppeteer` for that process (and, for Ace, `PUPPETEER_EXECUTABLE_PATH`).

The tool home after a full install:

```
<tool home>/
├── uv/                     uv, if the installer downloaded it
├── uv-tools/               the isolated environment with mdbindery, PyYAML, and Pillow
├── python/                 Python 3.12, if uv had to download one
└── tools/
    ├── pandoc/
    ├── epubcheck/
    ├── jre/                only if a Java runtime was downloaded
    ├── node/
    ├── npm/                mermaid-cli and Ace
    ├── puppeteer/          headless Chrome builds
    ├── puppeteer-config.json
    └── no-sandbox          only after Chrome reported that its sandbox cannot run
```

A manual install (see below) creates only `tools/`.

## External tools

| Tool | Installed version | If you provide it yourself | Used for | How the download is checked |
|---|---|---|---|---|
| uv | 0.12.19 | Any `uv` on `PATH` is used | Installs mdbindery and, if needed, Python (installers only) | SHA-256 in `install.sh` and `install.ps1` |
| Python | 3.12 (installers) | 3.9 or newer for manual installs | Runs mdbindery | Chosen by uv |
| pandoc | 3.11 | 3.8 or newer on `PATH`, used when the tool home has none; an older one is ignored | Reads Markdown, runs the Lua filter, writes the EPUB | SHA-256 in `installer.py` |
| EPUBCheck | 5.4.0 | Only the copy in the tool home is used | The epubcheck gate | SHA-256 in `installer.py` |
| Java | an existing Java 11+, or the latest Eclipse Temurin 21 JRE | 11 or newer on `PATH`, used when `tools/jre/` has none | Runs EPUBCheck | SHA-256 returned by the Adoptium API |
| Node.js | 24.21.0 | `node` on `PATH`, used when `tools/node/` has none | Runs mermaid-cli, Ace, and `mdbindery preview` | SHA-256 in `installer.py` |
| mermaid-cli | 12.0.0 | Only the copy in `tools/npm/` is used | Renders Mermaid charts to PNG | Pinned version; npm checks package integrity; dependencies resolved by npm |
| DAISY Ace | 1.4.6 | Only the copy in `tools/npm/` is used | The ace gate | Pinned version; npm checks package integrity; dependencies resolved by npm |
| chrome-headless-shell | the builds the bundled Puppeteer copies request | Only the builds in `tools/puppeteer/` are used | Page rendering for mermaid-cli, Ace, EPUB `preview`, and PDF export | Downloaded by Puppeteer; mdbindery does not check it |
| git | any | Optional | The build timestamp; `mdbindery check` of repositories | Not downloaded |

On Windows arm64 the x64 build of pandoc is installed (there is no arm64 build) and runs under emulation.

## Disk space

Measured on Linux x64 with `du -sh`:

| Part | Size |
|---|---|
| `tools/pandoc/` | 157 MB |
| `tools/epubcheck/` | 35 MB |
| `tools/node/` | 204 MB |
| `tools/npm/` (mermaid-cli and Ace) | 548 MB |
| `tools/puppeteer/` (two headless Chrome builds) | 522 MB |
| `uv/` (only if the installer downloaded uv) | 49 MB |
| `python/` (only if uv downloaded Python 3.12) | 107 MB |
| `uv-tools/` (the mdbindery environment) | 23 MB |

- Full tool set: about 1.5 GB in `tools/`.
- With `--no-node`: about 190 MB in `tools/`. A `--no-node` install that also downloaded uv and Python took 368 MB for the whole tool home.
- A downloaded Java runtime adds about 130 MB.
- Outside the tool home, uv keeps its download cache (28 MB after that `--no-node` install; `uv cache dir` prints where). npm's cache is kept inside the tool home during `install-tools` and deleted afterwards.

To see what your install takes, run `du -sh "$MDBINDERY_HOME"`, or `du -sh ~/.local/share/mdbindery` for the Linux default.

## Headless Chrome

mermaid-cli, Ace, and `mdbindery preview` run a headless Chrome build downloaded by Puppeteer. On Linux that browser needs system libraries that minimal installations, containers, and WSL images often lack. If `mdbindery doctor` reports `mermaid    installed but cannot render: ...`, or the build log shows `Ace: FAILED to run: ...`, install them. A typical set for Debian and Ubuntu (not an exhaustive list):

```
sudo apt install libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 libgbm1 libpango-1.0-0 libasound2
```

On Ubuntu 24.04 and later, `libasound2` is a virtual package: install `libasound2t64` instead. Other distributions ship the same libraries under similar names.

To see exactly what is missing, ask the dynamic linker (Linux x64 path shown):

```
ldd "${MDBINDERY_HOME:-$HOME/.local/share/mdbindery}"/tools/puppeteer/chrome-headless-shell/*/chrome-headless-shell-linux64/chrome-headless-shell | grep "not found"
```

Then run `mdbindery doctor` again.

Chrome's sandbox stays on for mermaid-cli and `preview` wherever it works. mdbindery turns it off in these cases:

- mdbindery runs as root (in most containers);
- `CI` or `MDBINDERY_NO_SANDBOX` is set;
- Chrome failed with a message about its sandbox, for example on a system that restricts unprivileged user namespaces. mdbindery then retries without the sandbox, logs `warning: Chrome's sandbox cannot start on this machine; Mermaid now renders without it`, and writes `<tool home>/tools/no-sandbox`, so later runs start without it.

`preview` follows the marker and the variables above, but its own sandbox failure is not remembered: it warns and takes that run's screenshots without the sandbox. It also keeps scripts off and loads only the EPUB's own files (see [building.md](building.md#previewing-pages)).

PDF requires an explicit `MDBINDERY_NO_SANDBOX=1` to disable its sandbox; it neither retries automatically nor follows the Mermaid marker. See [PDF security and failures](pdf.md#checks-and-failures).

`mdbindery doctor` shows `mermaid    renders PNG (Chrome sandbox off)` when the sandbox is off. To try the sandbox again after changing the system, delete `tools/no-sandbox`. Ace always starts its Chrome without the sandbox (a setting inside Ace); it only opens the EPUB that was just built. Other launch problems are covered in [troubleshooting](troubleshooting.md#puppeteer-and-chrome-launch-failures).

## Manual installation

Use this when you prefer your own Python tooling. mdbindery needs Python 3.9 or newer. Get the source first:

```
git clone https://github.com/sagol/mdbindery
cd mdbindery
```

Then install it with one of:

```
pipx install .
uv tool install .
python3 -m venv .venv && .venv/bin/python -m pip install .
```

On Windows the last form is `python -m venv .venv` followed by `.venv\Scripts\python -m pip install .`. For development, use an editable install (`pip install -e ".[test]"`); see [design.md](design.md#tests).

Then download the external tools into the tool home (same defaults and `MDBINDERY_HOME` as above):

```
mdbindery install-tools            # or: --no-node, --java always|never, --force
mdbindery doctor
```

If you cannot run `install-tools`, mdbindery can use some tools you provide yourself, as listed in the "If you provide it yourself" column of [External tools](#external-tools):

- pandoc: a `pandoc` 3.8 or newer on `PATH` is used when the tool home has none. mdbindery passes options that older versions reject (`--syntax-highlighting`), so it ignores an older pandoc, and `mdbindery doctor` says so.
- Java: a `java` 11+ on `PATH` is used when `tools/jre/` has none. `JAVA_HOME` is not read.
- EPUBCheck: only the copy in the tool home is used. Unzip the EPUBCheck release so that `<tool home>/tools/epubcheck/<any folder>/epubcheck.jar` exists.
- mermaid-cli and Ace: only the copies that `install-tools` puts in `tools/npm/` are used, because they must be paired with the headless Chrome builds in `tools/puppeteer/`. Without them, charts become placeholders, the Ace gate warns, and `preview` does not work.

## Offline and air-gapped machines

1. On a connected machine with the same operating system and CPU architecture, install mdbindery and run `mdbindery install-tools`. If that machine has its own Java and the target machine has none, add `--java always` so a runtime is downloaded into the tool home.
2. Copy `<tool home>/tools/` to the same place under the target machine's tool home. mdbindery finds everything in `tools/` relative to the tool home at run time, so it can live at a different path. Leave out `tools/no-sandbox` unless the target machine needs Chrome without its sandbox too.
3. Install the mdbindery command on the target machine without network access. On the connected machine (same Python minor version as the target), build wheels:

   ```
   python -m pip wheel ./mdbindery -w wheels     # mdbindery, PyYAML, Pillow
   ```

   Copy `wheels/` over and install from it:

   ```
   python -m pip install --no-index --find-links wheels mdbindery
   ```

   You can instead copy the whole tool home, including `uv-tools/` and `python/`, together with the `mdbindery` command link. This works only if the tool home has the same absolute path on both machines, because the Python environment records absolute paths.
4. On Linux, install the [headless Chrome libraries](#headless-chrome) from the target's package mirror.
5. Set `MDBINDERY_HOME` if you used a non-default location, then run `mdbindery doctor`.

Building needs no network access: a remote image (`https://...`) is never downloaded; it is replaced by a text placeholder and fails the images gate. `mdbindery check <URL>` is the only command besides the installers that needs the network.

## Verifying the installation

`mdbindery doctor` prints the version, the tool home, and one line per tool. A full install in the default tool home (path shortened):

```
mdbindery 0.1.1
tool home: .../.local/share/mdbindery (default; set MDBINDERY_HOME to use another)
--- tools
pandoc     pandoc 3.11
epubcheck  EPUBCheck v5.4.0
java       /usr/bin/java (version 25)
node       v24.21.0
mermaid    renders PNG
ace        1.4.6
python     3.12.14 (PyYAML 6.0.3, Pillow 12.3.0)
```

`doctor` exits with 0 when pandoc and EPUBCheck work, even if the Node.js tools are missing, and with 1 otherwise.

- `missing` on the `pandoc` or `epubcheck` line: builds stop (no pandoc) or fail the epubcheck gate. `doctor` ends with ``required tools are missing: run `mdbindery install-tools` ``. When `MDBINDERY_HOME` is not set and the default tool home has no `tools/` folder, it adds `if you installed the tools into another folder, set MDBINDERY_HOME to it first`.
- Notes under the table explain a missing tool:
  - `pandoc: <path> (3.1) on PATH is older than 3.8 and is not used`;
  - `epubcheck: needs Java 11 or newer` (the jar is there, Java is not);
  - `epubcheck: installed but does not run: Error: Invalid or corrupt jarfile .../epubcheck.jar` (a damaged download: run `mdbindery install-tools --force`);
  - `node: install failed: ...` (the last `install-tools` could not install the Node.js tools).
- `mermaid` runs a real test render. `renders PNG (Chrome sandbox off)` is normal in containers and CI. `installed but cannot render: ...` means headless Chrome cannot start, and `doctor` adds `Mermaid charts will become placeholders (see docs/installation.md, "Headless Chrome").`; see [Headless Chrome](#headless-chrome). `missing` means the Node.js tools are not installed, and `doctor` adds `mermaid-cli is not installed (tools installed with --no-node): charts become placeholders.`
- `ace missing`: `doctor` adds ``Ace is not installed: builds skip the accessibility check, and `preview` does not work (run `mdbindery install-tools`).`` Builds still pass, with the ace gate at `warn`.

## Updating

- One-line install: run the same installer command again. It reinstalls mdbindery from `main` (or from `--ref`), then `install-tools` downloads only the components whose pinned version changed.
- PyPI or Homebrew: `pipx upgrade mdbindery`, `uv tool upgrade mdbindery`, or `brew upgrade mdbindery`, then `mdbindery install-tools`.
- Manual install: update the checkout (`git pull`) and reinstall the package the way you installed it (`pipx install --force .`, `uv tool install --force .`, or `pip install .` in the venv), then run `mdbindery install-tools`.
- `mdbindery install-tools --force` downloads every component again, including a Java runtime downloaded earlier.
- The downloaded JRE is marked with its major version only (21), and `--java auto` keeps using any working Java. To refresh a downloaded JRE, run `mdbindery install-tools --java always --force`.
- Old headless Chrome builds stay in `tools/puppeteer/` after Puppeteer versions change. To reclaim the space, delete that folder and run `mdbindery install-tools`.

## Uninstalling

Installed with the one-line installer, on Linux and macOS:

```
curl -fsSL https://raw.githubusercontent.com/sagol/mdbindery/main/install/install.sh | bash -s -- --uninstall
```

On Windows, any of the forms under [Windows](#windows) works with `-Uninstall`, for example:

```
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/sagol/mdbindery/main/install/install.ps1))) -Uninstall
```

Run it with the same `MDBINDERY_HOME` and `MDBINDERY_BIN` values you installed with. Uninstalling runs `uv tool uninstall mdbindery`, deletes the `mdbindery` command from the bin folder, and deletes the four folders mdbindery created in the tool home: `tools/`, `uv/`, `uv-tools/`, and `python/`. The tool home folder itself is deleted only when nothing else is left in it, so other files you keep there survive. It prints `mdbindery removed from <tool home>`.

On Windows, `-Uninstall` also takes the bin folder out of the user `PATH` when the folder is empty afterwards; a folder that still holds other programs stays on `PATH`. The script ends with `return` rather than `exit`, so running it through `iex` or a script block does not close the PowerShell window, and it works in Windows PowerShell 5.1 as well as PowerShell 7.

Not removed:

- uv's download cache (`uv cache dir` prints where it is, if uv is still installed).
- The bin folder itself, and any `PATH` line you added to a shell profile.
- A uv you installed yourself.

Installed from PyPI, Homebrew, or manually: uninstall the package (`pipx uninstall mdbindery`, `uv tool uninstall mdbindery`, `brew uninstall mdbindery`, or delete the venv), then delete the tool home folder.

## Optional PDF export

PDF needs the `pdf` Python extra and the Node/Puppeteer tools; an install with `--no-node` cannot export PDF. See [PDF installation](pdf.md#install-pdf-dependencies). PDF support is unreleased; version `0.1.1` lacks it. Install the source checkout with `python -m pip install '.[pdf]'` in your Python environment. Base installers omit this extra. `doctor` checks the EPUB toolchain; a successful `doctor` run does not prove pypdf is installed.
