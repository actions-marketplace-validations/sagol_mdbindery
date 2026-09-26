"""Build pipeline: analyze (pre-pass, per-file AST, link resolution) and build (EPUB + gates)."""
import datetime
import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid
import zipfile
from importlib import resources
from pathlib import Path

from . import config as config_mod
from . import tools
from .markdown import md_escape, prepass

DATA = Path(str(resources.files('mdbindery') / 'data'))
REPORT_FILES = ('build.json', 'build.log', 'epubcheck.json')  # what a build writes into reports/


class BuildError(Exception):
    pass


def run(cmd, env=None, check=True):
    """Run a command (never through a shell)."""
    try:
        r = subprocess.run([str(c) for c in cmd], env=env or tools.tool_env(), text=True,
                           capture_output=True, encoding='utf-8', errors='replace')
    except OSError as e:
        raise BuildError(f'cannot run {cmd[0]}: {e}')
    if check and r.returncode != 0:
        raise BuildError(f"command failed ({r.returncode}): {' '.join(map(str, cmd))}\n{r.stderr}{r.stdout}"[-4000:])
    return r


def git_epoch(src):
    try:
        r = subprocess.run(['git', '-C', str(src), 'log', '-1', '--format=%ct'], capture_output=True, text=True)
        return int(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else None
    except (OSError, ValueError):
        return None


def source_epoch(cfg):
    """Timestamp for reproducible output: last git commit, else the config's fixed date,
    else the newest source file."""
    e = git_epoch(cfg.source)
    if e:
        return e
    d = str(cfg.meta.get('date') or '')
    if re.match(r'^\d{4}-\d{2}-\d{2}$', d):
        return int(datetime.datetime.strptime(d, '%Y-%m-%d').replace(tzinfo=datetime.timezone.utc).timestamp())
    times = [(cfg.source / f['file']).stat().st_mtime for f in cfg['files'] if (cfg.source / f['file']).is_file()]
    return int(max(times)) if times else None


def load_report(path, list_keys):
    """Read a filter report; pandoc's JSON encoder writes empty Lua lists as {}."""
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    for k in list_keys:
        v = data.get(k)
        if v is None or v == {}:
            data[k] = []
    return data


def words(text):
    return len(re.findall(r"[^\W_][\w'’-]*", text))


def xhtml_text(s):
    s = re.sub(r'<head\b.*?</head>', ' ', s, flags=re.S | re.I)
    s = re.sub(r'<!--.*?-->', ' ', s, flags=re.S)
    s = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', s, flags=re.S | re.I)
    s = re.sub(r'<img\b[^>]*\balt="([^"]*)"[^>]*>', r' \1 ', s)  # pandoc's plain text keeps alt text too
    # not in pandoc's plain text: captions made from image titles, TeX copies of formulas
    s = re.sub(r'<figcaption\b.*?</figcaption>|<annotation\b.*?</annotation>', ' ', s, flags=re.S)
    s = re.sub(r'<[^>]+>', ' ', s)
    return re.sub(r'&[a-zA-Z#0-9]+;', ' ', s)


class Mermaid:
    """Renders Mermaid sources to PNG files in a work folder (or placeholders)."""

    def __init__(self, cfg, work, log):
        self.cfg, self.work, self.log = cfg, work, log
        self.cmd = tools.command('mmdc') if cfg.opts['mermaid'] == 'png' else None
        self.failures = []

    def _render(self, mmd, png, mcfg):
        return run(self.cmd + ['-q', '-i', mmd, '-o', png, '-b', 'white', '-c', mcfg,
                               '-s', str(float(self.cfg.opts['mermaid_scale'])), '-p', tools.puppeteer_config()],
                   check=False)

    def __call__(self, src, alt, source_link='', file=''):
        from .markdown import mermaid_hash
        h = mermaid_hash(src)
        img_dir = self.work / 'images'
        img_dir.mkdir(exist_ok=True)
        png = img_dir / f'mermaid-{h}.png'
        if self.cmd and not png.exists():
            mmd = self.work / f'mermaid-{h}.mmd'
            mmd.write_text(src, encoding='utf-8')
            mcfg = self.work / 'mermaid-config.json'
            if not mcfg.exists():
                mcfg.write_text(json.dumps({'theme': self.cfg.opts.get('mermaid_theme', 'neutral'),
                                            'themeVariables': {'fontSize': f"{self.cfg.opts.get('mermaid_font_size', 18)}px"}}),
                                encoding='utf-8')
            r = self._render(mmd, png, mcfg)
            if r.returncode != 0 and tools.sandbox_error(r.stderr + r.stdout):
                tools.disable_sandbox()  # remembered for later runs
                r = self._render(mmd, png, mcfg)
            if r.returncode != 0 or not png.exists():
                out = (r.stderr or '') + (r.stdout or '')
                lines = [l.strip() for l in out.splitlines() if l.strip()]
                msg = next((l for l in lines if 'Parse error' in l or l.startswith(('Error', 'error'))), None)
                i = lines.index(msg) if msg in lines else -1
                if msg and 'Parse error' in msg and i + 2 < len(lines):
                    msg = ' '.join(lines[i:i + 3])
                self.failures.append({'file': file, 'alt': alt, 'error': (msg or (lines[-1] if lines else 'unknown error'))[:300]})
        if png.exists():
            return [f'![{md_escape(alt)}](<{png.as_posix()}>)', '']
        note = f'> {md_escape(alt)}. This chart is available in the online edition'
        note += f': <{source_link}>' if source_link else '.'
        return [note, '']


def read_utf8(path, rel):
    try:
        return path.read_bytes().decode('utf-8')
    except UnicodeDecodeError as e:
        raise BuildError(f'{rel} is not valid UTF-8 (byte {e.start}); re-save it as UTF-8')


def site_links(cfg):
    """True when source_url is a website (not GitHub): files missing from the repository may exist there."""
    return bool(cfg['source_url']) and not config_mod.github_of(cfg['source_url'])


def analyze(cfg, work, log=print, skip_missing=False):
    """Pre-pass and pandoc per-file pass for every file, then link resolution.

    Returns dict with 'files' (per-file stats and reports), 'links', 'h1', 'linked' path.
    """
    pandoc = tools.find('pandoc')
    if not pandoc:
        raise BuildError('pandoc not found (or older than 3.8): run `mdbindery install-tools`')
    if not cfg['files']:
        raise BuildError('no Markdown files in the reading order (MB100): add chapters or list them under files:')
    lua = DATA / 'book.lua'
    src = cfg.source
    repo_root = Path(cfg.repo_root).resolve()
    files = cfg['files']
    file_map = {f['file']: f['key'] for f in files}
    card_files = set(cfg.opts['cards'].get('files') or [])
    mermaid = Mermaid(cfg, work, log)
    result = {'files': {}, 'h1': {}, 'mermaid_failures': mermaid.failures}
    root_prefix = os.path.relpath(repo_root, src.resolve()).replace('\\', '/')
    root_prefix = '' if root_prefix == '.' else root_prefix
    source_prefix = os.path.relpath(src.resolve(), repo_root).replace('\\', '/')
    source_prefix = '' if source_prefix == '.' or source_prefix.startswith('..') else source_prefix
    posix = lambda p: str(p).replace('\\', '/')
    common = {'files': file_map, 'source_url': cfg['source_url'], 'root_prefix': root_prefix,
              'source_prefix': source_prefix, 'github': cfg.github,
              'source_root': posix(src.resolve()), 'repo_root': posix(repo_root), 'work_dir': posix(work.resolve()),
              'image_root': '' if cfg.trusted else posix(repo_root),
              'card_min_columns': cfg.opts['cards'].get('min_columns', 9),
              'card_title_columns': cfg.opts['cards'].get('title_columns', 1),
              'wide_table_warn': cfg.opts['wide_table_warn']}
    asts = []
    for f in files:
        key = f['key']
        path = src / f['file']
        if not path.is_file():
            if skip_missing:
                continue
            raise BuildError(f"listed file not found: {f['file']}")
        raw = read_utf8(path, f['file']) if not skip_missing else path.read_text(encoding='utf-8', errors='replace')
        link = cfg['source_url'] + f['file'].replace(' ', '%20') if cfg['source_url'] else ''
        text, stats = prepass(raw, f, cfg.opts, lambda s, a, _f=f['file']: mermaid(s, a, link, _f),
                              base_dir=path.parent, root=repo_root)
        prepared = work / f'{key}.md'
        prepared.write_text(text, encoding='utf-8')
        rel_dir = posix(Path(f['file']).parent)
        ctx = dict(common, key=key, file=f['file'], file_dir=posix(path.parent.resolve()),
                   file_rel_dir='' if rel_dir == '.' else rel_dir, title=f.get('title', ''),
                   fallback_title=cfg.meta['title'] if f['file'].lower() == 'readme.md' else '',
                   cards=f['file'] in card_files, citations=stats.get('citations', []),
                   report=str(work / f'{key}.report.json'))
        (work / f'{key}.ctx.json').write_text(json.dumps(ctx), encoding='utf-8')
        env = tools.tool_env()
        env.update({'MDBINDERY_CTX': str(work / f'{key}.ctx.json'), 'MDBINDERY_PHASE': 'file'})
        run([pandoc, '-f', 'gfm', '-t', 'json', prepared, '-o', work / f'{key}.json', '--lua-filter', lua], env=env)
        rep = load_report(work / f'{key}.report.json',
                          ('ids', 'wide_tables', 'external', 'images', 'html_removed', 'cited', 'math'))
        cited = set(rep['cited'])
        stats['uncited'] = [c['label'] for c in stats.get('citations', []) if c['label'] not in cited]
        result['h1'][key] = rep['h1']
        asts.append(json.loads((work / f'{key}.json').read_text(encoding='utf-8')))
        result['files'][f['file']] = {'key': key, 'stats': stats, 'report': rep, 'prepared': str(prepared)}
    if not asts:
        raise BuildError('none of the files in the reading order exist')

    merged = {'pandoc-api-version': asts[0]['pandoc-api-version'], 'meta': {},
              'blocks': [b for x in asts for b in x['blocks']]}
    (work / 'merged.json').write_text(json.dumps(merged), encoding='utf-8')
    lctx = {'h1': result['h1'], 'report': str(work / 'links.report.json')}
    (work / 'links.ctx.json').write_text(json.dumps(lctx), encoding='utf-8')
    env = tools.tool_env()
    env.update({'MDBINDERY_CTX': str(work / 'links.ctx.json'), 'MDBINDERY_PHASE': 'links'})
    run([pandoc, '-f', 'json', '-t', 'json', work / 'merged.json', '-o', work / 'linked.json', '--lua-filter', lua],
        env=env)
    links = load_report(work / 'links.report.json', ('unresolved', 'fuzzy'))
    key_file = {f['key']: f['file'] for f in files}
    for u in links['unresolved'] + links['fuzzy']:
        u['file'] = key_file.get(u['key'], u['key'])
    result['links'] = links
    result['linked'] = str(work / 'linked.json')
    return result


def ensure_identifier(cfg, log):
    ident = cfg.meta.get('identifier')
    if ident:
        return str(ident)
    ident = f'urn:uuid:{uuid.uuid4()}'
    if config_mod.save_identifier(cfg, ident):
        log(f'  generated identifier {ident} (saved in {cfg.path.name})')
    else:
        log(f'  warning: generated identifier {ident} for this build only; add "identifier:" to the config '
            'metadata to keep it stable across builds')
    return ident


def make_covers(cfg, out_dir, work, slug):
    from PIL import Image, ImageOps, UnidentifiedImageError
    from .cover import make_cover
    cov = cfg['cover']
    store = out_dir / f'{slug}-cover.jpg'
    if cov.get('image'):
        base = cfg.source if cov.get('_base') == 'source' else cfg.base
        p = (base / cov['image']).resolve()
        if not p.is_file():
            raise BuildError(f'cover image not found: {p}')
        try:
            with Image.open(p) as src:
                im = ImageOps.exif_transpose(src)
                if im.mode in ('RGBA', 'LA', 'P'):
                    im = im.convert('RGBA')
                    white = Image.new('RGBA', im.size, (255, 255, 255, 255))
                    im = Image.alpha_composite(white, im)
                im.convert('RGB').save(store, 'JPEG', quality=92, optimize=True)
        except (UnidentifiedImageError, OSError) as e:
            raise BuildError(f'cover image cannot be read ({e}); save it again as JPEG')
    else:
        md = cfg.meta
        make_cover(store, md['title'], md.get('subtitle') or '', ', '.join(md.get('authors') or []),
                   bg=cov['background'], fg=cov['foreground'], accent=cov['accent'], lang=md.get('lang') or '')
    with Image.open(store) as im:
        eh = int(cov.get('embed_height') or im.height)
        if im.height > eh:
            im = im.resize((round(im.width * eh / im.height), eh), Image.LANCZOS)
        embed = work / 'cover.jpg'
        im.convert('RGB').save(embed, 'JPEG', quality=90, optimize=True)
    return store, embed


def meta_value(v):
    """A Python value as pandoc JSON metadata; strings stay literal (never parsed as Markdown)."""
    if isinstance(v, dict):
        return {'t': 'MetaMap', 'c': {k: meta_value(x) for k, x in v.items()}}
    if isinstance(v, list):
        return {'t': 'MetaList', 'c': [meta_value(x) for x in v]}
    if isinstance(v, bool):
        return {'t': 'MetaBool', 'c': v}
    return {'t': 'MetaString', 'c': str(v)}


def book_metadata(cfg, ident, date):
    md = cfg.meta
    title = [{'type': 'main', 'text': md['title']}]
    if md.get('subtitle'):
        title.append({'type': 'subtitle', 'text': md['subtitle']})
    meta = {'title': title, 'lang': md.get('lang') or 'en-US', 'date': str(date),
            'identifier': [{'scheme': 'UUID' if ident.startswith('urn:uuid:') else 'URI', 'text': ident}],
            'creator': [{'role': 'author', 'text': a} for a in (md.get('authors') or [])]}
    for k in ('rights', 'publisher', 'description'):
        if md.get(k):
            meta[k] = md[k]
    if md.get('subjects'):
        meta['subject'] = md['subjects']
    if md.get('series'):
        meta['belongs-to-collection'] = md['series']
        if md.get('series_position'):
            meta['group-position'] = md['series_position']
    return {k: meta_value(v) for k, v in meta.items()}


def write_css(cfg, work):
    o = cfg.opts
    css = Path(o['css']) if o['css'] else DATA / 'epub.css'
    if not css.is_absolute():
        css = cfg.base / css
    text = css.read_text(encoding='utf-8')
    if o['extra_css']:
        extra = Path(o['extra_css'])
        text += '\n' + (extra if extra.is_absolute() else cfg.base / extra).read_text(encoding='utf-8')
    p = work / 'book.css'
    p.write_text(text, encoding='utf-8')
    return p


NOTE_RE = re.compile(r'(<aside\b[^>]*\bepub:type="footnote"[^>]*\bid="fn(\d+)"[^>]*>\s*)(<p>)?')


def number_notes(xhtml):
    """Give each endnote its number, linked back to the note reference (pandoc's asides have none)."""
    def repl(m):
        back = f'<a href="#fnref{m.group(2)}" class="footnote-back" role="doc-backlink">{m.group(2)}.</a>'
        return m.group(1) + (f'<p>{back} ' if m.group(3) else f'<p class="footnote-number">{back}</p>')
    return NOTE_RE.sub(repl, xhtml)


def postprocess(src_epub, epub, cfg, has_images, epoch, all_alt=True):
    """Merge accessibility metadata into the OPF, number endnotes, and write a normalized zip."""
    opts = cfg.opts
    esc = lambda s: s.replace('&', '&amp;').replace('<', '&lt;')
    with zipfile.ZipFile(src_epub) as zin:
        names = zin.namelist()
        opf_name = next(n for n in names if n.endswith('.opf'))
        opf = zin.read(opf_name).decode('utf-8')
        wanted = [('schema:accessMode', 'textual'), ('schema:accessModeSufficient', 'textual'),
                  ('schema:accessibilityFeature', 'tableOfContents'),
                  ('schema:accessibilityFeature', 'readingOrder'),
                  ('schema:accessibilityFeature', 'structuralNavigation'),
                  ('schema:accessibilityHazard', 'none')]
        if has_images:
            wanted.append(('schema:accessMode', 'visual'))
        if has_images and all_alt:
            wanted.append(('schema:accessibilityFeature', 'alternativeText'))
        else:  # pandoc claims alternative text by default; only keep the claim when it is true
            opf = opf.replace('<meta property="schema:accessibilityFeature">alternativeText</meta>', '')
        if 'schema:accessibilitySummary' not in opf:
            wanted.append(('schema:accessibilitySummary', opts['accessibility_summary']))
        if opts.get('conformance_claim'):
            wanted.append(('dcterms:conformsTo', opts['conformance_claim']))
        add = ''.join(f'    <meta property="{p}">{esc(v)}</meta>\n' for p, v in wanted
                      if f'<meta property="{p}">{esc(v)}</meta>' not in opf)
        if add:
            opf = opf.replace('</metadata>', add + '  </metadata>', 1)
        opf = re.sub(r'\n\s*\n', '\n', opf)
        stamp = (1980, 1, 1, 0, 0, 0)
        if epoch:  # zip dates start in 1980
            stamp = max(stamp, datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc).timetuple()[:6])
        tmp = epub.with_name(epub.name + '.part')
        with zipfile.ZipFile(tmp, 'w') as zout:
            def zinfo(name, compress):
                zi = zipfile.ZipInfo(name, date_time=stamp)
                zi.compress_type = compress
                zi.create_system = 3  # same bytes on every OS
                zi.external_attr = 0o644 << 16
                return zi
            zout.writestr(zinfo('mimetype', zipfile.ZIP_STORED), zin.read('mimetype'))
            for n in names:
                if n == 'mimetype':
                    continue
                data = zin.read(n)
                if n == opf_name:
                    data = opf.encode('utf-8')
                elif n.endswith('.xhtml') and b'epub:type="footnote"' in data:
                    data = number_notes(data.decode('utf-8')).encode('utf-8')
                zout.writestr(zinfo(n, zipfile.ZIP_DEFLATED), data)
    tmp.replace(epub)


def collect_ace(report):
    fails = []

    def walk(node):
        if isinstance(node, dict):
            res, test = node.get('earl:result'), node.get('earl:test')
            if isinstance(res, dict) and res.get('earl:outcome') == 'fail' and isinstance(test, dict):
                fails.append((test.get('earl:impact', ''), test.get('dct:title', '')))
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(report)
    return fails


def gate_epubcheck(epub, reports, log, required=True):
    cmd = tools.epubcheck_cmd()
    if not cmd:
        if not required:
            return {'result': 'skipped'}
        log('  EPUBCheck: NOT RUN: Java 11+ or EPUBCheck missing (run `mdbindery install-tools`, '
            'or set options.epubcheck: false to build without validation)')
        return {'result': 'fail', 'detail': 'EPUBCheck not available'}
    rj = reports / 'epubcheck.json'
    if rj.exists():
        rj.unlink()
    r = run(cmd + [epub, '--json', rj, '-q'], check=False)
    try:
        data = json.loads(rj.read_text(encoding='utf-8'))
        if 'checker' not in data:
            raise ValueError('no checker section')
    except (OSError, ValueError) as e:
        detail = ((r.stderr or '') + (r.stdout or '')).strip()[-500:] or str(e)
        log(f'  EPUBCheck: FAILED to run (exit {r.returncode}): {detail}')
        return {'result': 'fail', 'detail': f'EPUBCheck did not produce a report: {detail}'}
    msgs = data.get('messages', [])
    sev = {}
    for m in msgs:
        sev[m['severity']] = sev.get(m['severity'], 0) + 1
    errors = sev.get('FATAL', 0) + sev.get('ERROR', 0)
    log(f"  EPUBCheck: {sev or 'no messages'}")
    details = []
    for m in msgs[:50]:
        loc = (m.get('locations') or [{}])[0]
        details.append({'severity': m['severity'], 'id': m['ID'], 'message': m['message'],
                        'path': loc.get('path', ''), 'line': loc.get('line', '')})
        log(f"    {m['severity']} {m['ID']}: {m['message'][:160]} [{loc.get('path', '')}:{loc.get('line', '')}]")
    return {'result': 'pass' if errors == 0 else 'fail', 'counts': sev, 'messages': details}


def gate_ace(epub, reports, cfg, log):
    ace = tools.command('ace')
    if not ace:
        log('  Ace: not run: not installed (tools were installed with --no-node); accessibility not checked. '
            'Run `mdbindery install-tools` to add it.')
        return {'result': 'warn', 'detail': 'Ace not installed'}
    ad = reports / 'ace'
    if ad.exists():
        shutil.rmtree(ad, ignore_errors=True)
    r = run(ace + ['-f', '-s', '-o', ad, epub], env=tools.ace_env(), check=False)
    rj = ad / 'report.json'
    if not rj.exists():
        detail = ((r.stderr or '') + (r.stdout or '')).strip()
        log(f'  Ace: FAILED to run: {detail[-300:]} (see docs/troubleshooting.md, or build with --no-ace)')
        return {'result': 'fail', 'detail': detail[-1000:]}
    fails = collect_ace(json.loads(rj.read_text(encoding='utf-8')))
    waived = set(cfg.opts['ace_waivers'])
    blocking = [x for x in fails if x[0] in ('critical', 'serious') and x[1] not in waived]
    by = {}
    for imp, rule in fails:
        by[(imp, rule)] = by.get((imp, rule), 0) + 1
    log(f'  Ace: {len(fails)} violation(s), {len(blocking)} blocking')
    for (imp, rule), n in sorted(by.items()):
        log(f'    {imp} {rule} x{n}' + (' (waived)' if rule in waived else ''))
    return {'result': 'pass' if not blocking else 'fail',
            'violations': [{'impact': k[0], 'rule': k[1], 'count': v} for k, v in by.items()]}


def source_words(pandoc, prepared):
    """Words in a prepared file as a reader sees them: raw HTML as its text, tags and comments removed."""
    plain = run([pandoc, '-f', 'gfm', '-t', 'plain', '--wrap=none', prepared,
                 '--lua-filter', DATA / 'plaintext.lua']).stdout
    return words(re.sub(r'<https?://[^>]+>|https?://\S+', ' ', plain))


def gate_wordcount(epub, cfg, analysis, log):
    pandoc = tools.find('pandoc')
    card_files = set(cfg.opts['cards'].get('files') or [])
    with zipfile.ZipFile(epub) as z:
        names = z.namelist()
        opf_name = next(n for n in names if n.endswith('.opf'))
        opf = z.read(opf_name).decode('utf-8')
        base = opf_name.rsplit('/', 1)[0] + '/' if '/' in opf_name else ''
        manifest = dict(re.findall(r'<item id="([^"]+)" href="([^"]+)"', opf))
        spine = [manifest[i] for i in re.findall(r'<itemref idref="([^"]+)"', opf) if i in manifest]
        body = '\n'.join(re.sub(r'<head\b.*?</head>', ' ', z.read(base + h).decode('utf-8'), flags=re.S)
                         for h in spine if (base + h) in names)
    # split the reading order at each file's first heading
    marks = []
    for name, info in analysis['files'].items():
        pos = body.find(f'id="{analysis["h1"][info["key"]]}"')
        marks.append((pos, name))
    ordered = sorted(p for p in marks if p[0] >= 0)
    slices = {}
    for i, (pos, name) in enumerate(ordered):
        end = ordered[i + 1][0] if i + 1 < len(ordered) else len(body)
        start = body.rfind('<', 0, pos)
        end = body.rfind('<', 0, end) if i + 1 < len(ordered) else end
        slices[name] = body[start:end]
    tol, min_words = float(cfg.opts['wordcount_tolerance']), int(cfg.opts['wordcount_min_words'])
    wc, failing = {}, []
    for name, info in analysis['files'].items():
        n_src = source_words(pandoc, info['prepared'])
        seg = slices.get(name, '')
        n_out = words(re.sub(r'https?://\S+', ' ', xhtml_text(seg))) if seg else 0
        diff = (n_out - n_src) / n_src if n_src else (1.0 if n_out else 0.0)
        wc[name] = {'source': n_src, 'epub': n_out, 'diff': round(diff, 4)}
        if name not in card_files and abs(diff) > tol and abs(n_out - n_src) > min_words:
            failing.append(name)
    worst = max((abs(wc[n]['diff']) for n in failing), default=0.0)
    if failing:
        failing.sort(key=lambda n: -abs(wc[n]['diff']))
        shown = '; '.join(f"{n} {wc[n]['source']} -> {wc[n]['epub']} words ({wc[n]['diff']:+.1%})"
                          for n in failing[:5])
        more = f' and {len(failing) - 5} more' if len(failing) > 5 else ''
        log(f'  word count: FAILED: text lost or added in conversion (limit {tol:.0%} and {min_words} words): '
            f'{shown}{more}')
    else:
        big = max(((abs(v['diff']), k) for k, v in wc.items()
                   if k not in card_files and abs(v['epub'] - v['source']) > min_words), default=None)
        note = f'; largest difference {big[0]:.1%} in {big[1]}' if big else ''
        log(f'  word count: no text lost or duplicated{note}')
    return {'result': 'fail' if failing else 'pass', 'worst': round(worst, 4), 'failing': failing, 'files': wc}


def clear_reports(reports):
    """Remove what an earlier build wrote (and nothing else)."""
    for n in REPORT_FILES:
        p = reports / n
        if p.is_file():
            p.unlink()
    if (reports / 'ace').is_dir():
        shutil.rmtree(reports / 'ace', ignore_errors=True)


def build(cfg, out_dir=None, run_ace=True, keep_work=False, log=print):
    """Build the EPUB. Returns a summary dict; summary['ok'] is True when every gate passed."""
    opts = cfg.opts
    if not cfg['files']:
        raise BuildError('no Markdown files in the reading order (MB100): add chapters or list them under files:')
    pandoc = tools.find('pandoc')
    if not pandoc:
        raise BuildError('pandoc not found (or older than 3.8): run `mdbindery install-tools`')
    out_dir = Path(out_dir) if out_dir else (cfg.base / cfg['output_dir'])
    out_dir = out_dir.resolve()
    if out_dir.exists() and not out_dir.is_dir():
        raise BuildError(f'output folder is a file: {out_dir}')
    slug = cfg['slug']
    epub = (out_dir / f'{slug}.epub').resolve()
    if epub.parent != out_dir:
        raise BuildError(f'slug must be a plain file name: {slug!r}')
    reports = out_dir / 'reports'
    reports.mkdir(parents=True, exist_ok=True)
    clear_reports(reports)  # stale reports from an earlier build would mislead
    work = Path(tempfile.mkdtemp(prefix='mdbindery-'))
    n = len(cfg['files'])
    log(f"mdbindery: {slug} ({n} file{'s' if n != 1 else ''}) from {cfg.source}")
    for w in cfg.warnings:
        log(f'  config warning: {w}')
    summary = {'gates': {}, 'files': {}}
    try:
        epoch = source_epoch(cfg)
        a = analyze(cfg, work, log)
        ident = ensure_identifier(cfg, log)
        date = cfg.meta.get('date') or 'git'
        if date == 'git':
            date = (datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc).date().isoformat()
                    if epoch else datetime.date.today().isoformat())

        has_images = False
        all_alt = True
        img_problems, include_problems = [], []
        card_files = set(opts['cards'].get('files') or [])
        for name, info in a['files'].items():
            st, rep = info['stats'], info['report']
            imgs = rep.get('images', [])
            has_images |= any(i['status'] == 'ok' for i in imgs)  # rendered charts are images here too
            all_alt &= all(i.get('alt') for i in imgs)
            img_problems += [dict(i, file=name) for i in imgs if i['status'] != 'ok']
            include_problems += [{'file': name, 'directive': d, 'error': e} for d, e in st.get('include_errors', [])]
            extra = []
            if st.get('includes'):
                extra.append(f"{st['includes']} include(s) expanded")
            if st.get('references'):
                extra.append(f"{st['references']} refs")
            if st.get('uncited'):
                extra.append(f"uncited {st['uncited']}")
            if st.get('mermaid'):
                extra.append(f"{st['mermaid']} chart(s)")
            if imgs:
                extra.append(f"{len(imgs)} image(s)")
            local = [i['local_copy'] for i in imgs if i.get('local_copy') and i['status'] == 'ok']
            if local:
                extra.append(f'{len(local)} image URL(s) of this repository replaced by the local file')
            if rep.get('html_links'):
                extra.append(f"{rep['html_links']} .html link(s) resolved to .md files")
            if rep.get('wide_tables') and name not in card_files:
                extra.append(f"wide tables {rep['wide_tables']} cols")
            if name in card_files:
                extra.append('tables as cards')
            if st.get('dropped_sections'):
                extra.append(f"dropped {st['dropped_sections']}")
            if rep.get('html_removed'):
                extra.append('HTML removed: ' + ', '.join(f"<{x['tag']}>x{x['count']}" for x in rep['html_removed']))
            if rep.get('h1_fix'):
                extra.append({'title': 'title from config', 'promoted': 'first heading promoted to level 1',
                              'filename': 'title made from the file name'}[rep['h1_fix']])
            if rep.get('moved_before_h1'):
                extra.append(f"{rep['moved_before_h1']} block(s) above the title moved below it")
            unlinked = [e['path'] for e in rep.get('external', []) if e.get('mode') == 'unlinked' and e.get('exists')]
            if unlinked:
                extra.append(f'links to files outside the book kept as text (no source_url): {sorted(set(unlinked))}')
            log(f"  {info['key']} {name}: " + (', '.join(extra) or 'ok'))
            summary['files'][name] = {'stats': st, 'images': imgs, 'html_removed': rep.get('html_removed'),
                                      'external_links': rep.get('external'), 'math': rep.get('math')}
        for m in a['mermaid_failures']:
            log(f"  CHART in {m['file']} failed to render (placeholder used): {m['error']}")
        charts = sum(info['stats'].get('mermaid', 0) for info in a['files'].values())
        if a['mermaid_failures']:
            summary['gates']['charts'] = {'result': 'fail', 'failures': a['mermaid_failures']}
        elif charts and opts['mermaid'] == 'png' and not tools.command('mmdc'):
            log(f'  warning: {charts} chart(s) became placeholders: mermaid-cli is not installed '
                '(run `mdbindery install-tools`, or set options.mermaid: placeholder)')
            summary['gates']['charts'] = {'result': 'warn', 'placeholders': charts}
        else:
            summary['gates']['charts'] = {'result': 'pass', 'charts': charts}
        links = a['links']
        key_file = {f['key']: f['file'] for f in cfg['files']}
        for fz in links['fuzzy']:
            log(f"  link in {key_file.get(fz.get('source'), '?')} to {fz['file']}#{fz['fragment']} "
                f"matched approximately (anchor is #{fz['to'].split('-', 1)[1]})")
        for u in links['unresolved']:
            log(f"  UNRESOLVED link in {key_file.get(u.get('source'), '?')} to {u['file']}#{u['fragment']} "
                f"(text: {u['text']})")
        missing_files, web_only = [], []
        for name, info in a['files'].items():
            for e in info['report'].get('external', []):
                if not e.get('exists', True):
                    (web_only if site_links(cfg) and e.get('mode') == 'source_url' else missing_files).append(
                        dict(e, file=name))
        for m in missing_files:
            log(f"  LINK to a missing file in {m['file']}: {m['path']}")
        if web_only:
            log(f'  {len(web_only)} link(s) to pages that are not in the repository kept as web links '
                f"(not checked): {sorted({m['path'] for m in web_only})[:5]}")
        for p in include_problems:
            log(f"  INCLUDE in {p['file']} not expanded ({p['error']}): {p['directive']}")
        summary['links'] = links
        bad = links['unresolved'] or missing_files
        summary['gates']['links'] = {'result': 'pass' if not bad else ('fail' if opts['strict_links'] else 'warn'),
                                     'unresolved': len(links['unresolved']), 'missing_files': len(missing_files)}
        for p in img_problems:
            log(f"  IMAGE {p['status']}: {p['src']} in {p['file']}")
        summary['gates']['images'] = {'result': 'fail' if img_problems else 'pass', 'problems': img_problems}
        if include_problems:
            summary['gates']['includes'] = {'result': 'fail', 'problems': include_problems}

        store_cover, embed_cover = make_covers(cfg, out_dir, work, slug)
        css = write_css(cfg, work)
        linked = json.loads(Path(a['linked']).read_text(encoding='utf-8'))
        linked['meta'] = book_metadata(cfg, ident, date)  # literal strings: titles are not Markdown
        book_json = work / 'book.json'
        book_json.write_text(json.dumps(linked), encoding='utf-8')
        raw_epub = work / 'book.epub'
        cmd = [pandoc, '-f', 'json', '-t', 'epub3', book_json, '-o', raw_epub,
               '--css', css, '--epub-cover-image', embed_cover, '--split-level', str(opts['split_level']),
               '--toc-depth', str(opts['toc_depth']),
               f'--resource-path={os.pathsep.join([str(work), str(cfg.source)])}']
        if opts['toc']:
            cmd.append('--toc')
        # monochrome by default: readable on e-ink and passes contrast checks
        cmd.append(f"--syntax-highlighting={opts.get('highlight_style') or 'none'}")
        for fnt in opts['embed_fonts']:
            fp = Path(fnt)
            cmd += ['--epub-embed-font', str(fp if fp.is_absolute() else cfg.base / fp)]
        env = tools.tool_env()
        if epoch:
            env['SOURCE_DATE_EPOCH'] = str(max(epoch, 315532800))  # zip dates start in 1980
        r = run(cmd, env=env)
        warnings = [line.strip() for line in (r.stderr or '').splitlines() if line.strip()]
        for line in warnings:
            log(f'  pandoc: {line}')
        summary['pandoc_warnings'] = warnings
        postprocess(raw_epub, epub, cfg, has_images, epoch, all_alt)
        log(f'  built {epub} ({epub.stat().st_size // 1024} KB)')

        if opts.get('epubcheck', True):
            summary['gates']['epubcheck'] = gate_epubcheck(epub, reports, log)
        else:
            log('  EPUBCheck: skipped (options.epubcheck: false)')
            summary['gates']['epubcheck'] = {'result': 'skipped'}
        if run_ace and opts['ace']:
            summary['gates']['ace'] = gate_ace(epub, reports, cfg, log)
        else:
            summary['gates']['ace'] = {'result': 'skipped'}
        summary['gates']['wordcount'] = gate_wordcount(epub, cfg, a, log)
        summary['epub'] = str(epub)
        summary['cover'] = str(store_cover)
    finally:
        if keep_work:
            log(f'  work folder kept: {work}')
        else:
            shutil.rmtree(work, ignore_errors=True)
    failed = [k for k, v in summary['gates'].items() if v.get('result') == 'fail']
    summary['ok'] = not failed
    summary['failed_gates'] = failed
    (reports / 'build.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding='utf-8')
    log('BUILD OK' if not failed else f"BUILD FAILED: {', '.join(failed)} (details: {reports / 'build.json'})")
    return summary
