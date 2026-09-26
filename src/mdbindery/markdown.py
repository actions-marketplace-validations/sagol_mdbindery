"""Code-aware Markdown pre-pass: sections, lines, reference definitions, citations, includes, Mermaid."""
import hashlib
import re
from pathlib import Path

# fences may sit inside list items (indented) and block quotes (">" prefixes)
FENCE_RE = re.compile(r'^((?:[ \t]*>)*[ \t]*)(`{3,}|~{3,})(.*)$')
DEF_RE = re.compile(r'^(?:[ \t]*>)*[ \t]{0,3}\[([^\]\n^][^\]\n]*)\]:\s+<?(\S+?)>?(?:\s+(?:"(.*)"|\'(.*)\'|\((.*)\)))?\s*$')
HEADING_RE = re.compile(r'^ {0,3}(#{1,6})(?:[ \t]+(.*?))?(?:[ \t]+#+)?[ \t]*$')
URL_RE = re.compile(r'https?://[^\s<>")\]]+')
LIST_RE = re.compile(r'^ {0,3}([-*+]|\d{1,9}[.)])(\s|$)')
INCLUDE_RE = re.compile(r'(\\?)\{\{#(include|rustdoc_include|playground|title)\s+([^}]*?)\s*\}\}')
ANCHOR_LINE_RE = re.compile(r'ANCHOR(?:_END)?:\s*[\w-]+')


def md_escape(s):
    return re.sub(r'([\\`*_\[\]<>#|])', r'\\\1', s)


def title_markdown(title):
    """Escape a reference title for Markdown, keeping bare URLs as clean autolinks."""
    out, pos = [], 0
    for m in URL_RE.finditer(title):
        out.append(md_escape(title[pos:m.start()]))
        out.append(f'<{m.group(0)}>')
        pos = m.end()
    out.append(md_escape(title[pos:]))
    return ''.join(out)


def label_ids(labels):
    """Anchor ids for citation labels: ref-1 for [1], a Unicode slug for words; unique within the file."""
    ids, used = {}, set()
    for label in labels:
        base = 'ref-' + (re.sub(r'[\W_]+', '-', label.lower()).strip('-') or 'x')
        rid, n = base, 1
        while rid in used:
            n += 1
            rid = f'{base}-{n}'
        used.add(rid)
        ids[label] = rid
    return ids


def code_span_ranges(line):
    """(start, end) of inline code spans; linear scan, CommonMark backtick-run matching."""
    out, i, n = [], 0, len(line)
    while i < n:
        if line[i] != '`':
            i += 1
            continue
        j = i
        while j < n and line[j] == '`':
            j += 1
        run = j - i
        k = j
        while True:
            k = line.find('`' * run, k)
            if k < 0:
                break
            e = k
            while e < n and line[e] == '`':
                e += 1
            if e - k == run:
                break
            k = e
        if k < 0:
            i = j
            continue
        out.append((i, k + run))
        i = k + run
    return out


def strip_code_spans(line):
    """Blank out inline code spans and HTML comments (keeps column positions)."""
    chars = list(line)
    for s, e in code_span_ranges(line):
        chars[s:e] = ' ' * (e - s)
    line = ''.join(chars)
    return re.sub(r'<!--.*?-->', lambda m: ' ' * len(m.group(0)), line)


def fence_open(line):
    """(prefix, fence, info) when the line opens a fenced code block, else None."""
    m = FENCE_RE.match(line)
    if not m:
        return None
    fence, rest = m.group(2), m.group(3)
    if fence[0] == '`' and '`' in rest:
        return None  # ```inline``` code, not a fence
    info = rest.strip().split()[0].lower() if rest.strip() else ''
    return m.group(1), fence, info


def split_blocks(lines):
    """Yield (kind, info, start_line_index, block_lines).

    kind: 'text', 'code' (fenced; info = language), 'icode' (indented code), 'comment' (HTML comment block).
    """
    buf, start, i = [], 0, 0
    in_list, prev_blank = False, True

    def flush():
        nonlocal buf
        if buf:
            blk = buf
            buf = []
            return [('text', '', start, blk)]
        return []

    while i < len(lines):
        ln = lines[i]
        fo = fence_open(ln)
        if fo:
            yield from flush()
            prefix, fence, info = fo
            first, code = i, [ln]
            i += 1
            close = re.compile(r'^(?:[ \t]*>)*[ \t]*' + re.escape(fence[0]) + '{' + str(len(fence)) + r',}[ \t]*$')
            while i < len(lines):
                code.append(lines[i])
                if close.match(lines[i]):
                    break
                i += 1
            yield ('code', info, first, code)
            i += 1
            start, prev_blank = i, False
            continue
        s = ln.lstrip(' \t>')
        if s.startswith('<!--') and ('-->' not in s or s.rstrip().endswith('-->')):
            yield from flush()
            first, blk = i, [ln]
            while '-->' not in lines[i] and i + 1 < len(lines):
                i += 1
                blk.append(lines[i])
            yield ('comment', '', first, blk)
            i += 1
            start, prev_blank = i, False
            continue
        indented = ln.startswith(('    ', '\t'))
        if indented and prev_blank and not in_list and ln.strip():
            yield from flush()
            first, blk = i, []
            while i < len(lines) and (lines[i].startswith(('    ', '\t')) or not lines[i].strip()):
                blk.append(lines[i])
                i += 1
            while blk and not blk[-1].strip():  # trailing blank lines belong to the text
                blk.pop()
                i -= 1
            yield ('icode', '', first, blk)
            start, prev_blank = i, False
            continue
        if LIST_RE.match(ln):
            in_list = True
        elif ln.strip() and prev_blank and not ln[:1].isspace():
            in_list = False
        if not buf:
            start = i
        buf.append(ln)
        prev_blank = not ln.strip()
        i += 1
    yield from flush()


def iter_text_lines(lines):
    """(index, line) for lines outside code and HTML comments."""
    for kind, _, start, blk in split_blocks(lines):
        if kind == 'text':
            for j, ln in enumerate(blk):
                yield start + j, ln


SETEXT_RE = re.compile(r'^ {0,3}(=+|-+)\s*$')
HTML_H_RE = re.compile(r'^\s*<h([1-6])\b[^>]*>(.*?)</h\1>\s*$', re.I)


def headings(lines):
    """(index, level, text) outside code: ATX (#), setext (=== / ---), and HTML <h1>..<h6> lines."""
    out = []
    text = list(iter_text_lines(lines))
    idx = {i for i, _ in text}
    for i, ln in text:
        m = HEADING_RE.match(ln)
        if m:
            out.append((i, len(m.group(1)), (m.group(2) or '').strip()))
            continue
        h = HTML_H_RE.match(ln)
        if h:
            out.append((i, int(h.group(1)), re.sub(r'<[^>]+>', '', h.group(2)).strip()))
            continue
        nxt = lines[i + 1] if i + 1 < len(lines) and (i + 1) in idx else ''
        s = SETEXT_RE.match(nxt)
        if s and ln.strip() and not re.match(r'^\s*([-*+>|]|\d+[.)])\s', ln) and not HEADING_RE.match(ln) \
                and not SETEXT_RE.match(ln) and (i == 0 or not lines[i - 1].strip() or HEADING_RE.match(lines[i - 1])):
            out.append((i, 1 if s.group(1)[0] == '=' else 2, ln.strip()))
    return out


def is_setext(lines, i):
    return i + 1 < len(lines) and SETEXT_RE.match(lines[i + 1]) is not None and not HEADING_RE.match(lines[i])


def drop_sections(lines, names):
    """Remove sections whose heading text is in names (with all their subsections)."""
    if not names:
        return lines, []
    names = set(names)
    heads = {i: (lvl, t) for i, lvl, t in headings(lines)}
    out, dropped, skip = [], [], None
    for i, ln in enumerate(lines):
        if i in heads:
            lvl, t = heads[i]
            if skip is not None and lvl <= skip:
                skip = None
            if skip is None and t in names:
                skip = lvl
                dropped.append(t)
        if skip is None:
            out.append(ln)
    return out, dropped


def mask_dropped(lines, sections, line_patterns):
    """Blank out lines the build will drop, keeping line numbers intact (for check)."""
    out = list(lines)
    if sections:
        heads = {i: (lvl, t) for i, lvl, t in headings(lines)}
        skip = None
        for i in range(len(lines)):
            if i in heads:
                lvl, t = heads[i]
                if skip is not None and lvl <= skip:
                    skip = None
                if skip is None and t in set(sections):
                    skip = lvl
            if skip is not None:
                out[i] = ''
    res = [re.compile(p) for p in line_patterns]
    if res:
        for i, _ in iter_text_lines(lines):
            if any(r.search(lines[i]) for r in res):
                out[i] = ''
    return out


def parse_definitions(lines):
    """Reference definitions outside code and comments: label -> (url, title, line_index); plus duplicates."""
    defs, dups = {}, []
    for i, ln in iter_text_lines(lines):
        m = DEF_RE.match(ln)
        if m:
            label = m.group(1)
            title = next((g for g in m.groups()[2:] if g), '')
            if label in defs and defs[label][0] != m.group(2):
                dups.append((label, i))
            defs[label] = (m.group(2), title, i)
    return defs, dups


IMAGE_REF_RE = re.compile(r'!\[([^\]]*)\]\[([^\]]*)\]|!\[([^\]]+)\](?![\[(])')
IMAGE_EXT_RE = re.compile(r'\.(png|jpe?g|gif|svg|webp|bmp|tiff?|avif)([?#].*)?$', re.I)


def image_labels(lines):
    """Reference labels used by images (![alt][label], ![label]): they are never citations."""
    out = set()
    for _, ln in iter_text_lines(lines):
        for m in IMAGE_REF_RE.finditer(ln):
            out.add((m.group(2) or m.group(1) or m.group(3) or '').lower())
    return out


def is_citation_label(label, opts):
    """Numeric labels are citations; other labels only with citation_labels: all."""
    return label.isdigit() or opts.get('citation_labels', 'numeric') == 'all'


def reference_uses_re(labels):
    """Any use of a label as a reference: [label], [text][label], [label][], ![alt][label]."""
    alt = '|'.join(re.escape(l) for l in sorted(labels, key=len, reverse=True))
    return re.compile(r'\]\[(' + alt + r')\]|\[(' + alt + r')\]\[\]|(?<![\]\\])\[(' + alt + r')\](?![\(:])', re.I)


# ------------------------------------------------------------ mdBook includes

def _select(text, spec):
    """mdBook line selection: N, N:M, N:, :M (1-based, inclusive) or an ANCHOR name."""
    lines = text.split('\n')
    if text.endswith('\n'):
        lines = lines[:-1]
    if spec:
        if re.fullmatch(r'\d*(:\d*)?', spec):
            a, _, b = spec.partition(':')
            if ':' not in spec:
                lines = lines[int(a) - 1:int(a)] if a else lines
            else:
                lines = lines[(int(a) - 1 if a else 0):(int(b) if b else None)]
        else:
            name = re.escape(spec)
            out, on = [], False
            for ln in lines:
                if re.search(r'ANCHOR:\s*' + name + r'\b', ln):
                    on = True
                    continue
                if re.search(r'ANCHOR_END:\s*' + name + r'\b', ln):
                    on = False
                    continue
                if on:
                    out.append(ln)
            if not out:
                return None
            lines = out
    return '\n'.join(l for l in lines if not ANCHOR_LINE_RE.search(l))


def expand_includes(text, base_dir, root, depth=0):
    """Expand mdBook {{#include}}, {{#rustdoc_include}}, {{#playground}}; drop {{#title}}.

    Paths are relative to base_dir and must stay inside root. Returns (text, expanded, errors).
    """
    errors, count = [], 0

    def repl(m):
        nonlocal count
        if m.group(1):  # \{{#include}} is a literal
            return m.group(0)[1:]
        kind, arg = m.group(2), m.group(3).strip()
        if kind == 'title':
            return ''
        target = arg.split()[0] if arg else ''
        path, _, spec = target.partition(':')
        p = (Path(base_dir) / path).resolve()
        try:
            p.relative_to(Path(root).resolve())
        except ValueError:
            errors.append((m.group(0), 'outside the repository'))
            return m.group(0)
        if not p.is_file():
            errors.append((m.group(0), 'file not found'))
            return m.group(0)
        try:
            body = p.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError) as e:
            errors.append((m.group(0), f'cannot read: {e}'))
            return m.group(0)
        sel = _select(body, spec)
        if sel is None:
            errors.append((m.group(0), f'anchor not found: {spec}'))
            return m.group(0)
        if depth < 5 and '{{#' in sel:
            sel, n, errs = expand_includes(sel, p.parent, root, depth + 1)
            count += n
            errors.extend(errs)
        count += 1
        return sel

    return INCLUDE_RE.sub(repl, text), count, errors


def hide_rust_lines(code_lines):
    """mdBook hides lines starting with '# ' in Rust code blocks; '##' is a literal '#'."""
    out = [code_lines[0]]
    for ln in code_lines[1:-1]:
        m = re.match(r'^(\s*)#(#?)(.*)$', ln)
        if m and m.group(2):
            out.append(m.group(1) + '#' + m.group(3))
        elif m and (m.group(3) == '' or m.group(3).startswith(' ')):
            continue
        else:
            out.append(ln)
    out.append(code_lines[-1])
    return out


# ------------------------------------------------------------------ Mermaid

def mermaid_source(code_lines, today_marker=False):
    body = code_lines[1:]
    if body and re.match(r'^(?:[ \t]*>)*[ \t]*(`{3,}|~{3,})[ \t]*$', body[-1]):
        body = body[:-1]
    if not today_marker and body and body[0].strip().startswith('gantt') \
            and not any(l.strip().startswith('todayMarker') for l in body):
        body = [body[0], '    todayMarker off'] + body[1:]
    return '\n'.join(body) + '\n'


def mermaid_alt(code_lines, prefix, override=''):
    if override:
        return override
    title = next((l.strip()[6:].strip() for l in code_lines if l.strip().startswith('title ')), '')
    if not title:  # --- title: X --- front matter
        title = next((l.split(':', 1)[1].strip().strip('"\'') for l in code_lines
                      if re.match(r'^\s*title\s*:', l)), '')
    if not title:
        labels = re.findall(r'\w[\[\(\{]+"?([^\[\]\(\)\{\}"]+?)"?[\]\)\}]+', '\n'.join(code_lines[1:-1]))
        title = ', '.join(dict.fromkeys(l.strip() for l in labels if l.strip()))[:300]
    return f'{prefix}: {title}' if title else prefix


def mermaid_hash(src):
    return hashlib.sha256(src.encode('utf-8')).hexdigest()[:12]


# ------------------------------------------------------------------ pre-pass

def prepass(text, fcfg, opts, render_mermaid=None, base_dir=None, root=None):
    """Prepare one file's Markdown for pandoc.

    render_mermaid(src, alt) -> list of Markdown lines replacing the code block.
    base_dir/root: the file's folder and the repository root, for mdBook includes.
    Returns (text, stats); stats['citations'] lists {label, url, id} for the filter.
    """
    text = text.replace('\r\n', '\n').replace('\r', '\n').lstrip('﻿')
    stats = {'mermaid': 0, 'dropped_lines': 0, 'includes': 0, 'include_errors': []}
    if base_dir is not None and '{{#' in text:
        text, stats['includes'], stats['include_errors'] = expand_includes(text, base_dir, root or base_dir)
    lines = text.split('\n')
    lines, dropped = drop_sections(lines, fcfg.get('drop_sections') or [])
    stats['dropped_sections'] = dropped
    drop_res = [re.compile(p) for p in opts.get('drop_lines') or []]
    refdefs = opts.get('citations', 'refdefs') == 'refdefs'
    defs, order, out = {}, [], []

    not_cites = image_labels(lines)
    for kind, info, _, blk in split_blocks(lines):
        if kind == 'code':
            if info.startswith('mermaid') and opts.get('mermaid') != 'keep' and render_mermaid:
                src = mermaid_source(blk, opts.get('mermaid_today_marker', False))
                alt = mermaid_alt(blk, opts.get('mermaid_alt_prefix', 'Chart'), fcfg.get('mermaid_alt', ''))
                out.extend(render_mermaid(src, alt))
                stats['mermaid'] += 1
            elif info.startswith('rust') and opts.get('_mdbook') and len(blk) > 1:
                out.extend(hide_rust_lines(blk))
            else:
                out.extend(blk)
            continue
        if kind != 'text':
            out.extend(blk)
            continue
        for ln in blk:
            if any(r.search(ln) for r in drop_res):
                stats['dropped_lines'] += 1
                continue
            m = DEF_RE.match(ln) if refdefs else None
            if m and is_citation_label(m.group(1), opts) and m.group(1).lower() not in not_cites \
                    and (m.group(1).isdigit() or not IMAGE_EXT_RE.search(m.group(2))):
                # definition lines stay: pandoc resolves [1] to a link, which the filter turns into a citation
                label = m.group(1)
                if label not in defs:
                    order.append(label)
                defs[label] = (m.group(2), next((g for g in m.groups()[2:] if g), ''))
            out.append(ln)

    stats['citations'] = []
    if defs:
        ordered = sorted(order, key=lambda l: (0, int(l), '') if l.isdigit() else (1, order.index(l), l))
        ids = label_ids(ordered)
        entries = []
        for label in ordered:
            url, title = defs[label]
            stats['citations'].append({'label': label, 'url': url, 'id': ids[label]})
            t = title_markdown(title.strip()) if title else ''
            if t and not re.search(r'[.?!]$', t):
                t += '.'
            entry = f'- <a id="{ids[label]}"></a>\\[{md_escape(label)}\\] {t} <{url}>'
            entries.append(re.sub(r'  +', ' ', entry))
        block = ['', '<div class="references">', ''] + entries + ['', '</div>', '']
        heads = set(opts.get('reference_headings') or [])
        pos = None
        for i, lvl, t in headings(out):
            if t in heads:
                pos = i + 1 if is_setext(out, i) else i
        if pos is None:
            out += ['', f"## {opts.get('reference_heading_new', 'References')}"]
            pos = len(out) - 1
        out[pos + 1:pos + 1] = block
        stats['references'] = len(entries)
    return '\n'.join(out), stats
