"""Configuration: load mdbindery.yaml, apply defaults, or infer a config from a repository."""
import copy
import datetime
import difflib
import math
import posixpath
import re
import subprocess
from collections import Counter
from pathlib import Path
from urllib.parse import unquote

import yaml

CONFIG_NAMES = ('mdbindery.yaml', 'mdbindery.yml')

DEFAULTS = {
    'slug': '',
    'source_dir': '.',
    'output_dir': 'dist',
    'source_url': '',
    'metadata': {
        'title': '', 'subtitle': '', 'authors': [], 'lang': 'en-US', 'identifier': '',
        'date': 'git', 'rights': '', 'publisher': '', 'description': '', 'subjects': [],
        'series': '', 'series_position': '',
    },
    'cover': {'image': '', 'embed_height': 1000, 'background': '#1d2330',
              'foreground': '#f2efe6', 'accent': '#c8643b'},
    'files': [],
    'options': {
        'citations': 'refdefs', 'citation_labels': 'numeric',
        'reference_headings': ['References', 'Sources', 'Notes', 'Bibliography', 'Works cited',
                               'Литература', 'Источники', 'Примечания', 'Список литературы'],
        'reference_heading_new': 'References',
        'drop_lines': [],
        'toc': True, 'toc_depth': 2, 'split_level': 1,
        'mermaid': 'png', 'mermaid_scale': 2, 'mermaid_alt_prefix': 'Chart', 'mermaid_today_marker': False,
        'mermaid_theme': 'neutral', 'mermaid_font_size': 18,
        'cards': {'files': [], 'min_columns': 9, 'title_columns': 1},
        'wide_table_warn': 9,
        'css': '', 'extra_css': '', 'embed_fonts': [],
        'highlight_style': 'monochrome',
        'strict_links': True,
        'wordcount_tolerance': 0.02, 'wordcount_min_words': 25,
        'epubcheck': True, 'ace': True, 'ace_waivers': [],
        'accessibility_summary': '',
        'conformance_claim': '',
        'pdf': {'page_size': 'A4', 'margin_mm': 20, 'page_numbers': True},
    },
}

# the default accessibility summary: a base sentence and an ending chosen by what the book contains
DEFAULT_A11Y_SUMMARY = {
    'en': ('This publication has a navigable table of contents and a logical reading order; headings, '
           'lists, and tables are marked up structurally',
           {'all': ', and images carry text alternatives.', 'none': '.',
            'some': '; some images have no text alternative.'}),
    'ru': ('Публикация содержит оглавление и логический порядок чтения; заголовки, списки и таблицы '
           'размечены структурно',
           {'all': ', у изображений есть текстовые описания.', 'none': '.',
            'some': '; не у всех изображений есть текстовые описания.'}),
}


def default_summary(lang, has_images, all_alt):
    base, endings = DEFAULT_A11Y_SUMMARY.get(lang, DEFAULT_A11Y_SUMMARY['en'])
    return base + endings['none' if not has_images else 'all' if all_alt else 'some']


FILE_KEYS = {'file', 'role', 'title', 'drop_sections', 'mermaid_alt', 'key'}
SKIP_FILES = {'changelog', 'contributing', 'code_of_conduct', 'code-of-conduct', 'security', 'license',
              'licence', 'authors', 'support', 'governance', 'citation', 'funding', 'pull_request_template',
              'issue_template', 'maintainers', 'codeowners', 'summary', 'toc', 'contents', 'table-of-contents',
              'table_of_contents'}
TOC_FILES = ('SUMMARY.md', 'toc.md', 'TOC.md', 'contents.md', 'CONTENTS.md', 'table-of-contents.md')
IMAGE_DIRS = ('.', 'images', 'image', 'img', 'assets', 'media', 'figures', 'cover')
COVER_NAMES = ('cover.jpg', 'cover.jpeg', 'cover.png')
MERMAID_THEMES = ('default', 'neutral', 'dark', 'forest', 'base')

# unnumbered files named like front or back matter go before or after the chapters
FRONT_NAMES = ['title-page', 'titlepage', 'half-title', 'dedication', 'epigraph', 'foreword', 'preface',
               'prologue', 'introduction', 'intro', 'посвящение', 'предисловие', 'пролог', 'введение']
BACK_NAMES = ['afterword', 'epilogue', 'conclusion', 'glossary', 'bibliography', 'references',
              'acknowledgments', 'acknowledgements', 'about-the-author', 'about-the-authors', 'colophon',
              'index', 'послесловие', 'эпилог', 'заключение', 'глоссарий', 'библиография', 'благодарности']
LINK_RE = re.compile(r'\[[^\]]*\]\(\s*<?([^)>\s]+)>?(?:\s+"[^"]*")?\s*\)')


class ConfigError(Exception):
    pass


def deep_merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def did_you_mean(key, choices):
    m = difflib.get_close_matches(key, list(choices), n=1, cutoff=0.6)
    return f' (did you mean "{m[0]}"?)' if m else ''


def unknown_keys(user, base, prefix=''):
    """Keys in the user's config that mdbindery does not know (typos): [(dotted key, hint)]."""
    found = []
    for k, v in (user or {}).items():
        if k not in base:
            found.append((prefix + str(k), did_you_mean(str(k), base)))
        elif isinstance(v, dict) and isinstance(base[k], dict):
            found += unknown_keys(v, base[k], prefix + k + '.')
    return found


def natural_key(name):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', name)]


def first_heading(path):
    """Text of the first level-1 heading (ATX, setext, or HTML <h1>)."""
    from .markdown import headings
    try:
        lines = path.read_text(encoding='utf-8', errors='replace').split('\n')
    except OSError:
        return ''
    return next((t for _, lvl, t in headings(lines) if lvl == 1), '')


def norm_rel(path):
    """A file entry as a clean relative POSIX path, or None if it is absolute or leaves the folder."""
    p = str(path).replace('\\', '/')
    if p.startswith('/') or re.match(r'^[A-Za-z]:', p):
        return None
    p = posixpath.normpath(p)
    if p == '..' or p.startswith('../'):
        return None
    return p


def linked_files(md_path, src):
    """Local .md files linked from a Markdown file, in order of first appearance (relative to src)."""
    try:
        text = md_path.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return []
    from .markdown import iter_text_lines
    out = []
    for _, ln in iter_text_lines(text.split('\n')):
        for m in LINK_RE.finditer(ln):
            t = unquote(m.group(1).split('#')[0])
            if not t or re.match(r'^[a-zA-Z][\w+.-]*:', t) or not t.lower().endswith('.md'):
                continue
            p = (md_path.parent / t)
            try:
                rel = p.resolve().relative_to(src.resolve()).as_posix()
            except ValueError:
                continue
            if p.is_file() and rel not in out:
                out.append(rel)
    return out


def matter_group(stem):
    """0 front matter, 1 chapter, 2 appendix, 3 back matter (only for unnumbered file names)."""
    s = stem.lower()
    if s[:1].isdigit():
        return 1, 0
    if 'appendix' in s or 'приложение' in s or re.match(r'^app?[-_ ]?[a-h](?:$|[-_ .])', s):
        return 2, 0
    for i, n in enumerate(FRONT_NAMES):
        if s == n or s.startswith(n + '-') or s.startswith(n + '_'):
            return 0, i
    for i, n in enumerate(BACK_NAMES):
        if s == n or s.startswith(n + '-') or s.startswith(n + '_'):
            return 3, i
    return 1, 0


def discover_files(src, ok=lambda p: True):
    """Reading order when the config lists no files. Returns (files, how the order was found).

    ok(path) decides whether a file may be read (untrusted repositories: only inside the checkout).
    """
    base = src / 'chapters' if (src / 'chapters').is_dir() else src
    readme = next((p for p in src.glob('*') if p.is_file() and p.name.lower() == 'readme.md' and ok(p)), None)
    mds = [p for p in base.glob('*.md') if p.is_file() and ok(p)]
    body = [p for p in mds if p.name.lower() != 'readme.md' and p.stem.lower() not in SKIP_FILES]
    rels = {p.relative_to(src).as_posix(): p for p in body}

    ordered, how = None, 'file names'
    for toc in TOC_FILES:
        t = src / toc
        if t.is_file() and ok(t):
            links = [r for r in linked_files(t, src) if r.lower() != 'readme.md' or toc == 'SUMMARY.md']
            if len(links) >= (1 if toc == 'SUMMARY.md' else 2):
                ordered, how = links, toc
                break
    chapters = [r for r in rels if matter_group(Path(r).stem)[0] == 1]
    numbered = len(chapters) >= 2 and all(Path(r).name[:1].isdigit() for r in chapters)
    if ordered is None and readme and not numbered:  # numbered file names already say the order
        links = [r for r in linked_files(readme, src) if r in rels]
        if len(links) >= 2 and len(links) * 2 >= len(rels):
            ordered, how = links, 'links in ' + readme.name
    rest = sorted((r for r in rels if not ordered or r not in ordered),
                  key=lambda r: (matter_group(Path(r).stem), natural_key(Path(r).name)))
    if how == 'SUMMARY.md':
        rest = []  # mdBook: files missing from SUMMARY.md are not part of the book
    files = []
    if readme and how != 'SUMMARY.md' and not (ordered and readme.name in ordered):  # mdBook lists its README
        files.append({'file': readme.name, 'role': 'front'})
    for r in (ordered or []) + rest:
        g = matter_group(Path(r).stem)[0] if not (ordered and r in ordered) else 1
        files.append({'file': r, 'role': {0: 'front', 2: 'appendix', 3: 'back'}.get(g, 'chapter')})
    if ordered and rest:
        how += ' (then file names)'
    return files, how


def read_book_toml(path):
    """title, authors, language, src from an mdBook book.toml (a small subset of TOML)."""
    try:
        text = path.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return {}
    try:
        import tomllib
        data = tomllib.loads(text).get('book', {})
        return {k: data[k] for k in ('title', 'authors', 'language', 'src', 'description') if k in data}
    except Exception:  # Python < 3.11 or invalid TOML: read the simple keys
        out, section = {}, ''
        for ln in text.split('\n'):
            s = ln.strip()
            if s.startswith('['):
                section = s.strip('[] ')
                continue
            m = re.match(r'^(title|language|src|description)\s*=\s*"([^"]*)"', s)
            if m and section == 'book':
                out[m.group(1)] = m.group(2)
            m = re.match(r'^authors\s*=\s*\[(.*)\]', s)
            if m and section == 'book':
                out['authors'] = re.findall(r'"([^"]*)"', m.group(1))
        return out


def find_cover(src, ok=lambda p: True):
    for d in IMAGE_DIRS:
        for n in COVER_NAMES:
            p = src / d / n
            if p.is_file() and ok(p):
                return str(p.relative_to(src)).replace('\\', '/')
    return ''


def license_name(t):
    m = re.search(r'SPDX-License-Identifier:\s*([\w.+-]+)', t)
    if m:
        spdx = m.group(1)
        cc = re.match(r'^CC-(BY(?:-(?:NC|ND|SA))*)-(\d\.\d)$', spdx)
        if cc:
            return f'CC {cc.group(1)} {cc.group(2)}'
        return 'CC0 1.0' if spdx == 'CC0-1.0' else spdx
    v = re.search(r'(?:International|Unported|Generic)?\s*(?:Public License\s*)?\b(\d\.\d)\b', t)
    ver = v.group(1) if v else '4.0'
    for pat, label in ((r'Attribution[- ]NonCommercial[- ]ShareAlike', 'CC BY-NC-SA'),
                       (r'Attribution[- ]NonCommercial[- ]NoDerivatives|Attribution[- ]NonCommercial[- ]NoDerivs',
                        'CC BY-NC-ND'),
                       (r'Attribution[- ]NonCommercial', 'CC BY-NC'),
                       (r'Attribution[- ]NoDerivatives|Attribution[- ]NoDerivs', 'CC BY-ND'),
                       (r'Attribution[- ]ShareAlike', 'CC BY-SA'),
                       (r'Creative Commons Attribution \d\.\d', 'CC BY')):
        if re.search(pat, t, re.I):
            return f'{label} {ver}'
    for pat, label in ((r'CC0|Creative Commons Zero', 'CC0 1.0'),
                       (r'GNU LESSER GENERAL PUBLIC LICENSE', 'GNU LGPL'),
                       (r'GNU AFFERO GENERAL PUBLIC LICENSE', 'GNU AGPL'),
                       (r'GNU Free Documentation License', 'GNU FDL'),
                       (r'GNU GENERAL PUBLIC LICENSE', 'GNU GPL'),
                       (r'MIT License|Permission is hereby granted, free of charge', 'MIT License'),
                       (r'Apache License\s*,?\s*Version 2\.0', 'Apache License 2.0'),
                       (r'BSD \d-Clause|Redistribution and use in source and binary forms', 'BSD License'),
                       (r'Mozilla Public License,? v(?:ersion)?\.? ?2\.0', 'MPL 2.0'),
                       (r'The Unlicense|This is free and unencumbered software', 'The Unlicense')):
        if re.search(pat, t[:600] if label.startswith('GNU') else t, re.I):
            return label
    return ''


def detect_rights(*folders, ok=lambda p: True):
    for src in folders:
        for name in ('LICENSE', 'LICENSE.md', 'LICENSE.txt', 'LICENCE', 'LICENCE.md', 'COPYING', 'COPYING.md'):
            p = src / name
            if p.is_file() and ok(p):
                label = license_name(p.read_text(encoding='utf-8', errors='replace')[:6000])
                if label:
                    return label
    return ''


def guess_lang(src, files):
    sample = ''
    for f in files[:3]:
        try:
            sample += (src / f['file']).read_text(encoding='utf-8', errors='replace')[:4000]
        except OSError:
            pass
    letters = re.findall(r'[^\W\d_]', sample)
    if not letters:
        return 'en-US'
    cyr = sum(1 for c in letters if 'Ѐ' <= c <= 'ӿ')
    return 'ru' if cyr / len(letters) > 0.3 else 'en-US'


def slugify(s):
    return re.sub(r'[\W_]+', '-', s.lower()).strip('-') or 'book'


def _git(folder, *args):
    try:
        r = subprocess.run(['git', '-C', str(folder), *args], capture_output=True, text=True, timeout=20)
        return r.stdout.strip() if r.returncode == 0 else ''
    except (OSError, subprocess.SubprocessError):
        return ''


def github_of(url):
    """'owner/repo' for a GitHub URL (https, git@, or a blob/tree URL), else ''."""
    m = re.match(r'^(?:https?://(?:www\.)?github\.com/|git@github\.com:|ssh://git@github\.com/)([^/\s]+)/([^/\s#?]+?)'
                 r'(?:\.git)?(?:[/#?].*)?$', url or '')
    return f'{m.group(1)}/{m.group(2)}' if m else ''


def git_facts(source):
    """Repository root, GitHub owner/repo, and branch for a folder inside a git checkout."""
    top = _git(source, 'rev-parse', '--show-toplevel')
    if not top:
        return None, '', ''
    return Path(top).resolve(), github_of(_git(source, 'remote', 'get-url', 'origin')), \
        _git(source, 'rev-parse', '--abbrev-ref', 'HEAD')


class Config:
    def __init__(self, data, path, base, source, inferred, warnings, user=None):
        self.data = data            # merged dict
        self.path = path            # config file or None
        self.base = base            # folder paths are relative to
        self.source = source        # book source folder
        self.inferred = inferred    # list of inferred fields
        self.warnings = warnings
        self.user = user or {}      # the config file as written
        self.repo_root = source     # repository root ("/" in links and images)
        self.trusted = True         # False for repositories fetched by `check`: paths must stay inside
        self.github = ''            # owner/repo when known
        self.suggested_source_url = ''
        self.order_source = ''      # how the reading order was found, when inferred
        self.mdbook = False

    def __getitem__(self, k):
        return self.data[k]

    @property
    def opts(self):
        return self.data['options']

    @property
    def meta(self):
        return self.data['metadata']


def _str(value, name):
    if value is None:
        return ''
    if isinstance(value, bool):
        raise ConfigError(f'{name} must be text, not {str(value).lower()} (put it in quotes)')
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    if not isinstance(value, str):
        raise ConfigError(f'{name} must be text')
    return value


def _num(value, name, kind=int, lo=None, hi=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        try:
            value = float(str(value))
        except (TypeError, ValueError):
            raise ConfigError(f'{name} must be a number, not {value!r}')
    if not math.isfinite(value):
        raise ConfigError(f'{name} must be a finite number, not {value}')
    if kind is int and value != int(value):
        raise ConfigError(f'{name} must be a whole number')
    value = kind(value)
    if (lo is not None and value < lo) or (hi is not None and value > hi):
        raise ConfigError(f'{name} must be between {lo} and {hi}')
    return value


def valid_date(text):
    """YYYY, YYYY-MM, or YYYY-MM-DD, and a real calendar date."""
    for fmt, pattern in (('%Y-%m-%d', r'\d{4}-\d{2}-\d{2}'), ('%Y-%m', r'\d{4}-\d{2}'), ('%Y', r'\d{4}')):
        if re.fullmatch(pattern, text):
            try:
                datetime.datetime.strptime(text, fmt)
                return True
            except ValueError:
                return False
    return False


def _bool(value, name):
    if not isinstance(value, bool):
        raise ConfigError(f'{name} must be true or false')
    return value


def _str_list(value, name):
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list):
        raise ConfigError(f'{name} must be a list')
    return [_str(v, f'{name} entries') for v in value]


def validate(data):
    """Check and normalize value types; raises ConfigError with the key name."""
    for key in ('metadata', 'cover', 'options'):
        if not isinstance(data.get(key), dict):
            raise ConfigError(f'{key} must be a mapping of keys to values')
    md, cov, o = data['metadata'], data['cover'], data['options']
    for k in ('title', 'subtitle', 'rights', 'publisher', 'description', 'series', 'series_position', 'identifier'):
        md[k] = _str(md.get(k), f'metadata.{k}').strip()
    if isinstance(md.get('lang'), bool):
        raise ConfigError("metadata.lang must be a language code in quotes, e.g. lang: 'no' (YAML reads no as false)")
    md['lang'] = _str(md.get('lang'), 'metadata.lang').strip() or 'en-US'
    if isinstance(md.get('date'), datetime.datetime):
        md['date'] = md['date'].date()
    md['date'] = _str(md.get('date'), 'metadata.date').strip() or 'git'
    if md['date'] != 'git' and not valid_date(md['date']):
        raise ConfigError("metadata.date must be 'git' or a real date like 2026-09-26 (or 2026-09, or 2026)")
    md['authors'] = _str_list(md.get('authors') or [], 'metadata.authors')
    md['subjects'] = _str_list(md.get('subjects') or [], 'metadata.subjects')
    for k in ('slug', 'source_url', 'output_dir', 'source_dir'):
        data[k] = _str(data.get(k), k).strip()
    if data['slug'] and (not re.fullmatch(r'\w[\w.-]*', data['slug']) or '..' in data['slug']):
        raise ConfigError('slug may use letters, digits, dots, hyphens, and underscores only (it names the EPUB file)')
    if data['source_url']:
        if not re.match(r'^https?://', data['source_url']):
            raise ConfigError('source_url must start with https://')
        if not data['source_url'].endswith('/'):
            data['source_url'] += '/'
    cov['image'] = _str(cov.get('image'), 'cover.image')
    cov['embed_height'] = _num(cov.get('embed_height'), 'cover.embed_height', int, 200, 10000)
    for k in ('background', 'foreground', 'accent'):
        cov[k] = _str(cov.get(k), f'cover.{k}')
        if not re.fullmatch(r'#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?', cov[k]):
            raise ConfigError(f'cover.{k} must be a color like #1d2330')

    if not isinstance(o.get('pdf'), dict):
        raise ConfigError('options.pdf must be a mapping (page_size, margin_mm, page_numbers)')
    pdf = o['pdf']
    if pdf.get('page_size') not in ('A4', 'Letter'):
        raise ConfigError('options.pdf.page_size must be A4 or Letter')
    pdf['margin_mm'] = _num(pdf.get('margin_mm'), 'options.pdf.margin_mm', float, 10, 40)
    pdf['page_numbers'] = _bool(pdf.get('page_numbers'), 'options.pdf.page_numbers')

    if not isinstance(o.get('cards'), dict):
        raise ConfigError('options.cards must be a mapping (files, min_columns, title_columns)')
    for k in ('drop_lines', 'embed_fonts', 'ace_waivers', 'reference_headings'):
        if not isinstance(o.get(k), list):
            raise ConfigError(f'options.{k} must be a list')
        o[k] = _str_list(o[k], f'options.{k}')
    for p in o['drop_lines']:
        try:
            re.compile(p)
        except re.error as e:
            raise ConfigError(f'options.drop_lines: invalid pattern {p!r}: {e}')
    if not isinstance(o['cards'].get('files') or [], list):
        raise ConfigError('options.cards.files must be a list of file names')
    o['cards']['files'] = [norm_rel(f) or f for f in _str_list(o['cards'].get('files') or [], 'options.cards.files')]
    o['cards']['min_columns'] = _num(o['cards'].get('min_columns'), 'options.cards.min_columns', int, 1, 100)
    o['cards']['title_columns'] = _num(o['cards'].get('title_columns'), 'options.cards.title_columns', int, 1, 20)
    for k, lo, hi in (('toc_depth', 1, 6), ('split_level', 1, 6), ('mermaid_font_size', 6, 72),
                      ('wide_table_warn', 2, 100), ('wordcount_min_words', 0, 100000)):
        o[k] = _num(o.get(k), f'options.{k}', int, lo, hi)
    o['mermaid_scale'] = _num(o.get('mermaid_scale'), 'options.mermaid_scale', float, 0.5, 8)
    o['wordcount_tolerance'] = _num(o.get('wordcount_tolerance'), 'options.wordcount_tolerance', float, 0, 1)
    for k in ('toc', 'strict_links', 'epubcheck', 'ace', 'mermaid_today_marker'):
        o[k] = _bool(o.get(k), f'options.{k}')
    for k in ('css', 'extra_css', 'reference_heading_new', 'mermaid_alt_prefix', 'accessibility_summary',
              'conformance_claim', 'highlight_style', 'mermaid_theme'):
        o[k] = _str(o.get(k), f'options.{k}')
    if o['highlight_style'] and not re.fullmatch(r'[\w-]+', o['highlight_style']):
        raise ConfigError('options.highlight_style must be a pandoc style name (e.g. monochrome, tango) or none')
    if o['mermaid_theme'] not in MERMAID_THEMES:
        raise ConfigError(f"options.mermaid_theme must be one of: {', '.join(MERMAID_THEMES)}")
    if o.get('citations') not in ('refdefs', 'none'):
        raise ConfigError("options.citations must be 'refdefs' or 'none'")
    if o.get('citation_labels') not in ('numeric', 'all'):
        raise ConfigError("options.citation_labels must be 'numeric' or 'all'")
    if o.get('mermaid') not in ('png', 'placeholder', 'keep'):
        raise ConfigError("options.mermaid must be 'png', 'placeholder', or 'keep'")


def contained(path, root):
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except ValueError:
        return False


def load(target=None, config_path=None, name_hint=None, trusted=True, repo_root=None, ignore_config=False):
    """Load the config for a book.

    target: the book's source folder, or a config file (None: the config's folder, else the current folder).
    config_path: explicit config file (overrides discovery).
    name_hint: fallback title when nothing better is found (e.g. the repository name).
    trusted: False for fetched repositories; then every path must stay inside repo_root.
    repo_root: repository root for "/" links (default: the git checkout that holds the book).
    ignore_config: infer everything, even if a config file exists (init --force over a broken file).
    """
    if target is None:
        target = Path(config_path).resolve() if config_path else Path.cwd()
    target = Path(target).resolve()
    # untrusted repositories: every file read must resolve (symlinks included) inside the checkout
    guard = Path(repo_root).resolve() if repo_root else (target if target.is_dir() else target.parent)
    ok = (lambda p: True) if trusted else (lambda p: contained(p, guard))
    path = None
    if config_path:
        path = Path(config_path).resolve()
    elif target.is_file():
        path = target
    elif not ignore_config:
        for n in CONFIG_NAMES:
            if (target / n).is_file():
                path = target / n
                break
    user = {}
    warnings, inferred = [], []
    if path:
        if not path.is_file():
            raise ConfigError(f'config file not found: {path}')
        if not ok(path):
            raise ConfigError(f'{path.name} points outside the repository')
        try:
            user = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
        except yaml.YAMLError as e:
            mark = getattr(e, 'problem_mark', None)
            where = f', line {mark.line + 1}, column {mark.column + 1}' if mark else ''
            raise ConfigError(f'invalid YAML in {path.name}{where}: {getattr(e, "problem", None) or e}')
        except UnicodeDecodeError:
            raise ConfigError(f'{path.name} is not UTF-8 text')
        if not isinstance(user, dict):
            raise ConfigError(f'{path.name} must contain a mapping of keys to values')
        for k, hint in unknown_keys(user, DEFAULTS):
            if '.' not in k:
                raise ConfigError(f'unknown top-level key "{k}"{hint}: its settings would be ignored')
            warnings.append(f'unknown config key: {k}{hint}')
        base = path.parent
        if user.get('source_dir'):
            source = (base / str(user['source_dir'])).resolve()
        elif target.is_dir():
            source = target      # book folder given on the command line
        else:
            source = base        # the config sits in the book folder
    else:
        base = target
        source = target
        inferred.append('config (no mdbindery.yaml found)')

    # mdBook: book.toml names the source folder, SUMMARY.md the reading order
    toml, book_root = {}, None
    if (source / 'book.toml').is_file() and ok(source / 'book.toml'):
        toml = read_book_toml(source / 'book.toml')
        src_dir = source / str(toml.get('src') or 'src')
        if (src_dir / 'SUMMARY.md').is_file():  # an mdBook needs its SUMMARY.md
            book_root = source
            source = src_dir.resolve()
            inferred.append('source_dir (book.toml)')
    elif (source / 'SUMMARY.md').is_file() and (source.parent / 'book.toml').is_file() \
            and ok(source.parent / 'book.toml'):
        toml, book_root = read_book_toml(source.parent / 'book.toml'), source.parent.resolve()
    if not source.is_dir():
        raise ConfigError(f'source folder not found: {source}')
    data = deep_merge(DEFAULTS, user)
    validate(data)
    data['source_dir'] = str(source)

    top, gh, branch = git_facts(source) if trusted else (None, '', '')
    if repo_root is None:
        # outside git, an mdBook's root is the book.toml folder (its includes reach ../listings)
        repo_root = top if top and contained(source, top) else (book_root or source)
    repo_root = Path(repo_root).resolve()
    if not trusted:
        if not contained(source, repo_root):
            raise ConfigError('source_dir must stay inside the repository')
        for k in ('css', 'extra_css'):
            if data['options'][k] and not contained(base / data['options'][k], repo_root):
                raise ConfigError(f'options.{k} must be a file inside the repository')
        for fnt in data['options']['embed_fonts']:
            if not contained(base / fnt, repo_root):
                raise ConfigError('options.embed_fonts must list files inside the repository')
        if data['cover']['image'] and not contained(base / data['cover']['image'], repo_root):
            raise ConfigError('cover.image must be a file inside the repository')
    for k in ('css', 'extra_css'):
        if data['options'][k] and not (base / data['options'][k]).is_file():
            raise ConfigError(f"options.{k}: file not found: {data['options'][k]}")
    for fnt in data['options']['embed_fonts']:
        if not (base / fnt).is_file():
            raise ConfigError(f'options.embed_fonts: file not found: {fnt}')

    # files
    files = data.get('files') or []
    if not isinstance(files, list):
        raise ConfigError('files must be a list')
    order_source = ''
    if not files:
        files, order_source = discover_files(source, ok)
        inferred.append('files (reading order)')
    norm = []
    for i, f in enumerate(files):
        f = f if isinstance(f, dict) else {'file': f}
        if not f.get('file'):
            raise ConfigError(f'files entry {i + 1} has no "file:" key')
        extra = set(f) - FILE_KEYS
        if extra:
            warnings.append(f"unknown keys for file {f.get('file')}: {sorted(extra)}"
                            + did_you_mean(sorted(extra)[0], FILE_KEYS))
        f = dict(f)
        rel = norm_rel(_str(f['file'], 'files entry'))
        if rel is None:
            raise ConfigError(f"files entry {f['file']}: use a path relative to the book folder "
                              '(no absolute paths, no ..; set source_dir instead)')
        if not ok(source / rel):
            raise ConfigError(f'files entry {rel} points outside the repository')
        f['file'] = rel
        f.setdefault('role', 'chapter')
        f.setdefault('key', f'k{i:02d}')
        f['key'] = str(f['key'])
        if not re.match(r'^[A-Za-z0-9_]+$', f['key']):
            raise ConfigError(f"files entry {f['file']}: key must use letters, digits, and underscores")
        if 'title' in f:
            f['title'] = _str(f['title'], f"title of {f['file']}")
        for k in ('drop_sections',):
            if k in f:
                f[k] = _str_list(f[k], f"{k} of {f['file']}")
        norm.append(f)
    keys = [f['key'] for f in norm]
    dup = sorted(k for k, n in Counter(keys).items() if n > 1)
    if dup:
        raise ConfigError(f'duplicate file keys: {dup}')
    names = [f['file'] for f in norm]
    dupn = sorted(k for k, n in Counter(names).items() if n > 1)
    if dupn:
        raise ConfigError(f'file listed twice in files: {dupn}')
    data['files'] = norm

    md = data['metadata']
    if not md.get('title') and toml.get('title'):
        md['title'] = str(toml['title'])
        inferred.append('metadata.title (book.toml)')
    if not md.get('title'):
        t = ''
        if norm:
            front = next((f for f in norm if f['file'].lower() == 'readme.md'), norm[0])
            t = first_heading(source / front['file'])
        md['title'] = t or name_hint or source.name
        inferred.append('metadata.title')
    if not md.get('authors') and toml.get('authors'):
        md['authors'] = [str(a) for a in toml['authors']]
    if not md.get('description') and toml.get('description'):
        md['description'] = str(toml['description'])
    if not md.get('rights'):
        r = detect_rights(*((source, repo_root) if repo_root != source else (source,)), ok=ok)
        if r:
            md['rights'] = r
            inferred.append('metadata.rights')
    if 'lang' not in (user.get('metadata') or {}):
        md['lang'] = str(toml.get('language') or '') or guess_lang(source, norm)
        inferred.append('metadata.lang')
    if not data['cover'].get('image'):
        c = find_cover(source, ok)
        if c:
            data['cover']['image'] = c
            data['cover']['_base'] = 'source'
            inferred.append('cover.image')
    if not data.get('slug'):
        data['slug'] = slugify(md['title'])
    # an empty accessibility_summary gets the default, written at build time to match the images
    data['options']['_summary_lang'] = (md.get('lang') or 'en').split('-')[0].lower()
    data['options']['_mdbook'] = book_root is not None  # SUMMARY.md alone (GitBook) orders files only

    cfg = Config(data, path, base, source, inferred, warnings, user)
    cfg.repo_root = repo_root
    cfg.trusted = trusted
    cfg.order_source = order_source
    cfg.mdbook = data['options']['_mdbook']
    cfg.github = github_of(data['source_url']) or gh
    if gh and branch and branch != 'HEAD':
        sub = source.relative_to(repo_root).as_posix() if contained(source, repo_root) else ''
        cfg.suggested_source_url = f'https://github.com/{gh}/blob/{branch}/' + (sub + '/' if sub not in ('', '.') else '')
    return cfg


def save_identifier(cfg, ident):
    """Write a generated identifier into the config file's empty 'identifier:' key, if any."""
    if not cfg.path:
        return False
    text = cfg.path.read_text(encoding='utf-8')
    new, n = re.subn(r'^(\s*identifier:)[ \t]*(?:""|\'\'|~|null)?[ \t]*(#.*)?$',
                     lambda m: f'{m.group(1)} {ident}' + (f'  {m.group(2)}' if m.group(2) else ''),
                     text, count=1, flags=re.M)
    if n:
        cfg.path.write_text(new, encoding='utf-8')
    return bool(n)


def _y(value):
    """A YAML scalar (JSON strings, numbers, and lists are valid YAML; no document markers)."""
    import json
    return json.dumps(value, ensure_ascii=False)


def starter_yaml(cfg):
    """A commented mdbindery.yaml for `mdbindery init`, filled from inference and any existing config."""
    md = cfg.meta
    user = cfg.user or {}
    umd = user.get('metadata') or {}
    source_url = cfg['source_url'] or cfg.suggested_source_url
    lines = ['# mdbindery configuration: https://github.com/sagol/mdbindery/blob/main/docs/configuration.md']
    if user.get('slug'):
        lines.append(f'slug: {_y(cfg["slug"])}')
    else:
        lines.append(f'slug: {_y(cfg["slug"])}         # names the EPUB file')
    if user.get('source_dir'):
        lines.append(f"source_dir: {_y(user['source_dir'])}")
    lines += [
        f"output_dir: {_y(cfg['output_dir'])}",
        '# online copy of the book folder: links to files outside the book point here',
        f"source_url: {_y(source_url)}",
        '',
        'metadata:',
        f'  title: {_y(md["title"])}',
        f'  subtitle: {_y(md.get("subtitle") or "")}',
        f'  authors: {_y(md.get("authors") or [])}          # ["First Last"]',
        f'  lang: {_y(md["lang"])}',
    ]
    if md.get('identifier'):
        lines.append(f'  identifier: {_y(md["identifier"])}   # permanent: keep it across editions of this book')
    else:
        lines += ['  # identifier: left empty, a permanent urn:uuid is written here on the first build',
                  '  identifier:']
    lines += [f'  date: {_y(md.get("date") or "git")}',
              f'  rights: {_y(md.get("rights") or "")}',
              f'  description: {_y(md.get("description") or "")}']
    for k in ('publisher', 'series', 'series_position'):
        if umd.get(k):
            lines.append(f'  {k}: {_y(md[k])}')
    if umd.get('subjects'):
        lines.append(f"  subjects: {_y(md['subjects'])}")
    lines += ['', 'cover:',
              f"  image: {_y(cfg['cover'].get('image') or '')}          # 1600x2560 JPEG recommended; empty = generated"]
    for k, v in (user.get('cover') or {}).items():
        if k != 'image':
            lines.append(f'  {k}: {_y(v)}')
    lines += ['', '# reading order' + (f' (found from {cfg.order_source})' if cfg.order_source else ''), 'files:']
    for i, f in enumerate(cfg['files']):
        extra = {k: v for k, v in f.items() if k not in ('file', 'key') and not (k == 'role' and v == 'chapter')}
        if f.get('key') and f['key'] != f'k{i:02d}':
            extra['key'] = f['key']  # a custom key names the chapter's anchors
        if not extra:
            lines.append(f'  - {_y(f["file"])}')
            continue
        lines.append(f'  - file: {_y(f["file"])}')
        for k, v in extra.items():
            lines.append(f'    {k}: {_y(v)}')
    opts = user.get('options')
    if isinstance(opts, dict) and opts:
        dumped = yaml.safe_dump({'options': opts}, allow_unicode=True, sort_keys=False, default_flow_style=False)
        lines += [''] + dumped.rstrip('\n').split('\n')
    else:
        lines += ['', 'options:', '  citations: refdefs', '  toc_depth: 2']
    return '\n'.join(lines) + '\n'
