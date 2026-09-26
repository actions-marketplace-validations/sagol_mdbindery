# Checking a book

`mdbindery check` is a dry run. It reads a book from a local folder or a Git repository, reports every problem it can find with a code, file, line, and suggested fix, and can run a trial build with the same gates as `mdbindery build`. It never changes the book's files, never writes into its configuration, and does not write `dist/`.

```
mdbindery check                                   # the book in the current folder
mdbindery check path/to/book --build              # the same, plus a trial build
mdbindery check https://github.com/you/book       # a GitHub repository
```

The rules behind the checks are in [book-structure.md](book-structure.md), and the configuration keys mentioned below are in [configuration.md](configuration.md).

## Usage

```
mdbindery check [TARGET] [-c FILE] [--ref REF] [--build] [--no-render]
                [--report FILE] [--json FILE] [-q]
```

### Targets

`TARGET` defaults to `.`. A path that exists is always read as a local folder, even when it looks like a URL.

| Target | Examples | What is checked |
|---|---|---|
| Local folder | `.`, `path/to/book` | The book in that folder, with its `mdbindery.yaml` or `mdbindery.yml` if present. |
| GitHub repository | `https://github.com/you/book`, `github.com/you/book`, `www.github.com/you/book` (a trailing `/` or `.git` is fine) | The default branch, from the repository root. |
| GitHub branch or subfolder | `https://github.com/you/book/tree/dev`, `https://github.com/you/repo/tree/main/books/mars` | That branch; with a path after the branch, the book in that subfolder. |
| GitHub over SSH | `git@github.com:you/book.git`, `ssh://git@github.com/you/book` | The default branch, or `--ref`. There is no subfolder form. |
| Other Git URL | `https://gitlab.com/you/book.git`, `ssh://host/book`, `git://host/book`, `file:///srv/git/book.git`, any target ending in `.git` | The default branch, or `--ref`. Needs `git`. |

Any `http://`, `https://`, `ssh://`, `git://`, or `file://` URL that is not a GitHub URL, and any target that starts with `git@`, is handed to `git clone` as is.

In a `/tree/` URL the segment right after `/tree/` is the branch and the rest is the subfolder. `--ref` names the branch or tag to check and replaces the branch written in the URL, so a branch whose name contains a slash has to be given with `--ref`:

```
mdbindery check https://github.com/you/book --ref release/1.0
mdbindery check https://github.com/you/repo/tree/main/books/mars --ref release/1.0   # subfolder books/mars
```

A repository is cloned with `git clone --depth 1 --quiet` into a temporary folder (`mdbindery-check-*` in the system temp folder), which is deleted when the check ends, also after an error. The URL is passed to `git` after `--`. Git never prompts: `GIT_TERMINAL_PROMPT=0` is set, and SSH runs with `-o BatchMode=yes` unless you set `GIT_SSH_COMMAND` yourself. A private repository works only if your own `git` can clone it without a prompt (an SSH key in an agent, or a credential helper); otherwise clone it yourself and check the folder.

When `git` is not installed, a GitHub URL, HTTPS or SSH, is downloaded over HTTPS as a ZIP archive of the branch (the default branch comes from the GitHub API, or `main` if the API cannot be reached). That works only for public repositories. Other Git URLs then fail.

While fetching, check prints one progress line to standard error, which stays visible when you redirect the report:

```
$ mdbindery check https://github.com/getify/You-Dont-Know-JS/tree/2nd-ed/get-started > report.md
fetching https://github.com/getify/You-Dont-Know-JS.git (2nd-ed)
```

If the target cannot be used, check prints one line to standard error and exits with code 2. The messages:

| Situation | Message |
|---|---|
| The path does not exist | `check error: folder not found: nosuch` |
| The target looks like a host name without `https://` | `check error: not a folder or repository URL: example.com/foo (did you mean https://example.com/foo?)` |
| The path is a file, such as a configuration file | `check error: not a folder: sample-book/mdbindery.yaml (give the book folder or its repository URL)` |
| The target starts with `-` | `check error: not a folder or repository URL: -x` |
| A GitHub `/blob/` link to one file | `check error: this is a link to a single file; check the repository URL or https://github.com/OWNER/REPO/tree/BRANCH/FOLDER` |
| The branch or tag does not exist | `check error: branch or tag not found: no-such-branch (in https://github.com/getify/You-Dont-Know-JS.git)` |
| The repository does not exist, is private, or needs a password | `check error: repository not found or not accessible: URL`, then on a second line ``mdbindery clones with your git setup and never asks for a password; for a private repository, clone it yourself and run `mdbindery check <folder>` `` |
| The subfolder of a `/tree/` URL does not exist | `check error: subfolder not found in repository: books/mars` |
| The clone takes longer than 10 minutes | `check error: git clone timed out: URL` |
| Any other `git clone` failure | `check error: git clone failed: ` followed by git's message |
| No `git`, and the target is not a GitHub URL | `check error: git is required to check repositories outside GitHub` |
| No `git`; the GitHub API does not know the repository | `check error: repository not found or not public: URL` |
| No `git`; the ZIP archive does not exist | `check error: repository or branch not found: OWNER/REPO (BRANCH)` |
| No `git`; a network error during the download | `check error: ` followed by the error |

#### Repositories checked by URL

A repository fetched by URL is treated as untrusted, because its configuration file comes from someone else. Every path in the configuration must stay inside the repository: `source_dir`, `options.css`, `options.extra_css`, `options.embed_fonts`, and `cover.image`. A path that leaves it is an MB102 error, for example `cover.image must be a file inside the repository`. Images must stay inside the repository too (MB406 error), and so must the files of mdBook `{{#include}}` directives (MB131).

For a GitHub target whose configuration has no `source_url`, check assumes `https://github.com/OWNER/REPO/blob/BRANCH/FOLDER/`, where `FOLDER` is the book folder's path in the repository, for the link analysis and the trial build. Links to files outside the book then behave as they would with that setting. For an mdBook the book folder is its `src` folder, so the mdBook guide gets `https://github.com/rust-lang/mdBook/blob/main/guide/src/`. The value appears in the MB202 notes and in the suggested configuration.

When no title can be found in the files, the repository name becomes the title: `REPO` for a GitHub URL, and the last part of the URL without `.git` for other Git URLs.

### Options

| Option | Meaning |
|---|---|
| `-c FILE`, `--config FILE` | Use this configuration file instead of the one in the book folder. Relative paths in `FILE` are relative to the folder of `FILE`. The book folder is `source_dir` from `FILE` if set, else `TARGET`, which defaults to the current folder (not the folder of `FILE`). With a repository URL, `FILE` must not set `source_dir`, `options.css`, `options.extra_css`, `options.embed_fonts`, or `cover.image`: those paths would point outside the clone and give MB102 errors. |
| `--ref REF` | Branch or tag to check, for repository URLs. |
| `--build` | After the checks, run a trial build with all gates (see [Trial build](#trial-build)). |
| `--no-render` | Do not render Mermaid charts during the analysis. Faster, but chart errors (MB701) go unreported, and the trial build uses placeholders for the charts. |
| `--report FILE` | Also write the Markdown report to `FILE`. |
| `--json FILE` | Also write the JSON report to `FILE`. |
| `-q`, `--quiet` | Do not print the progress line. With `--report` or `--json`, do not print the report either. |

The Markdown report goes to standard output unless `-q` is combined with `--report` or `--json`. Existing report files are overwritten, and missing folders are created. If a report file cannot be written, check prints `check error: cannot write the report: ...` and exits with code 2.

### Trial build

With `--build`, check runs the full build pipeline into a temporary folder (`mdbindery-trial-*`, deleted afterwards) once all the other checks are done, but only if they found no errors. Otherwise the trial build is skipped, and the report says `Trial build: skipped: fix the errors first`.

The trial build runs the same gates as `mdbindery build` ([building.md](building.md#gates)): links, images, includes, charts, EPUBCheck, Ace, and the word count. Its results are reported as:

| Code | From |
|---|---|
| MB900 | each EPUBCheck message (at most 50) |
| MB901 | each Ace violation, per rule, and a warning when Ace is not installed |
| MB902 | the word-count gate |
| MB711 | pandoc warnings about TeX math it could not convert |
| MB904 | every failed gate that no MB900, MB901, or MB902 error already explains |
| MB903 | a trial build that stopped with an error instead of finishing |

So `check --build` never reports `ready to build` after a failed trial build. The trial build catches problems that the static checks cannot see, such as duplicate IDs that EPUBCheck rejects. Ace starts a headless browser, which makes this the slowest part of the check.

The trial build differs from a real build in these ways:

- It never writes into the configuration. An empty `metadata.identifier` gets a temporary `urn:uuid` for this run only.
- For a GitHub target without `source_url`, it uses the assumed `source_url` (see [Targets](#repositories-checked-by-url)).
- When charts are not rendered (`--no-render`, or mermaid-cli missing), it uses placeholders, so its size differs from the real EPUB.
- There is no `--no-ace` for check: Ace runs unless `options.ace` is `false`. When Ace is not installed, the ace gate only warns: the trial build can pass, and the report has an MB901 warning that the accessibility check did not run. When EPUBCheck cannot run, the epubcheck gate fails (MB904) unless `options.epubcheck` is `false`.

The `Trial build:` line of the report, and `facts.trial_build` in the JSON report, is one of:

| Text | Meaning |
|---|---|
| `passed (108 KB)` | Every gate passed; the size of the trial EPUB. |
| `failed: epubcheck (96 KB)` | These gates failed (comma-separated); the size of the trial EPUB. |
| `skipped: fix the errors first` | The checks before the trial build found errors. |
| `failed: ` and an error message | The trial build stopped with an error (MB903). |

### Exit codes

| Code | Meaning |
|---|---|
| 0 | No errors. Warnings and notes may be present. |
| 1 | At least one error, including configuration errors (MB102), an empty reading order (MB100), and trial-build failures (MB900 to MB904). |
| 2 | The target could not be used (see the messages under [Targets](#targets)), or a report file could not be written. |
| 3 | Internal error: mdbindery printed `internal error: ...` and a short traceback to report. |
| 130 | Interrupted with Ctrl+C. |

A broken configuration exits with 1 in check (an MB102 error in the report) and with 2 in `mdbindery build`.

## What check reads

The checks run in this order. The JSON report lists the findings in this order; the Markdown report sorts them by severity and groups them (see [Markdown report](#markdown-report)).

1. Configuration: load `mdbindery.yaml` as the build does. An MB102 error stops the check here. Then MB102 warnings, MB101, MB130, MB100 (which stops the check), and MB125.
2. Reading order: MB103, MB104, MB126.
3. Metadata and cover: MB120 to MB124, MB410 to MB412.
4. Static checks, file by file in reading order: MB105 (encoding), MB131 (includes), MB111, headings (MB106 to MB110), references and footnotes (MB300 to MB306), images (MB400 to MB406), HTML tags (MB500), tables (MB600), and code blocks (MB720). Then the book-wide notes MB107 (repeated first heading) and MB710 (math).
5. Analysis with pandoc, the first half of a real build: link resolution, HTML conversion, and chart rendering (MB700, MB200, MB201, MB202 to MB205, MB501, MB711, MB701, and image problems the static pass missed: MB400, MB401, MB406). Without pandoc this stage is skipped and MB001 is reported. If pandoc fails, MB903.
6. With `--build`, the trial build (MB900 to MB904, MB711).

### Content the static checks skip

The static checks (stage 4) read only what the build would show as text:

- Code. Fenced blocks (```` ``` ```` or `~~~`, three or more) are skipped, also when the fence is indented inside a list item or prefixed with `>` in a block quote. A fence closes with the same character repeated at least as often; an unclosed fence runs to the end of the file. Indented code blocks (four spaces or a tab after a blank line, outside lists) are skipped too.
- HTML comments. A comment that starts a line, with everything up to `-->`, also over several lines, is skipped: headings, definitions, images, and tags inside it are not seen. The HTML, image, citation, footnote, and math checks also ignore comments and inline code spans within a line, so `` `![alt](x.png)` `` in running text is not an image.
- YAML front matter. The lines of a front matter block at the top of a file are blanked, as pandoc drops them; only MB111 reports it.
- Dropped content. Lines that match `options.drop_lines`, and sections named in a file's `drop_sections` (with their subsections), are blanked before the checks. Line numbers stay as in the file.

### Includes and mdBook

mdBook directives are expanded before the static checks, in every book: `{{#include path}}`, the line forms `path:N`, `path:N:M`, `path:N:`, `path::M`, and `path:anchor` (between `ANCHOR:` and `ANCHOR_END:` lines), `{{#rustdoc_include ...}}` (read like include), and `{{#playground path}}`. `{{#title ...}}` is removed, and `\{{#include ...}}` stays as literal text. Paths are relative to the Markdown file and must stay inside the [repository root](configuration.md#the-repository-root), which outside git is the folder with `book.toml`. The included text is checked as part of the file, so line numbers after a multi-line include count the included lines. A directive that cannot be expanded is MB131.

A book is read as an mdBook (MB130) when its folder (`TARGET` or `source_dir`) has a `book.toml` (its `src`, default `src/`, becomes the book folder when it holds `SUMMARY.md`), or when it has a `SUMMARY.md` with a `book.toml` one level up. Title, authors, description, and language then come from `book.toml`, and, when `files:` is not set, the reading order comes from `SUMMARY.md`; files not listed there are left out. A `SUMMARY.md` without any `book.toml` (GitBook and similar tools) only sets the reading order (MB125): there is no MB130, and Rust code blocks stay as written.

### Headings

Check recognizes three heading forms, and uses them for the chapter-title checks, `drop_sections`, and the inferred title:

- ATX headings: `#` to `######`. A closing `#` sequence needs a space before it, so `# Learning C#` keeps its `#`.
- Setext headings: a line underlined with `===` (level 1) or `---` (level 2). The text line must be the first line of the file or follow a blank line or a heading, and must not be a list item, a quote, or a table row.
- HTML headings: `<h1>` to `<h6>` alone on one line.

### Line numbers

Line numbers are 1-based. Findings from the analysis (MB200 to MB204, MB711, MB701, and the image problems of stage 5) carry the first line of the source file that contains the anchor, file name, image path, or formula, so the line can point to an earlier mention of the same target. MB205, MB501, and findings about the whole book have no line.

## The report

### Markdown report

The Markdown report has these parts:

- A title line with the target, plus the branch for GitHub targets: `# mdbindery check: https://github.com/getify/You-Dont-Know-JS/tree/2nd-ed/get-started (branch 2nd-ed)`.
- A result line: `ready to build` when there are no errors, `needs fixes before a correct EPUB can be built` otherwise, followed by the counts.
- `## Book`: title and language, configuration file (`none (inferred)` without one), number of files, counts of references, footnotes, and charts (plus `includes expanded: N` when there were includes), the image count, and with `--build` the trial build result. This part is missing when the configuration could not be loaded.
- `## Summary`: a table of counts per code and severity, errors first, when there are more than 10 findings.
- `## Errors`, `## Warnings`, `## Notes`: the findings, each with its code, `file:line`, message, and a `Fix:` line when there is a fix.
- `## Reading order`: the files in the order they go into the book.
- `## Suggested mdbindery.yaml`: only when the book has no configuration file; the text `mdbindery init` would write, with the assumed `source_url` for a GitHub target.

The `Images:` line reads `Images: 0` when there are none, and otherwise names the kinds found: `block` (the only thing on its line, without a title; a `<p>`, `<div>`, `<center>`, or `<picture>` wrapper around an `<img>` is allowed), `figure` (the same with a title), `full-page` (a title that starts with `full-page` or `fullpage`, in any case), and `inline` (everything else, such as two images on one line). An `<img>` on the same line as an HTML `<figure>` counts as `figure`, as in the build. The kinds are estimated line by line, so a `<figure>` spread over several lines can be counted differently from the build.

Example, for a two-chapter book:

```markdown
# mdbindery check: .

**Result:** needs fixes before a correct EPUB can be built. 1 error(s), 2 warning(s), 3 note(s).

## Book

- Title: Demo Book (en-US)
- Config: .../demo-book/mdbindery.yaml
- Files in reading order: 2
- References: 0; footnotes: 0; charts: 0
- Images: 1 (block 1)

## Errors

- **MB200** `01-start.md:3` link to missing anchor: 02-storm.md#the-storm-case (link text: the storm case)
  - Fix: Point the link at an existing heading (GitHub-style slug) or add <a id="..."></a> there.

## Warnings

- **MB121** no author
  - Fix: Set metadata.authors: [First Last].
- **MB402** `01-start.md:5` image without alt text: images/diagram.png
  - Fix: Describe the image: ![what it shows](path), or alt="..." on <img>. Screen readers need it; use alt="" on <img> only for purely decorative images.

## Notes

- **MB125** reading order inferred from file names
  - Fix: Check the "Reading order" list below; set files: in mdbindery.yaml to change it.
- **MB124** no identifier: a permanent urn:uuid will be generated on the first build
  - Fix: Keep "identifier:" in mdbindery.yaml so the build can save it.
- **MB410** no cover image: a plain typographic cover will be generated
  - Fix: Add cover.jpg (1600x2560 px) to the book folder or images/.

## Reading order

1. 01-start.md
2. 02-storm.md
```

A larger report starts with the summary table. The beginning of the report for a real repository:

```markdown
# mdbindery check: https://github.com/getify/You-Dont-Know-JS/tree/2nd-ed/get-started (branch 2nd-ed)

**Result:** ready to build. 0 error(s), 10 warning(s), 8 note(s).

## Book

- Title: You Don't Know JS Yet: Get Started - 2nd Edition (en-US)
- Config: none (inferred)
- Files in reading order: 8
- References: 0; footnotes: 1; charts: 0
- Images: 7 (block 7)

## Summary

| Code | Severity | Count |
|---|---|---|
| MB107 | warning | 7 |
| MB121 | warning | 1 |
| MB402 | warning | 1 |
| MB411 | warning | 1 |
| MB101 | info | 1 |
| MB107 | info | 1 |
| MB120 | info | 1 |
| MB122 | info | 1 |
| MB124 | info | 1 |
| MB125 | info | 1 |
| MB202 | info | 2 |
```

#### Grouping

Within each section, findings are grouped by code and file, in the order each group first appears. A group of up to three findings is printed one finding per line. More than three findings of one code in one file become one entry, so a long report stays readable:

- When all messages are the same, the entry gives the message once, the count, and the lines:

  ```markdown
  - **MB720** `07-many.md` code block has lines over 90 characters; they wrap on small screens: 4 times (lines 13, 17, 21, 25)
    - Fix: Shorten long lines if the layout matters.
  ```

- When the messages differ, the entry gives the count and the lines, then up to 10 distinct messages (and `... and N more (see the JSON report)` beyond that):

  ```markdown
  - **MB400** `03-maps.md` 4 findings (lines 3, 5, 7, 9):
    - image file not found: images/crater.png
    - image file not found: images/ridge.png
    - image file not found: images/valley.png
    - image file not found: images/plain.png
    - Fix: Fix the path; image paths are relative to the Markdown file ("/" means the repository root).
  ```

At most 15 line numbers are listed, followed by `...`. The `Fix:` line appears once when every finding in the group has the same fix, and is left out otherwise. Findings about the whole book are grouped the same way, without a file name.

A finding identical to an earlier one (same severity, code, file, line, and message) is recorded only once, in both reports. The JSON report is never grouped.

### Severities

| Severity | Report section | Meaning |
|---|---|---|
| `error` | Errors | The build stops, a build gate fails, or the EPUB loses or misplaces content. Any error makes the exit code 1. |
| `warning` | Warnings | The EPUB can be built, but something is probably wrong or reads badly: missing alt text, a skipped heading level, a table too wide for phones. |
| `info` | Notes | Values that were inferred, things mdbindery does on its own, and minor layout hints. |

An error does not always mean that `mdbindery build` fails. These errors leave the build passing while the EPUB is wrong: MB301 (the citation is not linked), MB304 (the footnote marker stays as text), and MB500 errors (the element is removed). With `options.strict_links: false`, MB200 and MB204 only make the links gate warn. The trial build (`--build`) shows what the real build will do.

### JSON report

`--json FILE` writes the same findings in machine-readable form:

| Field | Type | Meaning |
|---|---|---|
| `target` | string | The target as given on the command line. |
| `ok` | boolean | `true` when there are no errors (exit code 0). |
| `counts` | object | Number of findings per severity: `error`, `warning`, `info`. |
| `by_code` | array | One object per code and severity: `code`, `severity`, `count`. Sorted like the summary table (errors first, then by code), and present even for short reports. |
| `facts` | object | What mdbindery learned about the book (below). |
| `findings` | array | One object per finding, in the order the checks ran. |

`facts`:

| Field | Type | Meaning |
|---|---|---|
| `github` | object | GitHub targets only (HTTPS and SSH): `owner`, `repo`, `branch`, `subdir`. |
| `source` | string | Absolute path of the book source folder. For a repository URL this is inside the temporary clone, which is gone after the run. |
| `config` | string or null | The configuration file used, or `null` when the configuration was inferred. |
| `inferred` | array of strings | What was inferred: `config (no mdbindery.yaml found)`, `source_dir (book.toml)`, `files (reading order)`, `metadata.title (book.toml)`, `metadata.title`, `metadata.rights`, `metadata.lang`, `cover.image`. |
| `title` | string | Book title, given or inferred. |
| `lang` | string | Book language. |
| `files` | array of strings | The reading order. |
| `totals` | object | `refs` (citation definitions), `footnotes` (footnote definitions), `images` (`inline`, `block`, `figure`, `full-page`), `charts` (Mermaid blocks), `math` (math blocks plus lines with inline math), `includes` (expanded mdBook directives). |
| `trial_build` | string | With `--build` only: one of the texts under [Trial build](#trial-build). |
| `suggested_config` | string | Only when there is no configuration file: a starter `mdbindery.yaml`. |

When the configuration could not be loaded (MB102 error), `facts` is empty, except for `github`. When the reading order is empty (MB100), `facts` has no `totals` and no `suggested_config`.

Each finding:

| Field | Type | Meaning |
|---|---|---|
| `severity` | string | `error`, `warning`, or `info`. |
| `code` | string | Check code, such as `MB200`. |
| `file` | string | The file as written in the reading order, relative to the book source folder. The configuration file's name for MB102 warnings, a path inside the EPUB for MB900, and `""` for findings about the whole book. |
| `line` | integer or null | 1-based line number, or `null`. |
| `message` | string | What was found. |
| `fix` | string | Suggested fix; can be `""`. |

The JSON report for the example above (paths shortened, short objects written on one line):

```json
{
  "target": ".",
  "ok": false,
  "counts": {"error": 1, "warning": 2, "info": 3},
  "by_code": [
    {"code": "MB200", "severity": "error", "count": 1},
    {"code": "MB121", "severity": "warning", "count": 1},
    {"code": "MB402", "severity": "warning", "count": 1},
    {"code": "MB124", "severity": "info", "count": 1},
    {"code": "MB125", "severity": "info", "count": 1},
    {"code": "MB410", "severity": "info", "count": 1}
  ],
  "facts": {
    "source": ".../demo-book",
    "config": ".../demo-book/mdbindery.yaml",
    "inferred": ["files (reading order)"],
    "title": "Demo Book",
    "lang": "en-US",
    "files": ["01-start.md", "02-storm.md"],
    "totals": {
      "refs": 0,
      "footnotes": 0,
      "images": {"inline": 0, "block": 1, "figure": 0, "full-page": 0},
      "charts": 0,
      "math": 0,
      "includes": 0
    }
  },
  "findings": [
    {
      "severity": "info",
      "code": "MB125",
      "file": "",
      "line": null,
      "message": "reading order inferred from file names",
      "fix": "Check the \"Reading order\" list below; set files: in mdbindery.yaml to change it."
    },
    {
      "severity": "warning",
      "code": "MB121",
      "file": "",
      "line": null,
      "message": "no author",
      "fix": "Set metadata.authors: [First Last]."
    },
    {
      "severity": "info",
      "code": "MB124",
      "file": "",
      "line": null,
      "message": "no identifier: a permanent urn:uuid will be generated on the first build",
      "fix": "Keep \"identifier:\" in mdbindery.yaml so the build can save it."
    },
    {
      "severity": "info",
      "code": "MB410",
      "file": "",
      "line": null,
      "message": "no cover image: a plain typographic cover will be generated",
      "fix": "Add cover.jpg (1600x2560 px) to the book folder or images/."
    },
    {
      "severity": "warning",
      "code": "MB402",
      "file": "01-start.md",
      "line": 5,
      "message": "image without alt text: images/diagram.png",
      "fix": "Describe the image: ![what it shows](path), or alt=\"...\" on <img>. Screen readers need it; use alt=\"\" on <img> only for purely decorative images."
    },
    {
      "severity": "error",
      "code": "MB200",
      "file": "01-start.md",
      "line": 3,
      "message": "link to missing anchor: 02-storm.md#the-storm-case (link text: the storm case)",
      "fix": "Point the link at an existing heading (GitHub-style slug) or add <a id=\"...\"></a> there."
    }
  ]
}
```

To list only the errors: `jq -r '.findings[] | select(.severity == "error") | "\(.code) \(.file):\(.line) \(.message)"' report.json`.

## Check codes

### Summary

| Code | Severity | Reported when |
|---|---|---|
| [MB001](#mb001-pandoc-not-installed) | warning | pandoc is not installed |
| [MB100](#mb100-no-markdown-files) | error | the reading order is empty |
| [MB101](#mb101-no-configuration-file) | info | there is no `mdbindery.yaml` |
| [MB102](#mb102-configuration-problem) | error, warning | the configuration cannot be used, or has unknown keys |
| [MB103](#mb103-listed-file-not-found) | error | a file in `files` does not exist |
| [MB104](#mb104-file-not-in-the-reading-order) | info | a Markdown file is not in the reading order |
| [MB105](#mb105-encoding-and-line-endings) | error, info | a file is not UTF-8, or has a BOM or CRLF line endings |
| [MB106](#mb106-no-level-1-heading) | warning | a file has no level-1 heading |
| [MB107](#mb107-several-level-1-headings) | warning, info | a file has more than one level-1 heading |
| [MB108](#mb108-skipped-heading-level) | warning | a heading skips a level |
| [MB109](#mb109-empty-file) | warning | a file is empty |
| [MB110](#mb110-content-above-the-chapter-title) | warning | something comes before the level-1 heading |
| [MB111](#mb111-yaml-front-matter) | warning | a file starts with YAML front matter |
| [MB120](#mb120-title-inferred) | info | the title was inferred |
| [MB121](#mb121-no-author) | warning | there is no author |
| [MB122](#mb122-language-inferred) | info | the language was inferred |
| [MB123](#mb123-no-rights-statement) | warning | there is no rights statement or license |
| [MB124](#mb124-no-identifier) | info | `metadata.identifier` is empty |
| [MB125](#mb125-reading-order-inferred) | info | the reading order was inferred |
| [MB126](#mb126-table-of-contents-file-in-the-reading-order) | warning | a table of contents file is in `files` |
| [MB130](#mb130-mdbook-layout) | info | the book is an mdBook |
| [MB131](#mb131-directive-not-expanded) | error | an mdBook directive cannot be expanded |
| [MB200](#mb200-link-to-a-missing-anchor) | error | a link points to an anchor that does not exist |
| [MB201](#mb201-anchor-matched-approximately) | warning | a link's anchor matches only when punctuation is ignored |
| [MB202](#mb202-link-to-a-file-outside-the-book) | warning, info | a link points to an existing file that is not in the book |
| [MB203](#mb203-web-link-not-checked) | warning | a link points to a website page that is not in the repository |
| [MB204](#mb204-link-to-a-missing-file) | error | a link points to a file that does not exist |
| [MB205](#mb205-html-link-resolved-to-a-markdown-file) | info | a `.html` or folder link was resolved to a `.md` file |
| [MB300](#mb300-reference-never-used) | warning | a reference definition is never used |
| [MB301](#mb301-reference-defined-twice) | error | a reference label has two different URLs |
| [MB302](#mb302-citation-without-a-definition) | warning | `[n]` in the text has no definition in the file |
| [MB303](#mb303-no-references-heading) | info | a file has citations but no references heading |
| [MB304](#mb304-footnote-without-a-definition) | error | a footnote reference has no definition |
| [MB305](#mb305-footnote-never-used) | warning | a footnote definition is never referenced |
| [MB306](#mb306-reference-without-a-title) | info | a citation definition has no title |
| [MB400](#mb400-image-not-found) | error | an image has no path or its file does not exist |
| [MB401](#mb401-image-url) | error, info | an image is loaded from a URL |
| [MB402](#mb402-image-without-alt-text) | warning | an image has no alt text |
| [MB403](#mb403-image-format) | error, warning | an image format is unsupported or unusual |
| [MB404](#mb404-image-too-large) | warning | an image is over 3200 px or 5 MB |
| [MB405](#mb405-animated-image-or-scripted-svg) | info, warning | an image is animated, or an SVG has scripts |
| [MB406](#mb406-image-outside-the-book-folder) | warning, error | an image lies outside the book folder or the repository |
| [MB410](#mb410-no-cover-image) | info | there is no cover image |
| [MB411](#mb411-cover-size-ratio-or-color-mode) | warning | the cover is small, has an unusual ratio, or is CMYK |
| [MB412](#mb412-cover-missing-unreadable-or-converted) | error, warning | the cover is missing, unreadable, or not JPEG or PNG |
| [MB500](#mb500-unsupported-html-tag) | error, warning | a file uses an HTML tag the EPUB cannot keep |
| [MB501](#mb501-html-dropped-in-conversion) | info | the conversion removed HTML from a file |
| [MB600](#mb600-wide-table) | warning | a table has too many columns for a phone |
| [MB700](#mb700-mermaid-cli-not-installed) | warning | the book has charts and mermaid-cli is missing |
| [MB701](#mb701-chart-failed-to-render) | error | a Mermaid chart does not render |
| [MB710](#mb710-math) | info | the book contains math |
| [MB711](#mb711-dollar-signs-read-as-math) | warning | text between dollar signs is read as a formula |
| [MB720](#mb720-long-code-lines) | info | a code block has lines over 90 characters |
| [MB900](#mb900-epubcheck-message) | error, warning | EPUBCheck reports a message (trial build) |
| [MB901](#mb901-ace-violation) | error, warning, info | Ace reports a violation (trial build) |
| [MB902](#mb902-word-count-mismatch) | error | the word-count gate fails (trial build) |
| [MB903](#mb903-analysis-or-trial-build-failed) | error | the pandoc analysis or the trial build stopped with an error |
| [MB904](#mb904-trial-build-gate-failed) | error | a trial-build gate failed |

Numbers that are not in this table are not used.

Codes that appear with more than one severity, depending on the case:

| Code | Higher severity when | Lower severity when |
|---|---|---|
| MB102 | error: the configuration cannot be used | warning: an unknown nested key or file key |
| MB105 | error: invalid UTF-8 | info: byte order mark, or CRLF line endings |
| MB107 | warning: one file has several level-1 headings | info: several files start with the same heading |
| MB202 | warning: no `source_url`, the link becomes plain text | info: a GitHub target without `source_url`, the link will point online |
| MB401 | error: a remote image, or an unsupported URL scheme | info: a URL of a file in this repository |
| MB403 | error: a known unsupported format | warning: an unknown extension |
| MB405 | warning: an SVG with scripts or `foreignObject` | info: an animated image |
| MB406 | error: outside the repository, for a repository checked by URL | warning: outside the book folder |
| MB412 | error: missing or unreadable | warning: readable, but not JPEG or PNG |
| MB500 | error: `script`, `iframe`, `object`, `embed`, `form`, `input`, `button`, `style`, `video`, `audio`, `canvas`, `select`, `textarea` | warning: any other unknown tag |
| MB900 | error: EPUBCheck `ERROR` or `FATAL` | warning: any other EPUBCheck severity |
| MB901 | error: Ace impact `critical` or `serious` | warning: `moderate` or `minor`, or Ace not installed; info: a rule listed in `options.ace_waivers` |

### Tools

#### MB001: pandoc not installed

Warning. pandoc was not found in mdbindery's tool folder, and the `PATH` has no pandoc 3.8 or newer (an older one is ignored). Message: `pandoc not installed (or older than 3.8): internal links were not verified`.

Without pandoc, check skips the whole analysis stage: links, HTML conversion, charts, and dollar-sign math are not checked, so a clean report can hide broken links. The build cannot run at all, so `--build` then ends with MB903.

Fix: run `mdbindery install-tools`, then `mdbindery doctor` to confirm.

### Files and configuration

#### MB100: no Markdown files

Error. Message: `no Markdown files found`. The reading order is empty: `files` is not set and no `.md` files were found in the book folder (or in `chapters/` when it exists), apart from skipped repository files such as `CHANGELOG.md`, `CONTRIBUTING.md`, `LICENSE.md`, and table of contents files (`SUMMARY.md`, `toc.md`, `contents.md`). The check stops here.

There is nothing to build. `mdbindery build` stops with `no Markdown files in the reading order (MB100)`.

Fix: put the chapters in the book folder or in `chapters/`, or list them under `files:`. If they exist, check that `TARGET` or `source_dir` points at the book folder and not at its parent.

#### MB101: no configuration file

Info. Message: `no mdbindery.yaml: using an inferred configuration`. There is no `mdbindery.yaml` or `mdbindery.yml` in the book folder and no `-c`, so the whole configuration is inferred ([configuration.md](configuration.md#what-is-inferred-when-keys-are-missing)).

The inferred reading order and metadata may be wrong, and without a file the generated identifier cannot be saved, so every build gets a new one. The report ends with a suggested configuration.

Fix: run `mdbindery init`, then review the title, authors, and file order.

#### MB102: configuration problem

Error or warning.

Error: the configuration cannot be used. The check stops here, `facts` stays empty, and `mdbindery build` stops with `config error: ...` and exit code 2. Fix text: `Fix mdbindery.yaml (see docs/configuration.md).` The messages:

| Problem | Message |
|---|---|
| The file given with `-c` does not exist | `config file not found: PATH` |
| Invalid YAML | `invalid YAML in mdbindery.yaml, line 3, column 5: PROBLEM` |
| Not UTF-8 | `mdbindery.yaml is not UTF-8 text` |
| The top level is not a mapping | `mdbindery.yaml must contain a mapping of keys to values` |
| Unknown top-level key | `unknown top-level key "metdata" (did you mean "metadata"?): its settings would be ignored` |
| `metadata`, `cover`, or `options` is not a mapping | `metadata must be a mapping of keys to values` |
| A value of the wrong type | `NAME must be text`, `NAME must be text, not true (put it in quotes)`, `NAME must be a number, not 'two'`, `NAME must be a whole number`, `NAME must be between 1 and 6`, `NAME must be true or false`, `NAME must be a list` |
| `lang: no` (YAML reads it as false) | `metadata.lang must be a language code in quotes, e.g. lang: 'no' (YAML reads no as false)` |
| A bad date | `metadata.date must be 'git' or a date like 2026-09-26` |
| A bad slug | `slug may use letters, digits, dots, hyphens, and underscores only (it names the EPUB file)` |
| A bad `source_url` | `source_url must start with https://` |
| A bad cover color | `cover.background must be a color like #1d2330` (also `foreground`, `accent`) |
| Bad `options.cards` | `options.cards must be a mapping (files, min_columns, title_columns)`, `options.cards.files must be a list of file names` |
| A `drop_lines` pattern that does not compile | `options.drop_lines: invalid pattern '(': ERROR` |
| A value outside its choices | `options.citations must be 'refdefs' or 'none'`, `options.citation_labels must be 'numeric' or 'all'`, `options.mermaid must be 'png', 'placeholder', or 'keep'`, `options.mermaid_theme must be one of: default, neutral, dark, forest, base`, `options.highlight_style must be a pandoc style name (e.g. monochrome, tango) or none` |
| A folder or file that does not exist | `source folder not found: PATH`, `options.css: file not found: X` (also `extra_css`), `options.embed_fonts: file not found: X` |
| A bad `files` list | `files must be a list`, `files entry 2 has no "file:" key`, `files entry ../x.md: use a path relative to the book folder (no absolute paths, no ..; set source_dir instead)`, `files entry X: key must use letters, digits, and underscores`, `duplicate file keys: [...]`, `file listed twice in files: [...]` |
| A path outside a repository checked by URL | `source_dir must stay inside the repository`, `options.css must be a file inside the repository` (also `extra_css`), `options.embed_fonts must list files inside the repository`, `cover.image must be a file inside the repository` |

Warning: a nested key or a key of a `files` entry is unknown, for example `unknown config key: options.toc_dept (did you mean "toc_depth"?)` or `unknown keys for file 01-intro.md: ['titel'] (did you mean "title"?)`. The finding's file is the configuration file's name. The key is ignored, so the setting you meant keeps its default.

Fix: correct the file against [configuration.md](configuration.md).

#### MB103: listed file not found

Error. A file under `files:` does not exist in the book source folder. Message: `file in the reading order not found: 04-gone.md`.

`mdbindery build` stops with `listed file not found: 04-gone.md`.

Fix: correct the name or remove the entry. Names are case-sensitive on Linux and in a cloned repository, even when they are not on your own system.

#### MB104: file not in the reading order

Info. Message: `Markdown file not in the reading order: intro.md`. Reported when there is a configuration file or a `chapters/` folder, for each `.md` file in the book folder or in `chapters/` that is not in the reading order. `README.md`, repository files such as `CONTRIBUTING.md`, and table of contents files are not reported.

The file is not part of the EPUB, and links to it from the book count as links to a file outside the book (MB202).

Fix: add it under `files:` if it belongs in the book.

#### MB105: encoding and line endings

Error or info.

Error: `not valid UTF-8 (byte 17); the build stops on it`. `mdbindery build` stops with `03-latin.md is not valid UTF-8 (byte 17); re-save it as UTF-8`. The check reads the rest of the file with the bad bytes replaced.

Info: `starts with a byte order mark (removed during the build)`, or `Windows line endings (CRLF); handled, but LF is recommended`. Nothing is lost.

Fix: re-save the file as UTF-8 in your editor, or convert it, for example `iconv -f windows-1252 -t utf-8 03-latin.md > 03-latin.utf8.md`.

#### MB106: no level-1 heading

Warning. The file has no level-1 heading, and its `files` entry has no `title:`. The build gives every file a chapter title, and the message says which one it will use:

| Case | Message |
|---|---|
| No headings at all | `no headings: the chapter title will be "Nohead" (from the file name, or the book title for README.md)` |
| Text comes before the first heading | `no level-1 heading and text above the first heading: the build makes the chapter title "Textfirst" from the file name (the book title for README.md)` |
| The first visible block is a heading | `no level-1 heading: the build promotes "Chapter six" to the chapter title and moves the file's other headings up by the same number of levels` |

A title from the file name drops the number prefix and turns hyphens and underscores into spaces (`04-nohead.md` becomes `Nohead`). When a heading is promoted, anchors and comments above it do not count as text, and the file's other headings move up with it but never above level 2.

The EPUB is complete either way, but the chapter title may not be the one you want.

Fix: start the file with one `#` heading, or set `title:` for the file under `files:`.

```markdown
## Introduction
```

becomes

```markdown
# 1. Introduction
```

#### MB107: several level-1 headings

Warning or info.

Warning: the file has more than one level-1 heading. Message: `2 level-1 headings: each starts a new EPUB section and TOC entry`. The line points to the second one. One source file becomes several chapters in the EPUB and in the table of contents.

Info, once for the book: two or more files with several level-1 headings share the same first one, usually the book title repeated at the top of every chapter. The fix line holds a ready `drop_lines` pattern:

```markdown
- **MB107** 7 files start with the same heading "You Don't Know JS Yet: Get Started - 2nd Edition" before their chapter title
  - Fix: To drop it without editing the files, add to options: drop_lines: ['^#\s+You Don''t Know JS Yet: Get Started - 2nd Edition\s*$']
```

Fix: keep one `#` heading per file. If the first one repeats the book title, delete it or drop it with the suggested `drop_lines`; otherwise demote the others to `##`, or split the file.

#### MB108: skipped heading level

Warning. A heading is more than one level deeper than the heading before it, for example `####` right after `##`. Message: `heading level jumps from 2 to 4: "Skipped level"`.

Screen readers and the table of contents use the heading levels as the book's outline. A skipped level looks like a missing section.

Fix: use the next level down (`###` after `##`).

#### MB109: empty file

Warning. Message: `file is empty`. The file contains only blank lines, also when everything in it is removed by `drop_lines` or `drop_sections`.

A chapter that should be there is missing.

Fix: remove the file from the reading order or write its content.

#### MB110: content above the chapter title

Warning. Message: `content above the chapter title: the build moves it below the title`. The file has a level-1 heading, and either another heading comes first or text lines come before it. Blank lines, comments, and lines that hold only an anchor (`<a id="..."></a>` or `<a name="..."></a>`) do not count. The line points to the first such line. Typical cases are badges and logos at the top of a README.

The build moves everything above the title to just below it, so nothing is lost, but the chapter no longer starts the way it does on GitHub.

Fix: start the file with its `# Title` heading, or remove the lines with `drop_lines`.

#### MB111: YAML front matter

Warning. Message: `YAML front matter at the top of the file is ignored (and hidden from the book)`, on line 1. The file's first line is `---`, and a `---` or `...` line follows within the next 39 lines.

mdbindery takes no metadata from the file itself, and the other checks ignore these lines.

Fix: move the values into `mdbindery.yaml` (the book's `metadata`, or `title:` in the file's `files` entry).

#### MB125: reading order inferred

Info. `files:` is not set, so the reading order was inferred. mdbindery takes the first of these that applies:

1. A table of contents file (`SUMMARY.md`, `toc.md`, `TOC.md`, `contents.md`, `CONTENTS.md`, `table-of-contents.md`) that links to at least two Markdown files (one is enough for `SUMMARY.md`): its links, in order. With `SUMMARY.md`, `README.md` is in the book only when `SUMMARY.md` lists it. Message: `reading order inferred from SUMMARY.md` (or the other file's name).
2. The README's links to chapter files, when they cover at least half of them. This step is skipped when the chapter files are all numbered (their names start with a digit; front matter, back matter, and appendix names do not count), because numbered names already give the order. Message: `reading order inferred from links in README.md`.
3. The file names: numbered files in numeric order, and unnumbered names sorted with front matter (preface, introduction, ...) first, then chapters, then appendices (`appendix...`, or `ap` or `app` and one letter from a to h, such as `apA` or `app-b`), then back matter. Message: `reading order inferred from file names`.

So a book with `01-one.md`, `02-two.md`, and `03-three.md` gets the numeric order, even when its README links the chapters in another order. The suffix ` (then file names)` means that files the list did not link were added after it, sorted by name; for `SUMMARY.md` they are left out instead.

Fix: check the `Reading order` list at the end of the report, and set `files:` to change it. The details are in [configuration.md](configuration.md#what-is-inferred-when-keys-are-missing).

#### MB126: table of contents file in the reading order

Warning. `files:` lists `SUMMARY.md`, `toc.md`, `TOC.md`, `contents.md`, `CONTENTS.md`, or `table-of-contents.md` from the book folder. Message: `toc.md is in the reading order: a hand-written table of contents repeats the EPUB navigation`.

The EPUB has its own table of contents, and the hand-written one links to chapter files by their Markdown names.

Fix: remove it from `files:`.

#### MB130: mdBook layout

Info. The book is an mdBook (see [Includes and mdBook](#includes-and-mdbook)). Message: `mdBook layout: reading order from SUMMARY.md, title from book.toml, {{#include}} directives expanded, hidden "# " lines in Rust code removed`.

mdbindery reads the book the way mdBook would. Preprocessors other than the built-in directives are not run.

#### MB131: directive not expanded

Error. An mdBook directive could not be expanded. Message: `mdBook directive not expanded (REASON): DIRECTIVE`, where `REASON` is `file not found`, `outside the repository`, `anchor not found: NAME`, or `cannot read: ...`. Example: `mdBook directive not expanded (file not found): {{#include snippets/missing.rs}}`.

The build leaves the directive in the text as it is, and its includes gate fails.

Fix: correct the path (relative to the Markdown file, inside the repository) or the anchor name, or replace the directive with the text it should include. Write `\{{#include ...}}` to show the directive itself.

### Metadata

#### MB120: title inferred

Info. `metadata.title` is not set. Message: `title inferred: "..."`. The title comes from the first level-1 heading of `README.md` (or of the first file when `README.md` is not in the reading order), else the repository name for a repository checked by URL, else the folder name. A title from `book.toml` is not reported.

The title appears on the title page, the generated cover, and the store listing, and in the output file name (`slug`).

Fix: set `metadata.title`.

#### MB121: no author

Warning. Message: `no author`. `metadata.authors` is empty and `book.toml` names no authors.

The EPUB has no `dc:creator`, stores ask for one, and the generated cover has no author line.

Fix: `authors: [Jane Doe]`.

#### MB122: language inferred

Info. The configuration has no `metadata.lang`. Message: `language inferred: en-US`. The language comes from `book.toml`, or is guessed from the first three files: `ru` when more than 30% of the letters are Cyrillic, `en-US` otherwise. No other language is guessed.

The language drives hyphenation, the reader's dictionary, and text-to-speech. A wrong guess affects all three.

Fix: set `metadata.lang` (`en-US`, `ru`, `de`, ...).

#### MB123: no rights statement

Warning. Message: `no license or rights statement`. `metadata.rights` is empty, and no license was recognized in `LICENSE`, `LICENSE.md`, `LICENSE.txt`, `LICENCE`, `LICENCE.md`, `COPYING`, or `COPYING.md` in the book folder or the repository root.

The EPUB has no `dc:rights`, so readers and stores cannot tell under which terms the book is published.

Fix: add a license file, or set `metadata.rights` (`CC BY 4.0`, `© 2026 Jane Doe. All rights reserved.`).

#### MB124: no identifier

Info. `metadata.identifier` is empty. Message: `no identifier: a permanent urn:uuid will be generated on the first build`.

The first build generates the identifier and saves it only if the configuration file has an empty `identifier:` line. If it cannot be saved, every build gets a new identifier, and stores treat each upload as a different book ([configuration.md](configuration.md#the-identifier)). Check itself never writes the file.

Fix: keep `identifier:` under `metadata:` with no value, and commit the file after the first build.

### Links

The rules for links and anchors are in [book-structure.md](book-structure.md#4-links). A link that starts with `/` is resolved from the repository root: the git checkout that holds the book, the clone for a URL target, or, when it is not in git, the book folder (for an mdBook, the folder with `book.toml`). So in a book stored in `book/`, a link to `/book/02.md` is a link to that chapter. Links that climb out of the book folder with `../` are resolved too.

#### MB200: link to a missing anchor

Error. A link points to `#anchor` in the same file or `file.md#anchor` in another file of the book, and no heading or `<a id>` there produces that anchor. Message: `link to missing anchor: 02-storm.md#the-storm-case (link text: the storm case)`.

mdbindery tries an exact match first, then a case-insensitive one (fixed silently, as GitHub does), then one that ignores ASCII punctuation and spaces (MB201). In the EPUB an unresolved link goes to the top of the target chapter, and the build's links gate fails. With `options.strict_links: false` the gate only warns, but check still reports an error.

Fix: use the anchor GitHub generates for the heading, or put an `<a id>` where the link should land:

```markdown
<!-- 02-storm.md -->
<a id="the-storm-case"></a>
## Dust storms
```

#### MB201: anchor matched approximately

Warning. The link's anchor differs from an existing anchor only in ASCII punctuation and spaces, and exactly one anchor in the target file matches. Message: `link #q-a-power-budget matched only approximately (anchor is #qa-power-budget)`.

mdbindery uses the matching anchor, so the link works in the EPUB. On GitHub, which needs the exact anchor, it lands at the top of the file.

Fix: write the anchor shown in the message.

```markdown
## Q&A: power budget

See [the questions](#q-a-power-budget).   <!-- MB201 -->
See [the questions](#qa-power-budget).    <!-- exact -->
```

#### MB202: link to a file outside the book

Warning or info. A relative link points to a file or folder that exists but is not in the reading order: `LICENSE`, source code, a chapter left out of `files`.

Warning: `source_url` is not set. Message: `link to LICENSE, which is not part of the book: it becomes plain text in the EPUB`. The build keeps the link text and removes the link, and lists these links in its log.

Info: the target is a GitHub URL and the configuration has no `source_url`, so check assumed one (see [Targets](#repositories-checked-by-url)). Message: `link to ../preface.md (not in the book) will point to the online repository`, with `Set source_url: https://github.com/getify/You-Dont-Know-JS/blob/2nd-ed/get-started/` as the fix.

Fix: set `source_url` so that such links point to the online copy, or add the file to `files:` if it belongs in the book. When the book folder is a git checkout with a GitHub remote, the fix line of the warning names the value to use.

```yaml
source_url: https://github.com/you/book/blob/main/
```

#### MB203: web link not checked

Warning. `source_url` is a website (not github.com), and a relative link points to a file that is not in the repository. The message gives the web address the link will have, resolved against `source_url`, with a `.md` target changed to its `.html` page: `link to ../guide/gone.md, which is not in the repository: it points to https://docs.example.org/guide/gone.html (not checked)`.

This is normal for a book whose `source_url` is its published website, where `.html` pages exist only online. The build keeps the web link, writes a log line, and does not fail. Nothing checks that the page exists.

Fix: make sure the page exists on the website.

#### MB204: link to a missing file

Error. A relative link points to a file that does not exist, and `source_url` is not set or is a GitHub URL. Message: `link to a missing file: ghost.md`. For a `.html` or `.htm` target, the fix line adds: `If it is a page of the published website, set source_url to the web address of the book folder, or use a full https:// link.`

The build's links gate fails (with `options.strict_links: false` it only warns).

Fix: correct the path (relative to the Markdown file, spaces written as `%20`) or remove the link.

#### MB205: .html link resolved to a Markdown file

Info. Message: `2 link(s) to .html pages or folders resolved to the matching .md files`, once per file. mdBook and web-style books link to pages as the website serves them, and mdbindery maps those links to the chapters of the book: `chapter.html` to `chapter.md`, and `dir/index.html` or `dir/` to `dir/README.md` (or `readme.md`, or `index.md`) when that file is in the book. Other `.html` links are MB204 or MB203.

Nothing to fix.

### Citations and footnotes

The citation rules are in [book-structure.md](book-structure.md#5-citations-and-references). With `options.citations: none`, MB300 to MB303 and MB306 are not checked. Definitions and footnotes are per file: a definition in another chapter does not count.

A citation label is a numeric label such as `[4]`, or any label with `options.citation_labels: all`. Other reference definitions, such as `[GitHub]: https://github.com`, are ordinary Markdown links. A definition used by an image (`![alt][2]`) is never a citation. With `citation_labels: all`, a named label whose URL is an image file is not a citation either; a numeric label that points to an image file stays one. Definitions inside block quotes (`> [4]: ...`) count like any other.

#### MB300: reference never used

Warning. A reference definition, citation or not, is not used anywhere in the same file. Message: `reference [4] is defined but never used`. Uses are `[4]`, `[text][4]`, `[4][]`, and `![alt][4]`, in any letter case, outside code blocks. A label that contains inline code, such as ``[`build.dir`]``, counts as used.

An unused citation still appears in the chapter's reference list, with nothing in the text pointing to it.

Fix: use it, or delete the definition line.

#### MB301: reference defined twice

Error. The same label is defined twice in one file with different URLs; the line points to the second definition. Message: `reference [5] is defined twice with different URLs`. Two identical definitions are not reported.

Markdown resolves `[5]` to the first definition, while the reference list shows the last one. In the EPUB, `[5]` in the text is then not linked to the reference list, and the list names a source that the text, and GitHub, do not use. The build does not fail.

Fix: keep one definition per label, and renumber the second source.

```markdown
[5]: https://example.org/a "First"
[5]: https://example.org/b "Second"    <!-- MB301: make this [6] and cite it as [6] -->
```

#### MB302: citation without a definition

Warning. A number in square brackets appears in the text, but the file has no definition for it. Message: `"[3]" looks like a citation but has no definition in this file`. Only numbers from 1 to 9999 without a leading zero are checked, so `[0]` is never reported. Brackets directly after a letter, digit, `]`, `\`, or `!` (`array[3]`), and brackets followed by `(`, `[`, or `:` are not treated as citations.

In the EPUB `[3]` stays plain text, with no link and no list entry.

Fix: add the definition to this file, or escape the brackets when the text is not a citation.

```markdown
Solar power at Mars is 43% of Earth's [3].

[3]: https://nssdc.gsfc.nasa.gov/planetary/factsheet/marsfact.html "NASA NSSDC, Mars Fact Sheet"
```

```markdown
The \[3] here is not a citation.
```

#### MB303: no references heading

Info. The file has citation definitions but no heading from `options.reference_headings` (References, Sources, Notes, Bibliography, Works cited, and Russian equivalents). Message: `citations but no References heading: a "References" section will be added at the end of the file`.

The build adds `## References` (`options.reference_heading_new`) at the end of the file and puts the list there.

Fix: add one of those headings where the list should go, or accept the default position.

#### MB304: footnote without a definition

Error. A footnote reference `[^x]` has no `[^x]: ...` definition in the same file. Definitions inside block quotes (`> [^x]: ...`) count. Message: `footnote [^x] has no definition`.

pandoc prints `[^x]` as literal text in the EPUB. The build does not fail.

Fix: add the definition, or remove the reference.

```markdown
A claim.[^x]

[^x]: The source of the claim.
```

#### MB305: footnote never used

Warning. A footnote definition is not referenced anywhere in the file. Message: `footnote [^x] is defined but never used`.

pandoc drops unreferenced notes, so the note's text is missing from the EPUB.

Fix: reference it in the text, or delete it.

#### MB306: reference without a title

Info. A citation definition has a URL but no title (`[1]: https://example.org`). Message: `reference [1] has no title; the list will show only the URL`.

The list entry shows only the label and the URL.

Fix: add a title in quotes: `[1]: https://example.org "Author, Title, Publisher, year"`.

### Images

The image rules are in [book-structure.md](book-structure.md#6-images). Check reads Markdown images (`![alt](src "title")`), reference-style images (`![alt][label]` with a definition in the same file), and HTML `<img>` tags, also when a tag spans several lines. Paths are relative to the Markdown file, `/` means the repository root, `%20` and other escapes are decoded, and `?query` and `#fragment` are ignored. `file:` URLs are local paths: `file:images/x.png` and `file://images/x.png` are relative like `images/x.png`, and `file:///home/me/x.png` is that path on this computer (the build reads it the same way). MB403 to MB405 look at the file itself, so they appear only when the file exists.

#### MB400: image not found

Error. The image has an empty path (`image without a source path`), or its file does not exist (`image file not found: images/missing.png`).

The build replaces the image with the text `[image: ALT]`, and its images gate fails.

Fix: correct the path, for example `../images/x.png` from a file in `chapters/`.

#### MB401: image URL

Error or info.

Error: the image source is a URL. `remote image: https://...` for `http` and `https`; `unsupported image URL: ...` for other schemes such as `data:` or `ftp:` (not `file:`). An EPUB cannot load images from the web: the build replaces the image with the text `[image: ALT]`, and its images gate fails.

Info: the URL points to a file of this book's own GitHub repository, and the file exists in the checkout. Message: `image URL points to this repository; the build uses the local file images/pic.png`, with `Link the file directly: images/pic.png` as the fix. The URL forms are `https://github.com/OWNER/REPO/blob/BRANCH/PATH` (also `/raw/`, with or without `?raw=true`) and `https://raw.githubusercontent.com/OWNER/REPO/BRANCH/PATH`. The repository is known from `source_url`, the git remote, or the checked GitHub URL. When the file is not in the checkout, the URL is a remote image (error).

Fix: download the image into the repository and link it with a relative path.

```markdown
![Mars rover tracks](https://example.org/tracks.jpg)    <!-- MB401 -->
![Mars rover tracks](images/tracks.jpg)                 <!-- fixed -->
```

#### MB402: image without alt text

Warning. Message: `image without alt text: images/diagram.png`. Reported for a Markdown image with empty or blank alt text (`![](images/diagram.png)`), an `<img>` without an `alt` attribute, and an `<img>` whose `alt` holds only spaces. An `<img>` with `alt=""` is decorative and is not reported; Markdown has no decorative form.

Screen reader users get no description of the image. The EPUB declares that images carry text alternatives only when every image has alt text.

Fix: describe what the image shows. A caption (the image title) does not replace alt text.

```markdown
![Power demand over one Martian day, peaking at dusk](images/demand.png "Figure 3. Daily power demand")
```

#### MB403: image format

Error or warning.

Error: `image format .bmp is not supported in EPUB: images/photo.bmp`, for `.bmp`, `.tif`, `.tiff`, `.heic`, `.heif`, `.psd`, `.avif`, `.ico`, `.eps`, and `.pdf`. EPUBCheck rejects such a file (`RSC-032`, no fallback for a foreign resource) and the build fails.

Warning: `unusual image format .xyz: ...`, for any other extension that is not `.jpg`, `.jpeg`, `.png`, `.gif`, `.svg`, or `.webp`.

Fix: convert the image, JPEG for photos and PNG for diagrams and screenshots, for example `magick photo.bmp -quality 85 photo.jpg`, and update the link.

#### MB404: image too large

Warning. The image is larger than 3200 px on its long side (`image is WIDTHxHEIGHT px: larger than readers need (SRC)`), or its file is larger than 5 MB (`image file is SIZE MB (SRC)`). SVG files are not measured.

Readers never show that many pixels, and large files make the book heavy; stores limit the size of uploads.

Fix: scale to at most 3200 px on the long side and compress photos, for example `magick big.jpg -resize '3200x3200>' -quality 85 big.jpg`.

#### MB405: animated image or scripted SVG

Info or warning.

Info: `animated GIF: most readers show only the first frame (SRC)`. Animated PNG and WebP files get the same message.

Warning: `SVG uses scripts or foreignObject, which many readers drop (SRC)`. Parts of the drawing disappear in those readers.

Fix: for an animation, make sure the first frame carries the point, or use a still image. For an SVG, export it with plain text elements, or use a PNG.

#### MB406: image outside the book folder

Warning or error.

Warning: `image lies outside the book folder: ../shared.png`. The file exists, but outside the book source folder. The build of a local folder still finds it, but the book now depends on files outside its folder, and a check of the book's subfolder URL or a copy of the book folder alone will miss them.

Error: `image outside the repository: ../../outside.png`, only for a repository checked by URL, when an image path leaves the repository, whether or not the file exists. A checked repository may not read other files on your computer, and its build fails the images gate.

Fix: move or copy the image into the book folder (`images/`) and link it from there.

### Cover

#### MB410: no cover image

Info. Message: `no cover image: a plain typographic cover will be generated`. `cover.image` is not set, and no `cover.jpg`, `cover.jpeg`, or `cover.png` was found in the book folder or its `images`, `image`, `img`, `assets`, `media`, `figures`, or `cover` subfolder.

mdbindery generates a plain typographic cover from the title, subtitle, and authors (colors under `cover:` in [configuration.md](configuration.md#cover)).

Fix: add `images/cover.jpg` at 1600x2560 px, or set `cover.image`.

#### MB411: cover size, ratio, or color mode

Warning. One or more of:

- `cover is 600x900 px; stores want at least 1400 px on the short side`;
- `cover ratio 1.00:1 (height:width); ebook covers are about 1.6:1` (for a square cover), when the height-to-width ratio is outside 1.4 to 1.7;
- `cover is CMYK; ebook covers must be RGB (it will be converted)`.

Stores reject or scale up small covers, and a cover far from 1.6:1 is shown with bars or cropped. The build converts a CMYK cover to RGB, but the colors can shift.

Fix: use a 1600x2560 px RGB image.

#### MB412: cover missing, unreadable, or converted

Error or warning.

Error: `cover image not found: PATH`, when the file named in `cover.image` does not exist (the path is relative to the configuration file's folder), or `the cover image cannot be read`. The build stops on both.

Warning: `cover is WEBP; it will be converted to JPEG`, for a GIF, WebP, or other image the build can read but that is not JPEG or PNG.

Fix: correct `cover.image`, or save the cover as JPEG (1600x2560 px) yourself to control the result.

### HTML

The HTML rules are in [book-structure.md](book-structure.md#10-html).

#### MB500: unsupported HTML tag

Error or warning. The file uses an HTML tag outside the set mdbindery handles. One finding per tag name and file, at its first occurrence, with the tag written as in the file. Only opening tags are read, and only tag names that Markdown accepts: a letter, then letters, digits, or hyphens. Tags in code (fenced, indented, or inline) and in comments, angle-bracket autolinks such as `<https://example.org>` and `<jane@example.org>`, and text such as `<YOUR_NAME>` (an underscore is not allowed in a tag name, so it stays text) are not reported.

Error: `HTML tag <iframe> is not supported in an EPUB and will be removed`, for `script`, `iframe`, `object`, `embed`, `form`, `input`, `button`, `style`, `video`, `audio`, `canvas`, `select`, and `textarea`. Interactive and embedded content cannot work in an ebook. The build removes the element without failing, so whatever it would show is lost; check counts it as an error for that reason.

Warning: `unknown HTML tag <Listing>: the tag is dropped and its content kept`, for any other tag. Examples are mdBook's `<Listing>` and placeholders such as `<yourname>` in running text, which vanish from the EPUB. For text that only looks like a tag, the fix line suggests `&lt;yourname&gt;` or backticks.

These tags are not reported: `a`, `abbr`, `b`, `big`, `blockquote`, `br`, `caption`, `center`, `cite`, `code`, `col`, `colgroup`, `dd`, `del`, `details`, `dfn`, `div`, `dl`, `dt`, `em`, `figcaption`, `figure`, `font`, `h1` to `h6`, `hr`, `i`, `img`, `ins`, `kbd`, `li`, `mark`, `ol`, `p`, `picture`, `pre`, `q`, `s`, `samp`, `small`, `source`, `span`, `strike`, `strong`, `sub`, `summary`, `sup`, `table`, `tbody`, `td`, `tfoot`, `th`, `thead`, `time`, `tr`, `tt`, `u`, `ul`, `var`, `wbr`. The build still removes some of them; MB501 lists what was actually removed.

Fix: replace the element with Markdown, a link to the online version, or a screenshot.

```markdown
<iframe src="https://www.youtube.com/embed/abc"></iframe>        <!-- MB500 error -->
[Watch the launch video](https://www.youtube.com/watch?v=abc)    <!-- fixed -->
```

#### MB501: HTML dropped in conversion

Info. Reported once per file after the pandoc analysis. It lists the tags that the conversion actually removed from that file, for example `HTML without an EPUB equivalent will be dropped: <script>, <iframe>`. `<unparsed>` and `<unparsed-block>` stand for inline and block HTML that could not be parsed.

The tag's formatting is gone in the EPUB. Its text usually stays; for scripts, frames, and styles, the content goes too.

Fix: use Markdown formatting instead.

### Tables

#### MB600: wide table

Warning. A pipe table has `options.wide_table_warn` (default 9) or more columns, and its file is not listed in `options.cards.files`. Only tables whose header row starts with `|` are counted. Message: `table with 10 columns is hard to read on phones`.

On a phone screen a wide table needs horizontal scrolling or becomes unreadably small.

Fix: list the file under `options.cards.files` to render its wide tables as cards (one block per row, for tables with at least `cards.min_columns` columns), or split the table.

```yaml
options:
  cards:
    files: [appendix-a-data.md]
```

### Charts, math, and code

#### MB700: mermaid-cli not installed

Warning. Message: `mermaid-cli not installed: charts would become placeholders`. The book has Mermaid charts and mermaid-cli is not installed.

The charts become placeholders: a quote with the chart's alt text and a pointer to the online edition. With `options.mermaid: png` the build's charts gate warns but does not fail.

Fix: run `mdbindery install-tools` (without `--no-node`), then `mdbindery doctor`.

#### MB701: chart failed to render

Error. mermaid-cli could not render a chart. The message carries mermaid's own error, for example `Mermaid chart "Chart" failed to render: Error: Parse error on line 2: ...t LR  A[Start --> B[ ----------------------^`. The line points to the first ```` ```mermaid ```` block in the file, which is not always the failing one. Not checked with `--no-render` or without mermaid-cli.

The build replaces the chart with a placeholder, and its charts gate fails.

Fix: correct the chart syntax; paste it into https://mermaid.live to see the error.

#### MB710: math

Info. Reported once for the whole book: `1 math expression(s): rendered as MathML, which some readers show poorly`. The count is the number of ```` ```math ```` blocks plus the number of lines with inline `$...$` math.

Some readers show MathML poorly or not at all.

Fix: check the formulas in the preview (`mdbindery preview`) and keep them simple where possible.

#### MB711: dollar signs read as math

Warning. Two dollar signs in running text were read as a formula, although the text between them looks like prose or a path. Message: `text between dollar signs is read as a formula: $HOME/bin:$`, for `export PATH=$HOME/bin:$PATH`. It is reported when the formula has no backslash and holds a `/`, two words of two or more letters separated by a space, or a run of four or more letters.

With `--build`, pandoc's own warnings about formulas it could not convert are reported under the same code: `pandoc: ` followed by the warning.

In the EPUB the dollar signs disappear and the text between them becomes a formula.

Fix: escape the dollar signs as `\$`, or put the text in backticks.

#### MB720: long code lines

Info. Message: `code block has lines over 90 characters; they wrap on small screens`. A fenced code block (not Mermaid or math) or an indented code block has a line longer than 90 characters. The line number points to the opening fence.

Long lines wrap on small screens, which breaks the layout of code.

Fix: shorten the lines if the layout matters.

### Trial build results

These codes appear only with `--build`. The trial EPUB and its reports are deleted after the check, so for the full EPUBCheck and Ace reports run `mdbindery build` and open `dist/reports/`.

#### MB900: EPUBCheck message

Error or warning. EPUBCheck reported a message about the trial EPUB: `ERROR` and `FATAL` messages are errors, all others are warnings. At most 50 messages are reported, each cut to 200 characters. Example:

```markdown
- **MB900** `EPUB/text/ch001.xhtml:15` EPUBCheck RSC-005: Error while parsing file: Duplicate ID "k00-dup"
  - Fix: See docs/troubleshooting.md.
```

The file is a path inside the EPUB, and the line is a line of that XHTML file. Any EPUBCheck error fails the build, and stores reject EPUBs that do not pass it. The example comes from two `<a id="dup"></a>` anchors in one chapter.

Fix: find the source of the message in the chapter file. Common ones: `RSC-005` duplicate IDs, `RSC-032` an unsupported image format (MB403). See [troubleshooting.md](troubleshooting.md).

#### MB901: Ace violation

Error, warning, or info. DAISY Ace reported an accessibility violation. Message: `Ace serious: link-name (x1)`, with the impact, the rule, and the number of occurrences. Impact `critical` or `serious` is an error, `moderate` or `minor` a warning. A rule listed in `options.ace_waivers` is a note, whatever its impact, because the build does not fail on it.

When Ace is not installed (for example after `install-tools --no-node`), MB901 is a warning instead: `Ace is not installed: the accessibility check did not run`, with the fix ``Run `mdbindery install-tools` (without --no-node) to add it.``

Fix: build with `mdbindery build` and open the Ace report (`dist/reports/ace/report.html`) for the location and explanation, then fix the source. The example above comes from a link with no text (`[](https://example.org)`). If a rule does not apply to your book, list it in `ace_waivers`.

#### MB902: word-count mismatch

Error. For at least one file, the number of words in the EPUB differs from the source by more than `wordcount_tolerance` (default 2%) and by more than `wordcount_min_words` (default 25 words). Files listed in `options.cards.files` are exempt. The message names up to five files, worst first, with the difference: a plus sign means the EPUB has more words.

The example comes from a book checked with `wordcount_tolerance: 0` and `wordcount_min_words: 0`, where the chapter titles made from file names count as added words:

```markdown
- **MB902** text lost or added in conversion: 04-nohead.md (+25.0%), 05-textfirst.md (+20.0%), 01-above.md (+11.9%)
  - Fix: Build with --keep-work and compare; usually malformed HTML or an unclosed <div>.
```

The gate catches text that disappeared or was duplicated during conversion, and the build fails on it. A common cause is malformed HTML, such as an unclosed `<div>`, that swallows text.

Fix: run `mdbindery build --keep-work`, read the per-file counts under `wordcount` in `dist/reports/build.json` (`files`, `failing`), and compare the prepared Markdown in the work folder (`k00.md`, `k01.md`, ...) with the chapter in the EPUB.

#### MB903: analysis or trial build failed

Error. The pandoc analysis stopped with an error (`analysis failed: ...`, fix `See the message; often malformed Markdown.`), or the trial build stopped with an error (`trial build failed: ...`), for example because pandoc is missing, the cover cannot be read, or a stylesheet cannot be found. After a failed trial build, `facts.trial_build` is `failed: ` and the message.

No EPUB can be built until the cause is fixed.

Fix: read the message; run `mdbindery build --keep-work` to see the full output. An analysis failure is often caused by malformed Markdown in the file named in the message.

#### MB904: trial build gate failed

Error. A gate of the trial build failed, and no MB900, MB901, or MB902 error explains it. Message: `trial build gate "NAME" failed: DETAIL`, with `See docs/building.md for what each gate checks.` as the fix. Example, with EPUBCheck not installed:

```markdown
- **MB904** trial build gate "epubcheck" failed: EPUBCheck not available
  - Fix: See docs/building.md for what each gate checks.
```

The detail depends on the gate:

| Gate | Detail |
|---|---|
| `links` | `N unresolved anchor(s), M missing file(s)` |
| `images` | the status and path of up to five images, such as `missing images/x.png` |
| `includes` | up to three directives that were not expanded |
| `charts` | up to three chart errors |
| `epubcheck` | `EPUBCheck not available` (Java 11+ or EPUBCheck missing), or `EPUBCheck did not produce a report: ...` |
| `ace` | the end of Ace's output, when Ace is installed but produced no report |

Fix: fix the cause the detail names. For `epubcheck` and `ace`, run `mdbindery doctor` and `mdbindery install-tools`; to build without validation, set `options.epubcheck: false` or `options.ace: false` ([building.md](building.md#gates)).
