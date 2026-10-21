"""PDF navigation and metadata: the rights line added to the print HTML, then the outline, Info and XMP written into
Chrome's PDF, and the gates that check them in the final file.

The outline holds exactly pandoc's contents (nav#TOC). Each entry's destination is its heading, chosen at print time by
the page script; for an element with no box of its own (display: contents), for which Chrome writes no destination, it
is the first element inside that has both a box and an id of its own. The title block, the contents nav and the rights
line are placed the same way, from their own ids. Chrome writes a destination only for a link target, so hidden links
to each (no annotation, tag or text) go in the document's head, where Chrome still finds them; the page is then printed
again without them, and a book whose CSS prints the two differently is refused."""
import hashlib
import html
import re
import unicodedata
import urllib.parse
from html.parser import HTMLParser
from xml.sax.saxutils import escape

from .build import BuildError

VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'source', 'track', 'wbr'}
TITLE, RIGHTS, CONTENTS = 'title-block-header', 'mdb-rights', 'TOC'   # pandoc's own ids, and the rights line setup adds
FIT_ARGS = {'/XYZ': ('/Left', '/Top', '/Zoom'), '/Fit': (), '/FitB': (), '/FitH': ('/Top',), '/FitBH': ('/Top',),
            '/FitV': ('/Left',), '/FitBV': ('/Left',), '/FitR': ('/Left', '/Bottom', '/Right', '/Top')}


class _Scan(HTMLParser):
    """Source positions in pandoc's print HTML: each id with its element and the end of its start tag, the contents
    links with their nesting, and the title block's start and closing tags. Regions an anchor may not target: the
    cover, the title block and the contents nav."""

    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.starts = [0]
        for line in text.split('\n')[:-1]:
            self.starts.append(self.starts[-1] + len(line) + 1)
        self.stack, self.ids, self.links = [], {}, []
        self.nav = self.header = self.header_close = None
        self._nav_at = self._header_at = None

    def _offset(self):
        line, col = self.getpos()
        return self.starts[line - 1] + col

    def _region(self):
        return any(tag == 'section' and 'pdf-cover' in classes or ident in ('title-block-header', 'TOC')
                   for tag, ident, classes in self.stack)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        start = self._offset()
        end = start + len(self.get_starttag_text())
        ident = attrs.get('id')
        classes = set((attrs.get('class') or '').split())
        here = tag == 'section' and 'pdf-cover' in classes or ident in ('title-block-header', 'TOC')   # a region's own root counts
        if ident is not None and ident not in self.ids:
            self.ids[ident] = {'tag': tag, 'end': end, 'region': self._region() or here}
        if tag == 'nav' and ident == 'TOC' and self.nav is None:
            self.nav, self._nav_at = end, len(self.stack)
        elif self._nav_at is not None and self._nav_at >= 0 and tag == 'a' and (attrs.get('href') or '').startswith('#'):
            depth = sum(1 for t, _, _ in self.stack[self._nav_at:] if t == 'ul')
            self.links.append({'depth': depth, 'start': start, 'end': end, 'raw': self.get_starttag_text(), 'href': attrs['href']})
        if tag == 'header' and ident == 'title-block-header' and self.header is None:
            self.header, self._header_at = end, len(self.stack)
        if tag not in VOID:
            self.stack.append((tag, ident, classes))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.stack.pop()

    def handle_endtag(self, tag):
        for k in range(len(self.stack) - 1, -1, -1):
            if self.stack[k][0] == tag:
                if k == self._header_at and self.header_close is None:
                    self.header_close = self._offset()
                if k == self._nav_at:
                    self._nav_at = -1   # past the nav: no more contents links
                del self.stack[k:]
                return


def prepare(path, rights):
    """Rewrite the print HTML once: the rights line, with its own id, before the title block's closing tag; each contents
    entry's key is its place among the contents links, which the page counts the same way. Nothing goes inside a heading
    or among an author's elements: the page script chooses each destination at print time (the heading itself, or for one
    with no box the first element in it with a box and an id) and puts the hidden links Chrome needs in the head. Returns
    the contents entries, in order, as {'depth', 'key', 'target'}, and whether pandoc wrote a contents nav."""
    text = path.read_text(encoding='utf-8')
    scan = _Scan(text)
    scan.feed(text)
    scan.close()
    if rights and RIGHTS in scan.ids:   # the only id the PDF's navigation adds (the contents entries' mdb-dest-<n> are keys
        raise BuildError(f'the book uses the id {RIGHTS!r}, which the PDF\'s rights line takes; rename it')   # for the page only)
    if scan.header is None or scan.header_close is None:
        raise BuildError('the print document has no title block (header#title-block-header)')
    edits, entries = [], []
    for n, link in enumerate(scan.links, 1):
        target = urllib.parse.unquote(link['href'][1:])
        found = scan.ids.get(target)
        if not found or found['tag'] in VOID or found['region']:
            raise BuildError(f'contents entry {n} points to {target!r}, which is not a printable element of the book')
        entries.append({'depth': link['depth'], 'key': f'mdb-dest-{n}', 'target': target})   # the link itself is left as it is:
        # the page finds the n-th contents link by its place, so no attribute a selector of the book's CSS could see is added
    if rights:
        edits.append((scan.header_close, scan.header_close, f'<p class="rights" id="{RIGHTS}">{html.escape(rights)}</p>'))
    for start, end, new in sorted(edits, key=lambda e: (e[0], e[1]), reverse=True):
        text = text[:start] + new + text[end:]
    path.write_text(text, encoding='utf-8')
    return entries, scan.nav is not None


def join_entries(entries, page):
    """The nav's entries with the anchor, labels and print visibility the page reported for each key, in order."""
    by_id = {e.get('id'): e for e in page}
    if len(page) != len(entries) or set(by_id) != {e['key'] for e in entries}:
        raise BuildError('the page reported other contents entries than the print document holds')
    out = []
    for n, e in enumerate(entries, 1):
        seen = by_id[e['key']]
        named = seen.get('name') or seen.get('text') or seen.get('label', '')   # a hidden entry shows no label of its own
        if not seen.get('listed', True):
            raise BuildError(f"contents entry «{named}» is hidden in the printed contents, so the bookmarks would "
                             'not match it; show it there, or keep its heading out of the contents with a lower options.toc_depth')
        if seen.get('placeless'):
            raise BuildError(f"contents entry «{named}» points to a heading with no box of its own (display: contents) and no element "
                             'in it that has both a box and an id, so its bookmark has nowhere to open; give the heading a box, or keep '
                             'it out of the contents with a lower options.toc_depth')
        if seen.get('unresolved'):
            raise BuildError(f"contents entry «{named}» shows text that print CSS generates with {', '.join(seen['unresolved'])}, which "
                             'the bookmark cannot repeat; write that text into the heading, or generate only strings and attr() there')
        if seen.get('cut'):
            raise BuildError(f"contents entry «{named}» is only partly visible in the printed contents: an element that hides its "
                             'overflow, or the page edge, cuts off part of its text, so what the bookmark should hold cannot be told; '
                             'let the entry show in full (no fixed width or height with overflow: hidden or text-overflow on it)')
        if not seen.get('printed'):
            raise BuildError(f"contents entry «{named}» points to a heading that isn't printed (display: none or "
                             'visibility: hidden, on it or a parent); show it in print, or keep it out of the contents and bookmarks '
                             'with a lower options.toc_depth')
        if not (seen.get('label') or '').strip():
            raise BuildError(f'contents entry {n} shows nothing a bookmark title can hold (an image with no alt text, say), so its '
                             'bookmark would be blank; give the image alt text (![a description](file)), or keep the heading out of the '
                             'contents with a lower options.toc_depth')
        out.append(dict(e, anchor=seen.get('anchor') or e['key'], marker=seen.get('marker', ''), outlined=seen.get('outlined', False),
                        runs=seen.get('runs'), label=seen.get('label', ''),
                        text=seen.get('text', seen.get('label', '')),
                        words=seen.get('words', seen.get('label', ''))))
    return out


def _decoded(key):
    """A destination's name: a NameObject key loses its leading slash once, a text string is taken as it is, and either is
    then URL-decoded, as Chrome percent-encodes the link fragment."""
    from pypdf.generic import NameObject
    return urllib.parse.unquote(str(key)[1:] if isinstance(key, NameObject) else str(key))


def named_destinations(reader):
    """Named destinations by their decoded names."""
    return {_decoded(key): dest for key, dest in reader.named_destinations.items()}


def _drawing(obj, memo, depth=0):
    """A comparable digest of what a page object draws: dictionaries and arrays by their items, streams by their decoded
    bytes, indirect objects resolved once each; parents and page back-references are left out."""
    from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject, StreamObject
    if isinstance(obj, IndirectObject):
        key = (obj.idnum, obj.generation)
        if key not in memo:
            memo[key] = None   # a cycle reads as itself
            memo[key] = _drawing(obj.get_object(), memo, depth + 1)
        return memo[key]
    if isinstance(obj, StreamObject):
        items = tuple(sorted((str(k), _drawing(v, memo, depth + 1)) for k, v in obj.items()
                             if k not in ('/Length', '/Filter', '/DecodeParms')))
        return hashlib.sha256(repr(items).encode() + obj.get_data()).hexdigest()
    if isinstance(obj, DictionaryObject):
        return tuple(sorted((str(k), _drawing(v, memo, depth + 1)) for k, v in obj.items() if k not in ('/Parent', '/P')))
    if isinstance(obj, ArrayObject):
        return tuple(_drawing(v, memo, depth + 1) for v in obj)
    return repr(obj)


def changed_page(with_links, without):
    """The first page (from 1) Chrome printed differently with the hidden locator links in the head than without them, 0
    when the page counts differ, or None when every page is the same: contents, resources, annotations and boxes."""
    from pypdf import PdfReader
    one, two = PdfReader(with_links, strict=True), PdfReader(without, strict=True)
    if len(one.pages) != len(two.pages):
        return 0
    memo_one, memo_two = {}, {}
    for n, (a, b) in enumerate(zip(one.pages, two.pages), 1):
        if _drawing(a, memo_one) != _drawing(b, memo_two):
            return n
    return None


def _fit(dest):
    typ = str(dest['/Type'])
    args = []
    for key in FIT_ARGS.get(typ, ()):
        value = dest.get(key)
        args.append(None if value is None or str(value) == 'null' else round(float(value), 2))
    return typ, tuple(args)


def project(reader, entries, has_nav, rights, places=None):
    """The outline to write, as (label, depth, page index, fit type, fit arguments) per entry, from each anchor's
    destination, and the locators' pages. places maps a locator's id to the element its destination was written for (the
    page reports it: the first element with a box inside a display: contents one). A missing destination is a
    finalization error."""
    named = named_destinations(reader)
    place = lambda ident: (places or {}).get(ident, ident)
    rows, open_depths = [], []
    for e in entries:
        dest = named.get(e['anchor'])
        if dest is None:
            raise BuildError(f"Chrome wrote no destination for contents entry «{e['label']}»")
        while open_depths and open_depths[-1] >= e['depth']:   # the tree depth, as the written outline nests it
            open_depths.pop()
        open_depths.append(e['depth'])
        rows.append((e['label'], len(open_depths), reader.get_destination_page_number(dest)) + _fit(dest))
    pages = {}
    for ident, wanted in ((TITLE, True), (RIGHTS, bool(rights)), (CONTENTS, has_nav)):
        if wanted:
            if place(ident) not in named:
                raise BuildError(f'Chrome wrote no destination for the {ident} locator (with display: contents, it needs an element '
                                 'inside with a box and an id)')
            pages[ident] = reader.get_destination_page_number(named[place(ident)])
    return rows, pages


def xmp(meta):
    """The XMP packet from the resolved metadata: dc:title and dc:description as language alternatives, dc:creator in
    order, dc:subject, dc:language, dc:rights and dc:publisher when set. XML-escaped on its own."""
    lang = escape(meta['lang'], {'"': '&quot;'})

    def alt(value):
        value = escape(value)
        return (f'<rdf:Alt><rdf:li xml:lang="x-default">{value}</rdf:li><rdf:li xml:lang="{lang}">{value}</rdf:li></rdf:Alt>')

    def items(kind, values):
        return f'<rdf:{kind}>' + ''.join(f'<rdf:li>{escape(v)}</rdf:li>' for v in values) + f'</rdf:{kind}>'
    parts = [f'<dc:title>{alt(meta["title"])}</dc:title>']
    if meta.get('authors'):
        parts.append(f'<dc:creator>{items("Seq", meta["authors"])}</dc:creator>')
    if meta.get('description'):
        parts.append(f'<dc:description>{alt(meta["description"])}</dc:description>')
    if meta.get('subjects'):
        parts.append(f'<dc:subject>{items("Bag", meta["subjects"])}</dc:subject>')
    parts.append(f'<dc:language>{items("Bag", [meta["lang"]])}</dc:language>')
    if meta.get('rights'):
        parts.append(f'<dc:rights>{alt(meta["rights"])}</dc:rights>')
    if meta.get('publisher'):
        parts.append(f'<dc:publisher>{items("Bag", [meta["publisher"]])}</dc:publisher>')
    return ('<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>\n<x:xmpmeta xmlns:x="adobe:ns:meta/">'
            '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"><rdf:Description rdf:about="" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/">' + ''.join(parts) + '</rdf:Description></rdf:RDF></x:xmpmeta>\n'
            '<?xpacket end="w"?>')


def info(meta):
    """The Info entries from the resolved metadata; empty optional fields are left out, never invented."""
    out = {'/Title': meta['title']}
    if meta.get('authors'):
        out['/Author'] = '; '.join(meta['authors'])
    if meta.get('description'):
        out['/Subject'] = meta['description']
    if meta.get('subjects'):
        out['/Keywords'] = ', '.join(meta['subjects'])
    return out


def _link_names(page):
    """The named destinations a page's link annotations go to, as (raw name object, decoded name)."""
    from pypdf.generic import NameObject
    out = []
    for annot in page.get('/Annots') or []:
        annot = annot.get_object()
        dest = annot.get('/Dest')
        if annot.get('/Subtype') == '/Link' and isinstance(dest, (NameObject, str)):
            out.append((dest, urllib.parse.unquote(str(dest)[1:] if isinstance(dest, NameObject) else str(dest))))
    return out


def finalize(source, target, rows, meta, aliases=None):
    """Clone Chrome's PDF whole, replace its outline with the projected one, write Info and XMP, and save to target.
    aliases maps a contents target id to its anchor: a printed contents link whose target got no destination from Chrome
    (a heading with no box of its own) is given its anchor's, under the name the link already uses."""
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import DecodedStreamObject, Fit, NameObject
    reader = PdfReader(source, strict=True)
    writer = PdfWriter(clone_from=reader)
    root = writer._root_object
    if '/Outlines' in root:
        del root['/Outlines']
    dests = root.get('/Dests')
    dests = dests.get_object() if dests is not None else None
    keys = {_decoded(key): key for key in dests} if aliases and dests is not None else {}   # Chrome's keys, encoded
    for page in writer.pages if keys else ():
        for raw, name in _link_names(page):
            anchor = keys.get(aliases[name]) if name in aliases else None
            if isinstance(raw, NameObject) and raw not in dests and anchor is not None:
                dests[raw] = dests[anchor]
    parents = []
    for label, depth, page, typ, args in rows:
        while parents and parents[-1][0] >= depth:
            parents.pop()
        item = writer.add_outline_item(label, page, parent=parents[-1][1] if parents else None, fit=Fit(typ, args))
        parents.append((depth, item))
    writer.add_metadata(info(meta))
    stream = DecodedStreamObject()
    stream.set_data(xmp(meta).encode('utf-8'))
    stream[NameObject('/Type')] = NameObject('/Metadata')
    stream[NameObject('/Subtype')] = NameObject('/XML')
    root[NameObject('/Metadata')] = writer._add_object(stream)
    with open(target, 'wb') as out:
        writer.write(out)


def words(text):
    """The words of a text, NFKC and case-folded, as a list: how a configured title or rights line is matched whole."""
    return re.findall(r'[^\W_]+', unicodedata.normalize('NFKC', text or '').casefold())


def holds(text, part):
    """Whether text holds part's words in order, each whole: «A» is not found in «Map». A part with no word in it (©,
    !!!) is found by its own characters, spaces aside."""
    want, have = words(part), words(text)
    if not want:
        squeeze = lambda t: ''.join(unicodedata.normalize('NFKC', t or '').split())
        return bool(squeeze(part)) and squeeze(part) in squeeze(text)
    return any(have[i:i + len(want)] == want for i in range(len(have) - len(want) + 1))


def normalized(text):
    """Letters and digits only, NFKC, case-folded: how labels, titles and rights are found in a page's text."""
    return ''.join(c for c in unicodedata.normalize('NFKC', text or '').casefold() if c.isalnum())


def _flat(reader, items, depth=1):
    out, last = [], None
    for item in items:
        if isinstance(item, list):
            out += _flat(reader, item, depth + 1)
            continue
        out.append((str(item.title), depth, reader.get_destination_page_number(item)) + _fit(item))
    return out


def _outlined_ends(contents, at, pieces):
    """Where an entry drawn partly or wholly as an outline can end, read from at: each filled piece exactly once, each outline
    piece twice, as Chrome writes it, or once; the ends that consume the most text first, none when the text there is not
    the entry. One pass over the pieces, keeping each distinct cursor once, so repeated pieces cost no more than their text."""
    cursors = {at}
    for text, outline in pieces:
        step = {c + len(text) for c in cursors if contents.startswith(text, c)}
        if outline:
            step |= {c + 2 * len(text) for c in cursors if contents.startswith(text * 2, c)}
        cursors = step
    return sorted(cursors, reverse=True)


def gates(path, rows, meta, toc_title, has_nav, rights, printed=None, links=None, listed=None, places=None, markers=None,
          before='', page_numbers=True, front=None, runs=None):
    """The outline, front-matter and metadata gates on the final file, each {'result', 'problems', ...}. printed holds each
    entry's heading words, which the page check looks for on its destination page (a bookmark label may also name an image
    by its alt text); listed holds the words each entry shows in the contents, which must be in the contents pages' own
    text, in order: CSS that keeps an entry's text out of the PDF (zero opacity or size, clipping, off the page) shows there.
    runs holds, for an entry with text drawn only as an outline, its printed pieces in order as (text, outline only)."""
    from pypdf import PdfReader
    import xml.etree.ElementTree as ElementTree
    reader = PdfReader(path, strict=True)
    place = lambda ident: (places or {}).get(ident, ident)   # the element each locator's destination was written for
    raw = [p.extract_text() or '' for p in reader.pages]
    texts = [normalized(t) for t in raw]

    def footless(i):   # page i's raw text without the page number its footer prints (its last line), when pages are numbered
        lines = raw[i].rstrip().split('\n')
        return '\n'.join(lines[:-1] if page_numbers and lines and lines[-1].strip() == str(i + 1) else lines)

    def unnumbered(i):
        return normalized(footless(i))
    problems, skipped = [], []
    found = _flat(reader, reader.outline)
    if found != rows:
        problems.append(f'the outline is not the projected one ({len(found)} entries against {len(rows)})')
    for n, (label, _, page, *_) in enumerate(rows):
        want = normalized(printed[n] if printed is not None else label)
        if not want:
            skipped.append(f'«{label}»: no letters or digits to find')
            continue
        here = texts[page] + (texts[page + 1] if page + 1 < len(texts) else '')
        at = here.find(want)
        if not 0 <= at < len(texts[page]):
            problems.append(f'«{label}» does not begin on its destination page {page + 1}')
    named = named_destinations(reader)
    if listed is not None and rows:
        first = reader.get_destination_page_number(named[place(CONTENTS)]) if place(CONTENTS) in named else None
        contents, at, last = '', 0, first
        if first is None:
            problems.append('the contents page has no destination, so its entries cannot be found on it')
        else:   # the contents pages, with the first listed heading's page when the contents run onto it (it does not start
            lead = min(range(len(rows)), key=lambda n: rows[n][2])   # with that heading). The entries are read as the sequence
            heading = normalized(printed[lead]) if printed is not None else ''   # they print in: each right after the one before,
            last = max(rows[lead][2], first)   # with only its own list marker between, so nothing is found in later text
            if last > first and heading and unnumbered(last).startswith(heading):
                last -= 1
            contents = ''.join(unnumbered(i) for i in range(first, last + 1))
            ahead = normalized(before)   # a page the title block shares with the contents starts with the end of it
            shared = place(TITLE) in named and reader.get_destination_page_number(named[place(TITLE)]) == first
            at = next((k for k in range(min(len(ahead), len(contents)), 0, -1) if contents.startswith(ahead[-k:])), 0) if shared else 0
            title = normalized(toc_title)
            if title and contents.startswith(title, at):
                at += len(title)
        pages = '' if first is None else f'page {first + 1}' if last == first else f'pages {first + 1}–{last + 1}'
        matched, doubt = None, None
        if first is not None and markers is not None and None in markers:   # a marker the page could not spell out: no exact
            skipped.append('the printed contents text: a list marker uses counters or a style the check cannot spell out, so '
                           'where each entry prints was not checked')   # sequence to read
            first = None
        for n, (label, *_) in enumerate(rows if first is not None else ()):
            want = normalized(listed[n])
            pieces = [(normalized(t), o) for t, o in (runs[n] if runs is not None and runs[n] else ()) if normalized(t)]
            if pieces:   # text drawn only as an outline: its pieces in place, the outline ones as Chrome writes them
                mark = normalized(markers[n]) if markers is not None else ''
                plain = [m for m in range(n + 1, len(rows)) if normalized(listed[m]) and not (runs and runs[m])]
                expect = lambda m: (normalized(markers[m]) if markers is not None else '') + normalized(listed[m])
                ends = _outlined_ends(contents, at + len(mark), pieces) if contents.startswith(mark, at) else []
                follows = bool(plain) and plain[0] == n + 1
                if ends:   # read in place: the next plain entry starts where it ends, else is read there and fails on its own
                    fit = next((e for e in ends[1:] if contents.startswith(expect(n + 1), e)), None) if follows else None
                    if fit is not None and not contents.startswith(expect(n + 1), ends[0]):   # it starts only where fewer
                        at, doubt = fit, n + 1   # copies end: its text may be this entry's second copy
                    else:
                        at = ends[0]
                    matched = label
                    continue
                found = next(((k, m) for m, k in ((m, contents.find(expect(m), at)) for m in plain) if k >= 0),
                             (len(contents), None))   # else its filled words, in order, before the next plain entry the
                bound, doubt = found   # text holds, whose place this entry's unread outline text leaves uncertain
                cursor = at
                for text, outline in pieces:
                    hit = -1 if outline else contents.find(text, cursor, bound)
                    cursor = cursor if outline else hit + len(text) if hit >= 0 else -1
                    if cursor < 0:
                        break
                if cursor < 0:
                    problems.append(f'«{label}» is not in the printed contents text ({pages}); CSS may keep it out of print')
                else:
                    skipped.append(f'«{label}»: its outline text is arranged in a way the check cannot read, so only its '
                                   'filled words were found, in order, before the next entry')
                    matched = label
                at = bound   # the next entry is read where it starts, past whatever this one left
                continue
            if not want:   # an image, or text drawn only as an outline: no text to find; its marker still prints
                skipped.append(f'«{label}»: no printed words in the contents to find')
                mark = normalized(markers[n]) if markers is not None and markers[n] is not None else ''
                at += len(mark) if mark and contents.startswith(mark, at) else 0
                continue
            mark = normalized(markers[n]) if markers is not None else ''   # the entry is its own list marker, then its words,
            where = at + len(mark) if contents.startswith(mark + want, at) else -1   # right here: anything else means it is not
                                                                                       # where it prints
            if where < 0:
                problems.append(f'«{label}» is not in the printed contents text ({pages}); CSS may keep it out of print')
            else:
                at, matched = where + len(want), label
                if doubt == n:
                    skipped.append(f'«{label}»: the outlined entry before it may have printed this text itself, so its '
                                   'place was not fully checked')
        if first is not None and last == rows[lead][2] and heading and matched is not None and contents.find(heading, at) < 0:
            problems.append(f'«{matched}» is not in the printed contents text ({pages}): what matched it is the heading that follows; '
                            'CSS may keep it out of print')   # the shared page's heading must still lie ahead of every entry
    for index, page in enumerate(reader.pages):   # every printed contents link goes where its bookmark goes
        for _, name in _link_names(page) if links else ():
            if name in links:
                dest = named.get(name)
                if dest is None or reader.get_destination_page_number(dest) != links[name]:
                    problems.append(f'the contents link to {name!r} on page {index + 1} does not open its heading\'s page')
    outline = {'result': 'fail' if problems else 'pass', 'entries': len(rows), 'problems': problems, 'not_checked': skipped}
    elements = front or {}   # the element itself prints, as the page reported it: its words elsewhere on the page are no proof

    def drawn(part, want):   # the element draws, and the words it draws hold the configured text, each whole (the page's
        # extracted text may split a word, so the page is checked by its letters; the element's own words come from the DOM)
        seen = elements.get(part)
        return not seen or bool(seen.get('shows')) and (seen.get('words') is None or holds(seen['words'], want))
    def cut(part):   # the element prints only part of its text: its words and the page text may hold what is cut off
        return bool((elements.get(part) or {}).get('cut'))
    front, not_applicable = [], []
    title_page = reader.get_destination_page_number(named[place(TITLE)]) if place(TITLE) in named else None
    if cut('title'):   # first: whatever the page text holds of it, part of it does not print
        front.append('the title is only partly visible on the title page: an element that hides its overflow, or the page edge, cuts it')
    elif title_page is None or normalized(meta['title']) not in texts[title_page] or not drawn('title', meta['title']):
        front.append('the title is not on the title page')
    else:   # the whole title block is on that page: each word it draws (author, date, abstract) is one of the page's own
        # words, each occurrence its own (a word the title shares with the author is two), a word of symbols only (©) by its
        # characters; whole words first, then a word the page's text splits over pieces or runs into a neighbour
        tokens = lambda text: [normalized(w) or ''.join(unicodedata.normalize('NFKC', w).split()) for w in text.split()]
        block = (elements.get('block') or {}).get('words') or ''
        have = [t for t in tokens(footless(title_page)) if t]   # the footer's page number is no word of the block
        left = []
        for word, want in sorted(((w, t) for w, t in zip(block.split(), tokens(block)) if t), key=lambda p: -len(p[1])):
            if want in have:
                have.remove(want)
            else:
                left.append((word, want))
        for word, want in left:
            spans = [(i, j) for i in range(len(have)) for j in range(i + 1, len(have) + 1) if ''.join(have[i:j]) == want]
            inside = next((i for i, h in enumerate(have) if want in h), None)
            if spans:
                del have[spans[0][0]:spans[0][1]]
            elif inside is not None:
                h, k = have[inside], have[inside].find(want)
                have[inside:inside + 1] = [x for x in (h[:k], h[k + len(want):]) if x]
            else:
                front.append(f'the title block does not fit on the title page: «{word}» prints on another page')
                break
    if rights:
        page = reader.get_destination_page_number(named[place(RIGHTS)]) if place(RIGHTS) in named else None
        if cut('rights'):
            front.append('the rights line is only partly visible on the title page: an element that hides its overflow, or the page edge, '
                         'cuts it')
        elif page != title_page or normalized(rights) not in texts[title_page or 0] or not drawn('rights', rights):
            front.append('the rights line is not on the title page')
    else:
        not_applicable.append('rights: none configured')
    if has_nav and toc_title:
        page = reader.get_destination_page_number(named[place(CONTENTS)]) if place(CONTENTS) in named else None
        if cut('contents'):
            front.append('the contents heading is only partly visible on the first contents page: an element that hides its overflow, '
                         'or the page edge, cuts it')
        elif page is None or normalized(toc_title) not in texts[page] or not drawn('contents', toc_title):
            front.append('the contents heading is not on the first contents page')
    else:
        not_applicable.append('contents heading: ' + ('no title for this language' if has_nav else 'contents disabled or pandoc wrote no contents'))
    front_matter = {'result': 'fail' if front else 'pass', 'problems': front, 'not_applicable': not_applicable}
    wrong = []
    for key, value in info(meta).items():
        if (reader.metadata or {}).get(key) != value:
            wrong.append(f'Info {key}')
    for key in ('/Author', '/Subject', '/Keywords'):
        if key not in info(meta) and key in (reader.metadata or {}):
            wrong.append(f'Info {key} set though the configuration has none')
    stream = reader.trailer['/Root'].get('/Metadata')
    if stream is None:
        wrong.append('no XMP metadata stream')
    else:
        stream = stream.get_object()
        if (stream.get('/Type'), stream.get('/Subtype'), stream.get('/Filter')) != ('/Metadata', '/XML', None):
            wrong.append('the XMP stream is not an uncompressed /Metadata /XML stream')
        if stream.get_data().decode('utf-8') != xmp(meta):
            wrong.append('the XMP packet differs from the configuration')
        try:
            ElementTree.fromstring(re.sub(r'<\?xpacket[^>]*\?>', '', stream.get_data().decode('utf-8')))
        except ElementTree.ParseError as e:
            wrong.append(f'the XMP packet is not well-formed XML ({e})')
    lang = str(reader.trailer['/Root'].get('/Lang') or '')
    if lang.lower() != meta['lang'].lower():
        wrong.append(f'catalog /Lang {lang!r}, not {meta["lang"]!r}')
    metadata = {'result': 'fail' if wrong else 'pass', 'problems': wrong}
    return outline, front_matter, metadata
