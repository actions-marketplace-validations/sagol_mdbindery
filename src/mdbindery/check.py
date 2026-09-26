"""`mdbindery check`: dry run and compatibility report for a local folder or a Git/GitHub repository."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from urllib.parse import unquote, urljoin

from . import config as config_mod
from . import tools
from .markdown import (DEF_RE, IMAGE_EXT_RE, expand_includes, image_labels, headings, is_citation_label, iter_text_lines,
                       mask_dropped, parse_definitions, reference_uses_re, split_blocks, strip_code_spans)

SEVERITIES = ('error', 'warning', 'info')
IMG_MD_RE = re.compile(r'!\[([^\]]*)\]\(\s*(<[^>]+>|[^)\s]+)(?:\s+"([^"]*)")?\s*\)')
IMG_REF_RE = re.compile(r'!\[([^\]]*)\]\[([^\]]*)\]')
IMG_HTML_RE = re.compile(r'<img\b[^>]*>', re.I)
ATTR_RE = re.compile(r'([\w:-]+)\s*=\s*("([^"]*)"|\'([^\']*)\'|([^\s"\'>]+))')
FOOTREF_RE = re.compile(r'\[\^([^\]\s]+)\](?!:)')
FOOTDEF_RE = re.compile(r'^(?:[ \t]*>)*[ \t]{0,3}\[\^([^\]\s]+)\]:')
HTML_TAG_RE = re.compile(r'<([a-zA-Z][a-zA-Z0-9-]*)(?=[\s/>])[^>]*>')  # CommonMark tag names; not autolinks
BARE_CITE_RE = re.compile(r'(?<![\]\\!\w])\[([1-9]\d{0,3})\](?![\(\[:])')
ANCHOR_ONLY_RE = re.compile(r'^\s*<a\s[^>]*\b(id|name)\s*=[^>]*>\s*</a>\s*$', re.I)
ALLOWED_TAGS = {'a', 'br', 'img', 'sup', 'sub', 'b', 'strong', 'i', 'em', 'u', 'ins', 's', 'del', 'strike',
                'kbd', 'code', 'q', 'small', 'mark', 'span', 'div', 'p', 'details', 'summary', 'center',
                'abbr', 'cite', 'table', 'thead', 'tbody', 'tfoot', 'caption', 'tr', 'td', 'th', 'ul', 'ol', 'li',
                'blockquote', 'pre', 'dl', 'dt', 'dd', 'hr', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'figure',
                'figcaption', 'picture', 'source', 'font', 'tt', 'big', 'time', 'var', 'samp', 'dfn', 'wbr',
                'colgroup', 'col'}
ACTIVE_TAGS = ('script', 'iframe', 'object', 'embed', 'form', 'input', 'button', 'style', 'video', 'audio',
               'canvas', 'select', 'textarea')
IMAGE_OK = {'.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp'}
IMAGE_BAD = {'.bmp', '.tif', '.tiff', '.heic', '.heif', '.psd', '.avif', '.ico', '.eps', '.pdf'}
GITHUB_RE = re.compile(r'^(?:https?://)?(?:www\.)?github\.com/([^/\s]+)/([^/\s#?]+?)(?:\.git)?'
                       r'(?:/(tree|blob)/([^/\s]+)(?:/(.*?))?)?/?$', re.I)
GITHUB_SSH_RE = re.compile(r'^(?:git@github\.com:|ssh://git@github\.com/)([^/\s]+)/([^/\s]+?)(?:\.git)?/?$', re.I)
GROUP_OVER = 3  # findings of one code in one file beyond this are grouped in the Markdown report


class Report:
    def __init__(self, target):
        self.target = target
        self.findings = []
        self.facts = {}
        self._seen = set()

    def add(self, severity, code, message, fix='', file='', line=None):
        k = (severity, code, file, line, message)
        if k in self._seen:
            return
        self._seen.add(k)
        self.findings.append({'severity': severity, 'code': code, 'file': file, 'line': line,
                              'message': message, 'fix': fix})

    def count(self, severity):
        return sum(1 for f in self.findings if f['severity'] == severity)

    @property
    def ok(self):
        return self.count('error') == 0


def progress(msg):
    print(msg, file=sys.stderr, flush=True)


# ----------------------------------------------------------------- fetching

def parse_target(target):
    """('local', path) | ('github', owner, repo, branch, subdir) | ('git', url)."""
    if target.startswith('-'):
        raise ValueError(f'not a folder or repository URL: {target}')
    m = GITHUB_RE.match(target)
    if m:
        if m.group(3) == 'blob':
            raise ValueError('this is a link to a single file; check the repository URL or '
                             f'https://github.com/{m.group(1)}/{m.group(2)}/tree/BRANCH/FOLDER')
        return ('github', m.group(1), m.group(2), m.group(4), m.group(5) or '')
    m = GITHUB_SSH_RE.match(target)
    if m:
        return ('github-ssh', m.group(1), m.group(2), None, '')
    if re.match(r'^(https?|ssh|git|file)://', target) or target.startswith('git@') or target.endswith('.git'):
        return ('git', target)
    return ('local', target)


def fetch(target, ref=None, log=progress):
    """Return (local_path, cleanup_dir, github_info). target: path, GitHub URL, or git URL."""
    p = Path(target)
    if p.exists():
        if not p.is_dir():
            raise ValueError(f'not a folder: {target} (give the book folder or its repository URL)')
        return p.resolve(), None, None
    kind = parse_target(target)
    if kind[0] == 'local':
        if re.match(r'^[\w.-]+\.[a-z]{2,}/', target):
            raise ValueError(f'not a folder or repository URL: {target} (did you mean https://{target}?)')
        raise FileNotFoundError(f'folder not found: {target}')
    tmp = Path(tempfile.mkdtemp(prefix='mdbindery-check-'))
    try:
        return _fetch(kind, ref, tmp, log)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise


def _fetch(kind, ref, tmp, log):
    dest = tmp / 'repo'
    gh = kind[0] in ('github', 'github-ssh')
    branch = ref or (kind[3] if gh else None)
    subdir = kind[4] if gh else ''
    if kind[0] == 'github':
        url = f'https://github.com/{kind[1]}/{kind[2]}.git'
    elif kind[0] == 'github-ssh':
        url = f'git@github.com:{kind[1]}/{kind[2]}.git'
    else:
        url = kind[1]
    git = shutil.which('git')
    log(f'fetching {url}' + (f' ({branch})' if branch else ''))
    if git:
        cmd = [git, 'clone', '--depth', '1', '--quiet']
        if branch:
            cmd += ['--branch', branch]
        env = dict(os.environ, GIT_TERMINAL_PROMPT='0', GIT_SSH_COMMAND=os.environ.get(
            'GIT_SSH_COMMAND', 'ssh -o BatchMode=yes'))
        try:
            r = subprocess.run(cmd + ['--', url, str(dest)], capture_output=True, text=True, env=env, timeout=600)
        except subprocess.TimeoutExpired:
            raise RuntimeError(f'git clone timed out: {url}')
        if r.returncode != 0:
            err = r.stderr.strip()
            if branch and ('Remote branch' in err or 'not found in upstream' in err):
                raise RuntimeError(f'branch or tag not found: {branch} (in {url})')
            if 'could not read Username' in err or 'not found' in err.lower() or 'Authentication' in err \
                    or 'Permission denied' in err:
                raise RuntimeError(f'repository not found or not accessible: {url}\n'
                                   'mdbindery clones with your git setup and never asks for a password; for a '
                                   'private repository, clone it yourself and run `mdbindery check <folder>`')
            raise RuntimeError(f'git clone failed: {err}')
    elif kind[0] in ('github', 'github-ssh'):  # without git: the public archive over HTTPS
        owner, repo = kind[1], kind[2]
        if not branch:
            try:
                api = f'https://api.github.com/repos/{owner}/{repo}'
                with urllib.request.urlopen(urllib.request.Request(api, headers={'User-Agent': 'mdbindery'}),
                                            timeout=30) as r:
                    branch = json.load(r).get('default_branch') or 'main'
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    raise RuntimeError(f'repository not found or not public: {url}')
                branch = 'main'
            except OSError:
                branch = 'main'
        zurl = f'https://github.com/{owner}/{repo}/archive/{branch}.zip'
        zpath = tmp / 'repo.zip'
        try:
            with urllib.request.urlopen(urllib.request.Request(zurl, headers={'User-Agent': 'mdbindery'}),
                                        timeout=120) as r, open(zpath, 'wb') as f:
                shutil.copyfileobj(r, f)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise RuntimeError(f'repository or branch not found: {owner}/{repo} ({branch})')
            raise
        with zipfile.ZipFile(zpath) as z:
            root = (tmp / 'x').resolve()
            for n in z.namelist():
                if not (root / n).resolve().is_relative_to(root):
                    raise RuntimeError(f'unsafe path in the downloaded archive: {n}')
            z.extractall(tmp / 'x')
        inner = next((tmp / 'x').iterdir())
        inner.rename(dest)
    else:
        raise RuntimeError('git is required to check repositories outside GitHub')
    info = None
    if gh:
        if not branch:
            r = subprocess.run([git, '-C', str(dest), 'rev-parse', '--abbrev-ref', 'HEAD'], capture_output=True,
                               text=True) if git else None
            branch = (r.stdout.strip() if r and r.returncode == 0 else 'main') or 'main'
        info = {'owner': kind[1], 'repo': kind[2], 'branch': branch, 'subdir': subdir}
    local = (dest / subdir).resolve() if subdir else dest.resolve()
    if not local.is_dir() or not config_mod.contained(local, dest):
        raise FileNotFoundError(f'subfolder not found in repository: {subdir}')
    return local, tmp, info, dest.resolve()


# ------------------------------------------------------------ static checks

def line_of(lines, needle, start=0):
    for i in range(start, len(lines)):
        if needle in lines[i]:
            return i + 1
    return None


def check_encoding(path, rel, rep):
    raw = path.read_bytes()
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError as e:
        rep.add('error', 'MB105', f'not valid UTF-8 (byte {e.start}); the build stops on it',
                'Re-save the file as UTF-8.', rel)
        text = raw.decode('utf-8', errors='replace')
    if text.startswith('﻿'):
        rep.add('info', 'MB105', 'starts with a byte order mark (removed during the build)', '', rel, 1)
    if '\r\n' in text:
        rep.add('info', 'MB105', 'Windows line endings (CRLF); handled, but LF is recommended', '', rel)
    return text.lstrip('﻿').replace('\r\n', '\n').replace('\r', '\n')


def filename_title(rel, book_title=''):
    if rel.lower() == 'readme.md' and book_title:
        return book_title
    name = re.sub(r'[-_]+', ' ', re.sub(r'^[\d\s._-]+', '', re.sub(r'\.md$', '', rel.split('/')[-1], flags=re.I)))
    name = name or rel
    return name[:1].upper() + name[1:]


def check_headings(lines, rel, rep, fcfg, book_title=''):
    hs = headings(lines)
    text_idx = [i for i, _ in iter_text_lines(lines)]
    if not any(l.strip() for l in lines):
        rep.add('warning', 'MB109', 'file is empty', 'Remove it from the reading order or add content.', rel)
        return
    has_title = bool(fcfg.get('title'))
    h1 = [h for h in hs if h[1] == 1]
    if not h1 and not has_title:
        if not hs:
            rep.add('warning', 'MB106', f'no headings: the chapter title will be "{filename_title(rel, book_title)}" '
                    '(from the file name, or the book title for README.md)', 'Start the file with a level-1 heading: "# Chapter title".', rel)
            return
        first = hs[0][0]
        before = [i for i in text_idx if i < first and lines[i].strip() and not ANCHOR_ONLY_RE.match(lines[i])]
        if before:
            rep.add('warning', 'MB106', 'no level-1 heading and text above the first heading: the build makes '
                    f'the chapter title "{filename_title(rel, book_title)}" from the file name (the book title for README.md)',
                    'Add "# Chapter title" as the first line.', rel, first + 1)
        else:
            rep.add('warning', 'MB106', f'no level-1 heading: the build promotes "{hs[0][2][:60]}" to the chapter '
                    'title and moves the file\'s other headings up by the same number of levels',
                    'Add "# Chapter title" as the first line (or set title: for this file).', rel, first + 1)
    elif h1:
        above = [i for i in text_idx if i < h1[0][0] and lines[i].strip() and not ANCHOR_ONLY_RE.match(lines[i])]
        if hs[0][1] != 1 or above:
            rep.add('warning', 'MB110', 'content above the chapter title: the build moves it below the title',
                    'Start the file with its "# Title" heading.', rel, (above[0] if above else hs[0][0]) + 1)
    if len(h1) > 1:
        rep.add('warning', 'MB107', f'{len(h1)} level-1 headings: each starts a new EPUB section and TOC entry',
                'Keep one "#" heading per file. If the first one repeats the book title in every file, delete '
                'it; otherwise demote the others to "##".', rel, h1[1][0] + 1)
    prev = 0
    for i, lvl, t in hs:
        if prev and lvl > prev + 1:
            rep.add('warning', 'MB108', f'heading level jumps from {prev} to {lvl}: "{t[:60]}"',
                    'Do not skip heading levels (screen readers and the TOC rely on them).', rel, i + 1)
        prev = lvl


def check_citations(lines, rel, rep, opts):
    refdefs = opts.get('citations', 'refdefs') == 'refdefs'
    defs, dups = parse_definitions(lines) if refdefs else ({}, [])
    for label, i in dups:
        rep.add('error', 'MB301', f'reference [{label}] is defined twice with different URLs',
                'Keep one definition per label in each file.', rel, i + 1)
    text_lines = [(i, strip_code_spans(l)) for i, l in iter_text_lines(lines) if not DEF_RE.match(l)]
    used = set()
    if defs:
        uses = reference_uses_re(defs)
        low = {k.lower(): k for k in defs}
        for i, l in iter_text_lines(lines):
            if DEF_RE.match(l):
                continue
            for m in uses.finditer(l):
                g = next(g for g in m.groups() if g)
                used.add(low.get(g.lower(), g))
        for label, (url, title, i) in defs.items():
            if label not in used:
                rep.add('warning', 'MB300', f'reference [{label}] is defined but never used',
                        'Use it in the text or delete the definition line.', rel, i + 1)
    not_cites = image_labels(lines)
    cites = {k: v for k, v in defs.items() if is_citation_label(k, opts) and k.lower() not in not_cites
             and (k.isdigit() or not IMAGE_EXT_RE.search(v[0]))}  # the rest are plain links and images
    for label, (url, title, i) in cites.items():
        if not title:
            rep.add('info', 'MB306', f'reference [{label}] has no title; the list will show only the URL',
                    'Add a title: [n]: https://example.org "Author, Title, year"', rel, i + 1)
    if cites:
        heads = set(opts.get('reference_headings') or [])
        if not any(t in heads for _, _, t in headings(lines)):
            rep.add('info', 'MB303', 'citations but no References heading: a "References" section will be added '
                    'at the end of the file', 'Add "## References" above the definitions to control the position.', rel)
    for i, l in text_lines if refdefs else []:
        for m in BARE_CITE_RE.finditer(l):
            if m.group(1) not in defs:
                rep.add('warning', 'MB302', f'"[{m.group(1)}]" looks like a citation but has no definition in this file',
                        f"Add the line  [{m.group(1)}]: https://... \"Author, Title, year\"  to this file "
                        '(definitions are per file), or remove the brackets.',
                        rel, i + 1)
    refs = {}
    for i, l in text_lines:
        for m in FOOTREF_RE.finditer(l):
            refs.setdefault(m.group(1), i)
    fdefs = {m.group(1): i for i, l in iter_text_lines(lines) for m in [FOOTDEF_RE.match(l)] if m}
    for k, i in refs.items():
        if k not in fdefs:
            rep.add('error', 'MB304', f'footnote [^{k}] has no definition', f'Add "[^{k}]: note text".', rel, i + 1)
    for k, i in fdefs.items():
        if k not in refs:
            rep.add('warning', 'MB305', f'footnote [^{k}] is defined but never used', '', rel, i + 1)
    return len(cites), len(fdefs)


def image_facts(path):
    try:
        from PIL import Image
        with Image.open(path) as im:
            return im.format, im.size, getattr(im, 'is_animated', False)
    except Exception:
        return None, None, False


def check_image_file(abs_path, src, rel, line, rep, alt, kind='image'):
    ext = Path(src.split('?')[0]).suffix.lower()
    if ext in IMAGE_BAD:
        rep.add('error', 'MB403', f'{kind} format {ext} is not supported in EPUB: {src}',
                'Convert to JPEG (photos) or PNG (diagrams, screenshots); SVG and WebP also work.', rel, line)
    elif ext and ext not in IMAGE_OK:
        rep.add('warning', 'MB403', f'unusual {kind} format {ext}: {src}', 'Use JPEG, PNG, GIF, SVG, or WebP.', rel, line)
    size = abs_path.stat().st_size
    fmt, dims, animated = image_facts(abs_path) if ext != '.svg' else ('SVG', None, False)
    if dims and max(dims) > 3200:
        rep.add('warning', 'MB404', f'{kind} is {dims[0]}x{dims[1]} px: larger than readers need ({src})',
                'Scale to at most 3200 px on the long side.', rel, line)
    if size > 5 * 1024 * 1024:
        rep.add('warning', 'MB404', f'{kind} file is {size / 1048576:.1f} MB ({src})',
                'Compress it (JPEG quality 85) or scale it down; stores limit total size.', rel, line)
    if animated:
        rep.add('info', 'MB405', f'animated GIF: most readers show only the first frame ({src})', '', rel, line)
    if ext == '.svg':
        t = abs_path.read_text(encoding='utf-8', errors='replace')
        if '<script' in t or 'foreignObject' in t:
            rep.add('warning', 'MB405', f'SVG uses scripts or foreignObject, which many readers drop ({src})',
                    'Export the SVG with plain text elements, or use PNG.', rel, line)
    if alt is None or (alt != '' and not alt.strip()) or alt == '\0md':
        rep.add('warning', 'MB402', f'image without alt text: {src}',
                'Describe the image: ![what it shows](path), or alt="..." on <img>. Screen readers need it; '
                'use alt="" on <img> only for purely decorative images.', rel, line)


def repo_file_for_url(url, github):
    """Path inside the repository when an image URL points into the same GitHub repository."""
    if not github:
        return None
    m = re.match(r'^https?://(?:github\.com/([^/]+/[^/]+)/(?:blob|raw)/[^/]+/|'
                 r'raw\.githubusercontent\.com/([^/]+/[^/]+)/[^/]+/)([^?#]+)', url)
    if m and (m.group(1) or m.group(2)).lower() == github.lower():
        return unquote(m.group(3))
    return None


def check_images(lines, path, rel, rep, src_root, repo_root, github, defs, strict_root=None):
    counts = {'inline': 0, 'block': 0, 'figure': 0, 'full-page': 0}
    text = list(iter_text_lines(lines))
    joined = {}
    for i, l in text:  # an <img> tag spread over several lines is read as one
        if re.search(r'<img\b[^>]*$', l, re.I):
            j, buf = i, l
            while '>' not in buf[buf.lower().rfind('<img'):] and j + 1 < len(lines):
                j += 1
                buf += ' ' + lines[j]
            joined[i] = buf
    for i, l in text:
        l = strip_code_spans(joined.get(i, l))
        found = []
        for m in IMG_MD_RE.finditer(l):
            # Markdown has no "decorative" form: an empty alt is a missing alt
            found.append((m.group(1) if m.group(1).strip() else '\0md', m.group(2).strip('<>'), m.group(3) or ''))
        for m in IMG_REF_RE.finditer(l):
            label = m.group(2) or m.group(1)
            d = next((v for k, v in defs.items() if k.lower() == label.lower()), None)
            if d:
                found.append((m.group(1) if m.group(1).strip() else '\0md', d[0], d[1] or ''))
        for m in IMG_HTML_RE.finditer(l):
            attrs = {a.group(1).lower(): next(g for g in (a.group(3), a.group(4), a.group(5)) if g is not None)
                     for a in ATTR_RE.finditer(m.group(0))}
            found.append((attrs.get('alt'), attrs.get('src', ''), attrs.get('title', '')))
        rest = re.sub(r'</?(p|div|center|picture)\b[^>]*>', '',
                      IMG_HTML_RE.sub('', IMG_REF_RE.sub('', IMG_MD_RE.sub('', l))), flags=re.I)
        only = len(found) == 1 and not rest.strip()
        for alt, src, title in found:
            in_figure = re.search(r'<figure\b', l, re.I) is not None  # pandoc reads <figure> as a figure
            kind = ('full-page' if title.lower().startswith(('full-page', 'fullpage')) else
                    'figure' if ((title and only) or in_figure) else 'block' if only else 'inline')
            counts[kind] += 1
            if not src:
                rep.add('error', 'MB400', 'image without a source path', '', rel, i + 1)
                continue
            machine = False
            if src.lower().startswith('file:'):  # file:///abs is this machine; file:rel and file://rel are relative
                machine = src[5:].startswith('///')
                src = re.sub(r'^/([A-Za-z]:)', r'\1', src[7:] if src[5:].startswith('//') else src[5:])
            elif re.match(r'^[a-zA-Z][\w+.-]*:', src) and not re.match(r'^[a-zA-Z]:[\\/]', src):
                local = repo_file_for_url(src, github)
                if local and (repo_root / local).is_file():
                    rep.add('info', 'MB401', f'image URL points to this repository; the build uses the local file '
                            f'{local}', f'Link the file directly: {os.path.relpath(repo_root / local, path.parent)}'
                            .replace('\\', '/'), rel, i + 1)
                    check_image_file(repo_root / local, local, rel, i + 1, rep, alt)
                elif src.startswith(('http://', 'https://')):
                    rep.add('error', 'MB401', f'remote image: {src}',
                            'Download it into the repository (e.g. images/) and link it with a relative path; '
                            'EPUB files cannot load images from the web.', rel, i + 1)
                else:
                    rep.add('error', 'MB401', f'unsupported image URL: {src}', 'Use a relative path.', rel, i + 1)
                continue
            rel_src = unquote(src.split('?')[0].split('#')[0])
            if machine or re.match(r'^[A-Za-z]:[\\/]|^[\\/]{2}', rel_src):
                target = Path(rel_src)  # a path on this machine
            else:
                target = ((repo_root / rel_src.lstrip('/')) if rel_src.startswith('/') else
                          (path.parent / rel_src)).resolve()
            if strict_root and not config_mod.contained(target, strict_root):
                rep.add('error', 'MB406', f'image outside the repository: {src}',
                        'Keep images inside the repository; a checked repository may not read other files.',
                        rel, i + 1)
                continue
            if not target.is_file():
                rep.add('error', 'MB400', f'image file not found: {src}',
                        'Fix the path; image paths are relative to the Markdown file ("/" means the repository '
                        'root).', rel, i + 1)
                continue
            if not config_mod.contained(target, src_root):
                rep.add('warning', 'MB406', f'image lies outside the book folder: {src}',
                        'Keep images inside the book folder (e.g. images/).', rel, i + 1)
            check_image_file(target, src, rel, i + 1, rep, alt)
    return counts


def check_html(lines, rel, rep):
    tags = {}
    for i, l in iter_text_lines(lines):
        for m in HTML_TAG_RE.finditer(strip_code_spans(l)):
            t = m.group(1)
            if t.lower() not in ALLOWED_TAGS:
                tags.setdefault(t.lower(), (t, i + 1))
    for low, (t, line) in tags.items():
        if low in ACTIVE_TAGS:
            rep.add('error', 'MB500', f'HTML tag <{t}> is not supported in an EPUB and will be removed',
                    'Replace it with Markdown (or drop it); scripts, forms, and embedded media cannot work in '
                    'an ebook.', rel, line)
        else:
            rep.add('warning', 'MB500', f'unknown HTML tag <{t}>: the tag is dropped and its content kept',
                    f'If it is meant as text, write &lt;{t}&gt; or put it in `backticks`.', rel, line)


def check_tables(lines, rel, rep, warn_cols, card_files):
    for kind, _, start, blk in split_blocks(lines):
        if kind != 'text':
            continue
        for j in range(len(blk) - 1):
            head, sep = blk[j], blk[j + 1]
            if head.lstrip().startswith('|') and re.match(r'^\s*\|?[\s:|-]+\|[\s:|-]*$', sep) and '-' in sep:
                cols = len([c for c in head.strip().strip('|').split('|')])
                if cols >= warn_cols and rel not in card_files:
                    rep.add('warning', 'MB600', f'table with {cols} columns is hard to read on phones',
                            f'List "{rel}" under options.cards.files to render its wide tables as cards, '
                            'or split the table.', rel, start + j + 1)


def check_code(lines, rel, rep):
    charts = math = 0
    for kind, info, start, blk in split_blocks(lines):
        if kind in ('code', 'icode'):
            body = blk[1:-1] if kind == 'code' else blk
            if kind == 'code' and info.startswith('mermaid'):
                charts += 1
            elif kind == 'code' and info == 'math':
                math += 1
            elif any(len(l) > 90 for l in body):
                rep.add('info', 'MB720', 'code block has lines over 90 characters; they wrap on small screens',
                        'Shorten long lines if the layout matters.', rel, start + 1)
    for _, l in iter_text_lines(lines):
        if re.search(r'(?<![\\$\w])\$[^\s$](?:[^$]*[^\s$\\])?\$(?![\d\w])', strip_code_spans(l)):
            math += 1
    return charts, math


def check_includes(text, path, rel, rep, repo_root):
    if '{{#' not in text:
        return 0
    lines = text.split('\n')
    _, n, errors = expand_includes(text, path.parent, repo_root)
    for directive, err in errors:
        rep.add('error', 'MB131', f'mdBook directive not expanded ({err}): {directive[:120]}',
                'Fix the path (relative to this file) or replace the directive with the text it should include.',
                rel, line_of(lines, directive))
    return n


def suspicious_math(expr):
    """Inline math that is probably prose between two dollar signs."""
    if '\\' in expr:
        return False
    return bool(re.search(r'[A-Za-z]{2,}\s+[A-Za-z]{2,}|/|[A-Za-z]{4,}', expr))


# ------------------------------------------------------------------ main

def check(target, config_path=None, ref=None, do_build=False, render=True, log=progress):
    fetched = fetch(target, ref, log)
    local, cleanup, gh = fetched[:3]
    repo_root = fetched[3] if len(fetched) > 3 else None
    rep = Report(target)
    if gh:
        rep.facts['github'] = gh
    try:
        return _check(local, config_path, rep, gh, do_build, render, log, remote=cleanup is not None,
                      repo_root=repo_root)
    finally:
        if cleanup:
            shutil.rmtree(cleanup, ignore_errors=True)


def _check(local, config_path, rep, gh, do_build, render, log, remote=False, repo_root=None):
    try:
        hint = gh['repo'] if gh else (re.sub(r'\.git$', '', re.split(r'[/:]', rep.target.rstrip('/'))[-1]) if remote
                                      else None)
        cfg = config_mod.load(local, config_path, name_hint=hint,
                              trusted=not remote, repo_root=repo_root)
    except config_mod.ConfigError as e:
        rep.add('error', 'MB102', str(e), 'Fix mdbindery.yaml (see docs/configuration.md).')
        return rep
    src = cfg.source
    repo = Path(cfg.repo_root)
    if gh:
        cfg.github = cfg.github or f"{gh['owner']}/{gh['repo']}"
    rep.facts.update({'source': str(src), 'config': str(cfg.path) if cfg.path else None,
                      'inferred': cfg.inferred, 'title': cfg.meta['title'], 'lang': cfg.meta['lang'],
                      'files': [f['file'] for f in cfg['files']]})
    for w in cfg.warnings:
        rep.add('warning', 'MB102', w, 'Check the key name against docs/configuration.md.',
                str(cfg.path.name) if cfg.path else '')
    if not cfg.path:
        rep.add('info', 'MB101', 'no mdbindery.yaml: using an inferred configuration',
                'Run `mdbindery init` to write one, then review the reading order and metadata.')
    if cfg.mdbook:
        rep.add('info', 'MB130', 'mdBook layout: reading order from SUMMARY.md, title from book.toml, '
                '{{#include}} directives expanded, hidden "# " lines in Rust code removed', '')
    if not cfg['files']:
        rep.add('error', 'MB100', 'no Markdown files found', 'Put chapters as .md files in the book folder '
                'or in chapters/, or list them under files: in mdbindery.yaml.')
        return rep
    if cfg.order_source:
        rep.add('info', 'MB125', f'reading order inferred from {cfg.order_source}',
                'Check the "Reading order" list below; set files: in mdbindery.yaml to change it.')

    # reading order
    listed = {f['file'] for f in cfg['files']}
    for f in cfg['files']:
        if not (src / f['file']).is_file():
            rep.add('error', 'MB103', f"file in the reading order not found: {f['file']}",
                    'Fix the name under files: in mdbindery.yaml.')
    if cfg.path or (src / 'chapters').is_dir():
        cand = list(src.glob('*.md')) + (list((src / 'chapters').glob('*.md')) if (src / 'chapters').is_dir() else [])
        for p in sorted(cand):
            r = str(p.relative_to(src)).replace('\\', '/')
            if r not in listed and p.stem.lower() not in config_mod.SKIP_FILES and p.name.lower() != 'readme.md':
                rep.add('info', 'MB104', f'Markdown file not in the reading order: {r}',
                        'Add it under files: if it belongs in the book.')
    for toc in config_mod.TOC_FILES:
        if toc in listed:
            rep.add('warning', 'MB126', f'{toc} is in the reading order: a hand-written table of contents '
                    'repeats the EPUB navigation', 'Remove it from files:; the EPUB has its own table of contents.')

    # metadata
    md = cfg.meta
    if 'metadata.title' in cfg.inferred:
        rep.add('info', 'MB120', f'title inferred: "{md["title"]}"', 'Set metadata.title in mdbindery.yaml.')
    if not md.get('authors'):
        rep.add('warning', 'MB121', 'no author', 'Set metadata.authors: [First Last].')
    if 'metadata.lang' in cfg.inferred:
        rep.add('info', 'MB122', f'language inferred: {md["lang"]}', 'Set metadata.lang (e.g. en-US, ru, de).')
    if not md.get('rights'):
        rep.add('warning', 'MB123', 'no license or rights statement', 'Add a LICENSE file or set metadata.rights.')
    if not md.get('identifier'):
        rep.add('info', 'MB124', 'no identifier: a permanent urn:uuid will be generated on the first build',
                'Keep "identifier:" in mdbindery.yaml so the build can save it.')
    suggested = ''
    if gh and not cfg['source_url']:
        sub = os.path.relpath(src.resolve(), repo.resolve()).replace('\\', '/')
        suggested = f"https://github.com/{gh['owner']}/{gh['repo']}/blob/{gh['branch']}/" + \
            ('' if sub == '.' else sub.strip('/') + '/')
        cfg.data['source_url'] = suggested  # so the analysis treats outside links as they would be built
    elif not cfg['source_url']:
        suggested = cfg.suggested_source_url

    # cover
    cov = cfg['cover'].get('image')
    if not cov:
        rep.add('info', 'MB410', 'no cover image: a plain typographic cover will be generated',
                'Add cover.jpg (1600x2560 px) to the book folder or images/.')
    else:
        base = src if cfg['cover'].get('_base') == 'source' else cfg.base
        cp = (base / cov).resolve()
        if not cp.is_file():
            rep.add('error', 'MB412', f'cover image not found: {cov}', 'Fix cover.image in mdbindery.yaml.')
        else:
            fmt, dims, _ = image_facts(cp)
            if not fmt:
                rep.add('error', 'MB412', 'the cover image cannot be read', 'Save it again as JPEG (1600x2560 px).')
            elif fmt not in ('JPEG', 'PNG'):
                rep.add('warning', 'MB412', f'cover is {fmt}; it will be converted to JPEG',
                        'Provide a JPEG to control the result.')
            if fmt:
                try:
                    from PIL import Image
                    with Image.open(cp) as im:
                        if im.mode == 'CMYK':
                            rep.add('warning', 'MB411', 'cover is CMYK; ebook covers must be RGB (it will be converted)',
                                    'Export the cover in RGB.')
                except Exception:
                    pass
            if dims:
                w, h = dims
                if min(w, h) < 1400:
                    rep.add('warning', 'MB411', f'cover is {w}x{h} px; stores want at least 1400 px on the short side',
                            'Use 1600x2560 px.')
                if not 1.4 <= h / w <= 1.7:
                    rep.add('warning', 'MB411', f'cover ratio {h / w:.2f}:1 (height:width); ebook covers are about 1.6:1',
                            'Use 1600x2560 px.')

    # per-file static checks
    totals = {'refs': 0, 'footnotes': 0, 'images': {'inline': 0, 'block': 0, 'figure': 0, 'full-page': 0},
              'charts': 0, 'math': 0, 'includes': 0}
    card_files = set(cfg.opts['cards'].get('files') or [])
    repeated = {}
    for f in cfg['files']:
        path = src / f['file']
        if not path.is_file():
            continue
        rel = f['file']
        text = check_encoding(path, rel, rep)
        totals['includes'] += check_includes(text, path, rel, rep, repo)
        if '{{#' in text:
            text = expand_includes(text, path.parent, repo)[0]
        lines = mask_dropped(text.split('\n'), f.get('drop_sections') or [], cfg.opts.get('drop_lines') or [])
        fm_end = next((j for j in range(1, min(len(lines), 40)) if lines[j].strip() in ('---', '...')), None) \
            if lines and lines[0].strip() == '---' else None
        if fm_end:
            lines = [''] * (fm_end + 1) + lines[fm_end + 1:]  # pandoc drops front matter; so does check
            rep.add('warning', 'MB111', 'YAML front matter at the top of the file is ignored (and hidden from '
                    'the book)', 'Move title and metadata into mdbindery.yaml.', rel, 1)
        check_headings(lines, rel, rep, f, cfg.meta['title'])
        nd, nf = check_citations(lines, rel, rep, cfg.opts)
        totals['refs'] += nd
        totals['footnotes'] += nf
        defs, _ = parse_definitions(lines)
        c = check_images(lines, path, rel, rep, src.resolve(), repo, cfg.github,
                         {k: (v[0], v[1]) for k, v in defs.items()}, None if cfg.trusted else repo)
        for k, v in c.items():
            totals['images'][k] += v
        check_html(lines, rel, rep)
        check_tables(lines, rel, rep, cfg.opts['wide_table_warn'], card_files)
        ch, mt = check_code(lines, rel, rep)
        totals['charts'] += ch
        totals['math'] += mt
        h1s = [t for _, lvl, t in headings(lines) if lvl == 1]
        if len(h1s) > 1:
            repeated.setdefault(h1s[0], []).append(rel)
    for text, files in repeated.items():
        if len(files) >= 2:
            pattern = '^#\\s+' + re.sub(r'([.^$*+?{}\[\]\\|()])', r'\\\1', text).replace("'", "''") + '\\s*$'
            rep.add('info', 'MB107', f'{len(files)} files start with the same heading "{text[:60]}" before their '
                    'chapter title', f"To drop it without editing the files, add to options: "
                    f"drop_lines: ['{pattern}']")
    rep.facts['totals'] = totals
    if totals['math']:
        rep.add('info', 'MB710', f"{totals['math']} math expression(s): rendered as MathML, which some readers "
                'show poorly', 'Check them in the preview; keep formulas simple where possible.')

    # analysis with pandoc: real link resolution, HTML conversion, charts
    if not tools.find('pandoc'):
        rep.add('warning', 'MB001', 'pandoc not installed (or older than 3.8): internal links were not verified',
                'Run `mdbindery install-tools`, then check again.')
    else:
        from .build import analyze, BuildError
        work = Path(tempfile.mkdtemp(prefix='mdbindery-analyze-'))
        try:
            if not render or not tools.command('mmdc'):
                cfg.opts['mermaid'] = 'placeholder' if cfg.opts['mermaid'] == 'png' else cfg.opts['mermaid']
                if totals['charts'] and not tools.command('mmdc'):
                    rep.add('warning', 'MB700', 'mermaid-cli not installed: charts would become placeholders',
                            'Run `mdbindery install-tools`.')
            a = analyze(cfg, work, log=lambda *_: None, skip_missing=True)
            analysis_findings(rep, a, cfg, src, suggested)
        except BuildError as e:
            rep.add('error', 'MB903', f'analysis failed: {str(e)[:500]}', 'See the message; often malformed Markdown.')
        finally:
            shutil.rmtree(work, ignore_errors=True)

    if do_build and rep.ok:
        trial_build(rep, cfg)
    elif do_build:
        rep.facts['trial_build'] = 'skipped: fix the errors first'
    if not cfg.path:
        if suggested and not cfg.user.get('source_url'):
            cfg.data['source_url'] = suggested
        rep.facts['suggested_config'] = config_mod.starter_yaml(cfg)
    return rep


def analysis_findings(rep, a, cfg, src, suggested):
    from .build import site_links
    site = site_links(cfg)
    key_file = {f['key']: f['file'] for f in cfg['files']}
    texts = {f['file']: (src / f['file']).read_text(encoding='utf-8', errors='replace').split('\n')
             for f in cfg['files'] if (src / f['file']).is_file()}
    for u in a['links']['unresolved']:
        srcf = key_file.get(u.get('source'), '')
        ln = line_of(texts.get(srcf, []), '#' + u['fragment']) or \
            line_of(texts.get(srcf, []), u['fragment'].replace(' ', '%20'))
        rep.add('error', 'MB200', f"link to missing anchor: {u['file']}#{u['fragment']} (link text: {u['text'][:60]})",
                'Point the link at an existing heading (GitHub-style slug) or add <a id="..."></a> there.',
                srcf, ln)
    for fz in a['links']['fuzzy']:
        srcf = key_file.get(fz.get('source'), '')
        rep.add('warning', 'MB201', f"link #{fz['fragment']} matched only approximately "
                f"(anchor is #{fz['to'].split('-', 1)[1]})", 'Use the exact anchor.', srcf,
                line_of(texts.get(srcf, []), '#' + fz['fragment']))
    for name, info in a['files'].items():
        r = info['report']
        for e in r.get('external', []):
            base = e['path'].split('/')[-1]
            ln = line_of(texts.get(name, []), base.replace(' ', '%20')) or line_of(texts.get(name, []), base)
            if not e.get('exists', True) and e['mode'] == 'source_url' and site:
                rep.add('warning', 'MB203', f"link to {e['path']}, which is not in the repository: it points to "
                        f"{urljoin(cfg['source_url'], re.sub(r'(?i)\.md$', '.html', re.sub(r'(?i)readme\.md$', 'index.html', e['path'])))} "
                        "(not checked)", 'Make sure the page exists on the website.',
                        name, ln)
            elif not e.get('exists', True):
                hint = (' If it is a page of the published website, set source_url to the web address of the '
                        'book folder, or use a full https:// link.' if e['path'].lower().endswith(('.html', '.htm'))
                        else '')
                rep.add('error', 'MB204', f"link to a missing file: {e['path']}",
                        'Fix the path (relative to this file) or remove the link.' + hint, name, ln)
            elif e['mode'] == 'unlinked':
                fix = (f'Set source_url: {suggested} so the link points to the online repository, or add the '
                       'file to the reading order.' if suggested else
                       'Set source_url so the link points to the online repository, or add the file to the '
                       'reading order.')
                rep.add('warning', 'MB202', f"link to {e['path']}, which is not part of the book: "
                        'it becomes plain text in the EPUB', fix, name, ln)
            elif e['mode'] == 'source_url' and not cfg.user.get('source_url'):
                rep.add('info', 'MB202', f"link to {e['path']} (not in the book) will point to the online "
                        'repository', f'Set source_url: {cfg["source_url"]}', name, ln)
        if r.get('html_links'):
            rep.add('info', 'MB205', f"{r['html_links']} link(s) to .html pages or folders resolved to the matching .md files",
                    '', name)
        if r.get('html_removed'):
            tags = ', '.join(f"<{x['tag']}>" for x in r['html_removed'])
            rep.add('info', 'MB501', f'HTML without an EPUB equivalent will be dropped: {tags}',
                    'Prefer Markdown formatting.', name)
        for img in r.get('images', []):
            if img['status'] in ('ok',) or img.get('local_copy'):
                continue
            already = any(x['file'] == name and x['code'] in ('MB400', 'MB401', 'MB406') and img['src'] in x['message']
                          for x in rep.findings)
            if already:
                continue
            what = {'missing': ('MB400', 'image file not found'), 'remote': ('MB401', 'remote image'),
                    'empty': ('MB400', 'image without a source path'),
                    'outside': ('MB406', 'image outside the repository (not allowed for checked repositories)')}
            code, msg = what.get(img['status'], ('MB400', f"image problem ({img['status']})"))
            rep.add('error', code, f"{msg}: {img['src']}", 'Fix the path; image paths are relative to the '
                    'Markdown file.', name, line_of(texts.get(name, []), img['src']))
        for expr in r.get('math', []):
            if suspicious_math(expr):
                rep.add('warning', 'MB711', f'text between dollar signs is read as a formula: ${expr[:60]}$',
                        'If these are not formulas, escape the dollar signs as \\$.', name,
                        line_of(texts.get(name, []), '$' + expr[:20]))
    for m in a['mermaid_failures']:
        rep.add('error', 'MB701', f"Mermaid chart \"{m['alt'][:60]}\" failed to render: {m['error']}",
                'Fix the chart syntax (paste it into https://mermaid.live to see the error).',
                m['file'], line_of(texts.get(m['file'], []), '```mermaid'))


def trial_build(rep, cfg):
    from .build import build
    out = Path(tempfile.mkdtemp(prefix='mdbindery-trial-'))
    try:
        if not cfg.meta.get('identifier'):  # a dry run never writes into the user's config
            import uuid
            cfg.meta['identifier'] = f'urn:uuid:{uuid.uuid4()}'
        s = build(cfg, out_dir=out, log=lambda *_: None)
        g = s['gates']
        ec = g.get('epubcheck', {})
        for m in ec.get('messages', []):
            sev = 'error' if m['severity'] in ('ERROR', 'FATAL') else 'warning'
            rep.add(sev, 'MB900', f"EPUBCheck {m['id']}: {m['message'][:200]}",
                    'See docs/troubleshooting.md.', m.get('path', ''), m.get('line') or None)
        waived = set(cfg.opts.get('ace_waivers') or [])
        for v in g.get('ace', {}).get('violations', []):
            sev = ('info' if v['rule'] in waived else
                   'error' if v['impact'] in ('critical', 'serious') else 'warning')
            rep.add(sev, 'MB901', f"Ace {v['impact']}: {v['rule']} (x{v['count']})", 'See the Ace report.')
        if g.get('ace', {}).get('result') == 'warn':
            rep.add('warning', 'MB901', 'Ace is not installed: the accessibility check did not run',
                    'Run `mdbindery install-tools` (without --no-node) to add it.')
        wc = g.get('wordcount', {})
        if wc.get('result') == 'fail':
            files = ', '.join(f"{n} ({wc['files'][n]['diff']:+.1%})" for n in wc.get('failing', [])[:5])
            rep.add('error', 'MB902', f'text lost or added in conversion: {files}',
                    'Build with --keep-work and compare; usually malformed HTML or an unclosed <div>.')
        for line in s.get('pandoc_warnings', []):
            if 'Could not convert TeX math' in line:
                rep.add('warning', 'MB711', f'pandoc: {line[:200]}',
                        'If the dollar signs are not a formula, escape them as \\$.')
        # every failed gate is an error, even one that produced no messages above
        reported = {'epubcheck': 'MB900', 'ace': 'MB901', 'wordcount': 'MB902'}
        for name, gate in g.items():
            if gate.get('result') != 'fail':
                continue
            code = reported.get(name)
            if code and any(f['code'] == code and f['severity'] == 'error' for f in rep.findings):
                continue
            detail = gate.get('detail') or ''
            if name == 'images':
                detail = '; '.join(f"{p['status']} {p['src']}" for p in gate.get('problems', [])[:5])
            elif name == 'links':
                detail = f"{gate.get('unresolved', 0)} unresolved anchor(s), {gate.get('missing_files', 0)} missing file(s)"
            elif name == 'includes':
                detail = '; '.join(p['directive'][:80] for p in gate.get('problems', [])[:3])
            elif name == 'charts':
                detail = '; '.join(p['error'][:80] for p in gate.get('failures', [])[:3])
            rep.add('error', 'MB904', f'trial build gate "{name}" failed' + (f': {detail[:400]}' if detail else ''),
                    'See docs/building.md for what each gate checks.')
        size = Path(s['epub']).stat().st_size // 1024 if s.get('epub') and Path(s['epub']).exists() else 0
        rep.facts['trial_build'] = (f'passed ({size} KB)' if s['ok'] else
                                    f"failed: {', '.join(s['failed_gates'])} ({size} KB)")
    except Exception as e:  # noqa: BLE001 - report any build failure
        rep.add('error', 'MB903', f'trial build failed: {str(e)[:500]}', '')
        rep.facts['trial_build'] = 'failed: ' + str(e)[:200]
    finally:
        shutil.rmtree(out, ignore_errors=True)


# ------------------------------------------------------------------ output

def code_summary(rep):
    out = {}
    for f in rep.findings:
        k = (f['code'], f['severity'])
        out[k] = out.get(k, 0) + 1
    order = {s: i for i, s in enumerate(SEVERITIES)}
    return sorted(out.items(), key=lambda kv: (order[kv[0][1]], kv[0][0]))


def to_markdown(rep):
    e, w, i = rep.count('error'), rep.count('warning'), rep.count('info')
    verdict = 'ready to build' if e == 0 else 'needs fixes before a correct EPUB can be built'
    f = rep.facts
    gh = f.get('github')
    title = rep.target + (f" (branch {gh['branch']})" if gh and gh.get('branch') else '')
    out = [f'# mdbindery check: {title}', '',
           f'**Result:** {verdict}. {e} error(s), {w} warning(s), {i} note(s).', '']
    if f.get('title'):
        t = f.get('totals', {})
        imgs = t.get('images') or {}
        n_img = sum(imgs.values())
        out += ['## Book', '',
                f"- Title: {f['title']} ({f.get('lang')})",
                f"- Config: {f.get('config') or 'none (inferred)'}",
                f"- Files in reading order: {len(f.get('files', []))}",
                f"- References: {t.get('refs', 0)}; footnotes: {t.get('footnotes', 0)}; charts: {t.get('charts', 0)}"
                + (f"; includes expanded: {t['includes']}" if t.get('includes') else ''),
                f"- Images: {n_img}" + (f" ({', '.join(f'{k} {v}' for k, v in imgs.items() if v)})" if n_img else '')]
        if f.get('trial_build'):
            out.append(f"- Trial build: {f['trial_build']}")
        out.append('')
    summary = code_summary(rep)
    if len(rep.findings) > 10:
        out += ['## Summary', '', '| Code | Severity | Count |', '|---|---|---|']
        out += [f'| {code} | {sev} | {n} |' for (code, sev), n in summary]
        out.append('')
    for sev, heading in (('error', 'Errors'), ('warning', 'Warnings'), ('info', 'Notes')):
        items = [x for x in rep.findings if x['severity'] == sev]
        if not items:
            continue
        out += [f'## {heading}', '']
        groups = {}
        for x in items:
            groups.setdefault((x['code'], x['file']), []).append(x)
        for (code, file), xs in groups.items():
            if len(xs) <= GROUP_OVER:
                for x in xs:
                    loc = x['file'] + (f":{x['line']}" if x['line'] else '') if x['file'] else ''
                    out.append(f"- **{x['code']}** {('`' + loc + '` ') if loc else ''}{x['message']}")
                    if x['fix']:
                        out.append(f"  - Fix: {x['fix']}")
                continue
            lines = [str(x['line']) for x in xs if x['line']]
            msgs = list(dict.fromkeys(x['message'] for x in xs))
            where = f"`{file}` " if file else ''
            at = f" (lines {', '.join(lines[:15])}{', ...' if len(lines) > 15 else ''})" if lines else ''
            if len(msgs) == 1:
                out.append(f"- **{code}** {where}{msgs[0]}: {len(xs)} times{at}")
            else:
                out.append(f"- **{code}** {where}{len(xs)} findings{at}:")
                out += [f'  - {m}' for m in msgs[:10]]
                if len(msgs) > 10:
                    out.append(f'  - ... and {len(msgs) - 10} more (see the JSON report)')
            fixes = list(dict.fromkeys(x['fix'] for x in xs if x['fix']))
            if len(fixes) == 1:
                out.append(f'  - Fix: {fixes[0]}')
        out.append('')
    if f.get('files'):
        out += ['## Reading order', ''] + [f'{n}. {p}' for n, p in enumerate(f['files'], 1)] + ['']
    if f.get('suggested_config'):
        out += ['## Suggested mdbindery.yaml', '', '```yaml', f['suggested_config'].rstrip(), '```', '']
    return '\n'.join(out)


def to_json(rep):
    return json.dumps({'target': rep.target, 'ok': rep.ok,
                       'counts': {s: rep.count(s) for s in SEVERITIES},
                       'by_code': [{'code': c, 'severity': s, 'count': n} for (c, s), n in code_summary(rep)],
                       'facts': rep.facts, 'findings': rep.findings}, indent=2, ensure_ascii=False)
