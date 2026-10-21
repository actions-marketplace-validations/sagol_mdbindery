"""PDF navigation and metadata (pdfnav): the anchor pass on pandoc-shaped HTML, then the outline, Info, XMP and gates on
small PDFs built here with pypdf. No browser."""
import re

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DecodedStreamObject, DictionaryObject, NameObject, NumberObject, TextStringObject

from mdbindery import pdfnav
from mdbindery.build import BuildError

HTML = '''<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8" /><title>Книга</title></head>
<body>
<section class="pdf-cover"><img src="cover.png" alt="Книга" id="cover-img"></section>
<header id="title-block-header">
<h1 class="title">Книга</h1>
<p class="author">Автор</p>
</header>
<nav id="TOC" role="doc-toc">
<h2 id="toc-title">Содержание</h2>
<ul>
<li><a href="#%D0%B3%D0%BB%D0%B0%D0%B2%D0%B0" id="toc-глава">Глава <em>первая</em></a>
<ul>
<li><a href="#with.dot" id="toc-with.dot">Точка</a></li>
</ul></li>
<li><a href="#second" id="toc-second">Вторая</a></li>
</ul>
</nav>
<h1 id="глава">Глава <em>первая</em></h1>
<p>Текст.</p>
<h2 id="with.dot">Точка</h2>
<h1 id="second" class="unnumbered">Вторая</h1>
</body></html>
'''


def prepared(tmp_path, text=HTML, rights='© 2026 «Автор» & <co>'):
    path = tmp_path / 'book.html'
    path.write_text(text, encoding='utf-8')
    entries, has_nav = pdfnav.prepare(path, rights)
    return path.read_text(encoding='utf-8'), entries, has_nav


def test_prepare_marks_the_contents_links_and_adds_only_the_rights_line(tmp_path):
    out, entries, has_nav = prepared(tmp_path)
    assert has_nav
    assert [(e['depth'], e['key'], e['target']) for e in entries] == [
        (1, 'mdb-dest-1', 'глава'), (2, 'mdb-dest-2', 'with.dot'), (1, 'mdb-dest-3', 'second')]
    assert '<h1 id="глава">Глава <em>первая</em></h1>' in out and '<h2 id="with.dot">Точка</h2>' in out   # nothing inside a heading
    assert '<a href="#second" id="toc-second">Вторая</a>' in out   # the contents links stay exactly as pandoc wrote them
    assert '<p class="rights" id="mdb-rights">© 2026 «Автор» &amp; &lt;co&gt;</p></header>' in out
    undone = re.sub(r'<p class="rights" id="mdb-rights">.*?</p>(?=</header>)', '', out)
    assert undone == HTML   # only the marks and the rights line differ


def test_prepare_without_contents_or_rights_changes_nothing(tmp_path):
    text = re.sub(r'<nav id="TOC".*?</nav>\n', '', HTML, flags=re.S)
    out, entries, has_nav = prepared(tmp_path, text, rights='')
    assert (entries, has_nav, out) == ([], False, text)


@pytest.mark.parametrize('change, message', [
    (lambda t: t.replace('href="#second"', 'href="#missing"'), "points to 'missing'"),
    (lambda t: t.replace('href="#second"', 'href="#toc-title"'), "points to 'toc-title'"),   # inside the contents
    (lambda t: t.replace('href="#second"', 'href="#cover-img"'), "points to 'cover-img'"),   # a void element in the cover
    (lambda t: t.replace('href="#second"', 'href="#title-block-header"'), "points to 'title-block-header'"),   # a region's own root
    (lambda t: t.replace('href="#second"', 'href="#TOC"'), "points to 'TOC'"),
    (lambda t: t.replace('<section class="pdf-cover">', '<section class="pdf-cover" id="cover-root">').replace('href="#second"', 'href="#cover-root"'),
     "points to 'cover-root'"),
    (lambda t: t.replace('<p>Текст.</p>', '<p id="mdb-rights">Текст.</p>'), "rights line takes"),   # with a rights line
    (lambda t: t.replace('<header id="title-block-header">', '<header>'), 'no title block'),
])
def test_prepare_refuses_what_it_cannot_anchor(tmp_path, change, message):
    with pytest.raises(BuildError, match=message):
        prepared(tmp_path, change(HTML))


def test_prepare_accepts_other_ids_that_start_with_mdb(tmp_path):
    for ident, rights in (('mdb-tools', 'R'), ('mdb-toc', 'R'), ('mdb-dest-1', 'R'), ('mdb-rights', '')):
        out, entries, _ = prepared(tmp_path, HTML.replace('<p>Текст.</p>', f'<p id="{ident}">Текст.</p>'), rights=rights)
        assert f'<p id="{ident}">Текст.</p>' in out and len(entries) == 3   # pandoc makes mdb-tools from "# MDB Tools"; the
        # entries' keys are never ids, and with no rights line nothing takes mdb-rights


def test_join_entries_takes_the_pages_anchors_and_labels_and_stops_on_a_hidden_heading():
    entries = [{'depth': 1, 'key': 'mdb-dest-1', 'target': 'a'}, {'depth': 2, 'key': 'mdb-dest-2', 'target': 'b'}]
    page = [{'id': 'mdb-dest-1', 'anchor': 'a', 'label': 'Energy E=mc2', 'printed': True},
            {'id': 'mdb-dest-2', 'anchor': 'mdb-dest-2', 'label': 'B', 'printed': True}]   # a heading with no box: its span
    joined = pdfnav.join_entries(entries, page)
    assert [(e['anchor'], e['label']) for e in joined] == [('a', 'Energy E=mc2'), ('mdb-dest-2', 'B')]
    with pytest.raises(BuildError, match='other contents entries'):
        pdfnav.join_entries(entries, page[:1])
    with pytest.raises(BuildError, match="«B» points to a heading that isn't printed"):
        pdfnav.join_entries(entries, [page[0], dict(page[1], printed=False)])
    with pytest.raises(BuildError, match='«B» is hidden in the printed contents'):
        pdfnav.join_entries(entries, [page[0], dict(page[1], listed=False)])
    with pytest.raises(BuildError, match=r'«B» shows text that print CSS generates with counter\(n\)'):
        pdfnav.join_entries(entries, [page[0], dict(page[1], unresolved=['counter(n)'])])


def make_pdf(path, pages, dests=()):
    """A PDF of text pages (one line each, Helvetica) with named destinations {name: (page, top)} in /Names/Dests."""
    writer = PdfWriter()
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'),
                             NameObject('/BaseFont'): NameObject('/Helvetica')})
    font_ref = writer._add_object(font)
    for lines in pages:
        page = writer.add_blank_page(612, 792)
        body = ''.join(f'BT /F1 12 Tf 72 {720 - 20 * k} Td ({line}) Tj ET\n' for k, line in enumerate(lines))
        content = DecodedStreamObject()
        content.set_data(body.encode('latin-1'))
        page[NameObject('/Contents')] = writer._add_object(content)
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): font_ref})})
    for name, (index, top) in dests:
        array = ArrayObject([writer.pages[index].indirect_reference, NameObject('/XYZ'), NumberObject(0), NumberObject(top), NumberObject(0)])
        names = writer._root_object.setdefault(NameObject('/Dests'), DictionaryObject())
        names[NameObject('/' + name)] = array
    writer._root_object[NameObject('/Lang')] = TextStringObject('en')
    with open(path, 'wb') as out:
        writer.write(out)


META = {'title': 'A & B <c> "d" \'e\'', 'authors': ['Ann & Bo', 'Ёж <Колючий>'], 'description': 'Desc & "more"',
        'subjects': ['One', 'Two & three'], 'rights': '© 2026 "R" & <S>', 'publisher': 'P & Q', 'lang': 'en'}


def built(tmp_path, pages=None, entries=None, meta=META, has_nav=True):
    pages = pages or [['cover'], ['A & B <c> "d" \'e\'', '2026 "R" & <S>'], ['Contents'], ['Chapter One'], ['Part', 'Chapter One']]
    dests = [(pdfnav.TITLE, (1, 700)), (pdfnav.RIGHTS, (1, 680)), (pdfnav.CONTENTS, (2, 700)),
             ('mdb-dest-1', (3, 720)), ('mdb-dest-2', (4, 700)), ('mdb-dest-3', (4, 680))]
    source, final = tmp_path / 'chrome.pdf', tmp_path / 'final.pdf'
    make_pdf(source, pages, dests)
    entries = entries if entries is not None else [
        {'depth': 1, 'anchor': 'mdb-dest-1', 'label': 'Chapter One'}, {'depth': 2, 'anchor': 'mdb-dest-2', 'label': 'Part'},
        {'depth': 4, 'anchor': 'mdb-dest-3', 'label': 'Chapter One'}]   # a repeated title, two entries on one page, a skipped level
    rows, pages_of = pdfnav.project(PdfReader(source), entries, has_nav, meta['rights'])
    pdfnav.finalize(source, final, rows, meta)
    return final, rows, pages_of


def test_outline_metadata_and_front_matter_pass_on_a_faithful_file(tmp_path):
    final, rows, pages_of = built(tmp_path)
    assert pages_of == {pdfnav.TITLE: 1, pdfnav.RIGHTS: 1, pdfnav.CONTENTS: 2}
    assert [r[:3] for r in rows] == [('Chapter One', 1, 3), ('Part', 2, 4), ('Chapter One', 3, 4)]   # level 4 nests at tree depth 3
    outline, front, metadata = pdfnav.gates(final, rows, META, 'Contents', True, META['rights'])
    assert (outline['result'], front['result'], metadata['result']) == ('pass', 'pass', 'pass'), (outline, front, metadata)
    reader = PdfReader(final)
    assert reader.metadata['/Author'] == 'Ann & Bo; Ёж <Колючий>' and reader.metadata['/Keywords'] == 'One, Two & three'
    xmp = reader.trailer['/Root']['/Metadata'].get_object().get_data().decode('utf-8')
    assert '<rdf:li>Ёж &lt;Колючий&gt;</rdf:li>' in xmp and 'xml:lang="en">Desc &amp; "more"<' in xmp
    nested = reader.outline
    assert isinstance(nested[1], list) and isinstance(nested[1][1], list)   # Part under Chapter One, the repeated title under Part


def test_empty_optional_metadata_is_left_out(tmp_path):
    meta = dict(META, authors=[], description='', subjects=[], rights='', publisher='')
    final, rows, _ = built(tmp_path, meta=meta)
    reader = PdfReader(final)
    assert not {'/Author', '/Subject', '/Keywords'} & set(reader.metadata)
    xmp = reader.trailer['/Root']['/Metadata'].get_object().get_data().decode('utf-8')
    assert 'dc:creator' not in xmp and 'dc:rights' not in xmp and 'dc:publisher' not in xmp
    assert pdfnav.gates(final, rows, meta, 'Contents', True, '')[2]['result'] == 'pass'


@pytest.mark.parametrize('alter', [
    lambda rows: [('Chapter 1',) + rows[0][1:]] + rows[1:],   # a wrong label
    lambda rows: rows[:2] + [rows[2][:1] + (1,) + rows[2][2:]],   # a wrong depth
    lambda rows: [rows[0][:2] + (2,) + rows[0][3:]] + rows[1:],   # a wrong but valid page
    lambda rows: [rows[0][:4] + ((0.0, 500.0, 0.0),)] + rows[1:],   # an altered fit
])
def test_the_outline_gate_fails_on_any_difference_from_the_projection(tmp_path, alter):
    final, rows, _ = built(tmp_path)
    written = tmp_path / 'altered.pdf'
    pdfnav.finalize(tmp_path / 'chrome.pdf', written, alter(rows), META)
    assert pdfnav.gates(written, rows, META, 'Contents', True, META['rights'])[0]['result'] == 'fail'


def test_a_label_not_on_its_destination_page_fails(tmp_path):
    entries = [{'depth': 1, 'anchor': 'mdb-dest-1', 'label': 'Elsewhere'}]
    final, rows, _ = built(tmp_path, entries=entries)
    outline = pdfnav.gates(final, rows, META, 'Contents', True, META['rights'])[0]
    assert outline['result'] == 'fail' and 'does not begin on its destination page' in outline['problems'][0]


def test_the_front_matter_gate_finds_each_part_by_its_locator(tmp_path):
    pages = [['cover'], ['A & B <c> "d" \'e\''], ['Contents'], ['Chapter One'], ['Part', 'Chapter One']]   # no rights text
    final, rows, _ = built(tmp_path, pages=pages)
    front = pdfnav.gates(final, rows, META, 'Contents', True, META['rights'])[1]
    assert front['problems'] == ['the rights line is not on the title page']
    front = pdfnav.gates(final, rows, META, 'Inhalt', True, META['rights'])[1]
    assert 'the contents heading is not on the first contents page' in front['problems']
    front = pdfnav.gates(final, rows, META, '', True, '')[1]
    assert front['result'] == 'pass' and len(front['not_applicable']) == 2


def test_no_contents_writes_no_outline(tmp_path):
    final, rows, _ = built(tmp_path, entries=[], has_nav=False)
    assert rows == [] and PdfReader(final).outline == []
    outline, front, _ = pdfnav.gates(final, rows, META, '', False, META['rights'])
    assert outline['result'] == 'pass' and front['result'] == 'pass'


def test_a_missing_destination_is_a_finalization_error(tmp_path):
    source = tmp_path / 'chrome.pdf'
    make_pdf(source, [['a'], ['b']], [(pdfnav.TITLE, (1, 700))])
    with pytest.raises(BuildError, match='no destination for contents entry «X»'):
        pdfnav.project(PdfReader(source), [{'depth': 1, 'anchor': 'mdb-dest-1', 'label': 'X'}], False, '')
    with pytest.raises(BuildError, match='mdb-rights locator'):
        pdfnav.project(PdfReader(source), [], False, 'rights')


def test_destination_names_are_normalized_by_their_pdf_type():
    class Reader:
        named_destinations = {NameObject('/mdb-dest-1'): 'a', TextStringObject('%D0%B3%D0%BB'): 'b', NameObject('/with.dot'): 'c'}
    assert pdfnav.named_destinations(Reader()) == {'mdb-dest-1': 'a', 'гл': 'b', 'with.dot': 'c'}


def test_an_alias_finds_chromes_encoded_destination_name(tmp_path):
    source, final = tmp_path / 'chrome.pdf', tmp_path / 'final.pdf'
    make_pdf(source, [['Contents'], ['Chapter']], [('%D1%82%20x', (1, 700))])   # the anchor's id is «т x»
    writer = PdfWriter(clone_from=PdfReader(source))
    link = DictionaryObject({NameObject('/Type'): NameObject('/Annot'), NameObject('/Subtype'): NameObject('/Link'),
                             NameObject('/Rect'): ArrayObject([NumberObject(v) for v in (72, 700, 200, 720)]),
                             NameObject('/Dest'): NameObject('/second')})   # the printed contents link to the heading
    writer.pages[0][NameObject('/Annots')] = ArrayObject([writer._add_object(link)])
    with open(source, 'wb') as out:
        writer.write(out)
    pdfnav.finalize(source, final, [], META, aliases={'second': 'т x'})
    named = pdfnav.named_destinations(PdfReader(final))
    assert PdfReader(final).get_destination_page_number(named['second']) == 1


def test_the_print_without_locator_links_must_match_page_for_page(tmp_path):
    a, b, c, d = (tmp_path / f'{n}.pdf' for n in 'abcd')
    make_pdf(a, [['One'], ['Two']], [(pdfnav.TITLE, (0, 700))])   # destinations alone are no difference
    make_pdf(b, [['One'], ['Two']])
    make_pdf(c, [['One'], ['Two!']])
    make_pdf(d, [['One']])
    assert pdfnav.changed_page(a, b) is None
    assert pdfnav.changed_page(a, c) == 2
    assert pdfnav.changed_page(a, d) == 0


def test_a_wrong_metadata_field_fails_the_metadata_gate(tmp_path):
    final, rows, _ = built(tmp_path)
    assert pdfnav.gates(final, rows, dict(META, title='Another'), 'Contents', True, META['rights'])[2]['result'] == 'fail'


def contents_problems(tmp_path, pages, heads, listed, markers=None, before='', page_numbers=True, title_page=1, contents_page=2,
                      runs=None):
    """The outline gate's contents-text problems for text pages made here: heads are (label, page) per entry."""
    source, final = tmp_path / 'chrome.pdf', tmp_path / 'final.pdf'
    dests = [(pdfnav.TITLE, (title_page, 700)), (pdfnav.CONTENTS, (contents_page, 690))] + [
        (f'mdb-dest-{n}', (page, 600)) for n, (_, page) in enumerate(heads, 1)]
    make_pdf(source, pages, dests)
    entries = [{'depth': 1, 'anchor': f'mdb-dest-{n}', 'label': label} for n, (label, _) in enumerate(heads, 1)]
    rows, _ = pdfnav.project(PdfReader(source), entries, True, '')
    meta = dict(META, rights='')
    pdfnav.finalize(source, final, rows, meta)
    outline = pdfnav.gates(final, rows, meta, 'Contents', True, '', printed=[label for label, _ in heads], listed=listed,
                           markers=markers, before=before, page_numbers=page_numbers, runs=runs)[0]
    return [p for p in outline['problems'] if 'printed contents' in p], outline['not_checked']


def test_the_contents_gate_reads_the_entries_with_their_own_markers(tmp_path):
    pages = [['cover'], ['Title'], ['Contents', 'a. First', 'b. Second'], ['First', 'Text.'], ['Second', 'Text.']]
    heads = [('First', 3), ('Second', 4)]
    assert contents_problems(tmp_path, pages, heads, ['First', 'Second'], ['a', 'b'])[0] == []
    assert contents_problems(tmp_path, pages, heads, ['First', 'Second'], ['', ''])[0] != []   # markers are not optional


def test_the_contents_gate_never_borrows_an_entry_from_the_text_after_the_contents(tmp_path):
    pages = [['cover'], ['Title'], ['Contents', 'One', 'One', 'Betaword appears here.'], ['Betaword', 'Text.']]   # shared page
    problems, _ = contents_problems(tmp_path, pages, [('One', 2), ('Betaword', 3)], ['One', 'Betaword'], ['', ''])
    assert problems and 'Betaword' in problems[0]
    pages = [['cover'], ['Title'], ['Contents', '1', 'Betaword appears here.'], ['Betaword', 'Text.']]   # a numeric heading
    problems, _ = contents_problems(tmp_path, pages, [('1', 2), ('Betaword', 3)], ['1', 'Betaword'], ['', ''])
    assert problems


def test_the_contents_gate_takes_the_heading_on_its_own_page_for_no_entry(tmp_path):
    pages = [['cover'], ['Title'], ['Contents'], ['Alphaword', 'Text.']]   # the one entry missing from the contents
    problems, _ = contents_problems(tmp_path, pages, [('Alphaword', 3)], ['Alphaword'], [''])
    assert problems and 'Alphaword' in problems[0]


def test_the_contents_gate_strips_footers_only_on_numbered_pages(tmp_path):
    pages = [['cover'], ['Title'], ['Contents', 'First', 'Second', '3'], ['First'], ['Second'], ['3']]
    heads = [('First', 3), ('Second', 4), ('3', 5)]
    assert contents_problems(tmp_path, pages, heads, ['First', 'Second', '3'], ['', '', ''], page_numbers=False)[0] == []


def test_the_contents_gate_skips_a_title_block_it_shares_a_page_with(tmp_path):
    pages = [['cover'], ['Book title', 'Rights line', 'Contents', 'First'], ['First', 'Text.']]
    problems, _ = contents_problems(tmp_path, pages, [('First', 2)], ['First'], [''], before='Book title Rights line',
                                    title_page=1, contents_page=1)
    assert problems == []


def test_the_contents_gate_does_not_guess_markers_it_cannot_spell(tmp_path):
    pages = [['cover'], ['Title'], ['Contents', 'alpha First'], ['First']]
    problems, skipped = contents_problems(tmp_path, pages, [('First', 3)], ['First'], [None])
    assert problems == [] and any('list marker' in n for n in skipped)


def test_the_contents_gate_reads_outline_text_in_place_and_the_entries_after_it(tmp_path):
    heads, listed = [('Map of Mars today', 3), ('Second', 4)], ['Map today', 'Second']   # «of Mars» drawn only as an outline
    runs = [[('Map ', False), ('of Mars', True), (' today', False)], None]
    pages = [['cover'], ['Title'], ['Contents', 'Map of Marsof Mars today', 'Second'], ['Map of Mars today', 'Text.'], ['Second', 'Text.']]
    assert contents_problems(tmp_path, pages, heads, listed, ['', ''], runs=runs) == ([], [])
    whole = [[('Map ', True), ('of Mars', True), (' today', True)], None]   # all of it, each piece written twice
    pages[2] = ['Contents', 'Map Map of Marsof Mars today today', 'Second']
    assert contents_problems(tmp_path, pages, heads, ['', 'Second'], ['', ''], runs=whole) == ([], [])
    pages[2] = ['Contents', 'Map of Marsof Mars today']   # the entry after it is missing
    problems, _ = contents_problems(tmp_path, pages, heads, listed, ['', ''], runs=runs)
    assert len(problems) == 1 and '«Second»' in problems[0]
    pages[2] = ['Contents', 'Map today', 'of Marsof Mars', 'Second']   # outline text elsewhere: the filled words, then the next
    problems, skipped = contents_problems(tmp_path, pages, heads, listed, ['', ''], runs=runs)
    assert problems == [] and any('arranged in a way' in n for n in skipped)
    pages[2] = ['Contents', 'of Marsof Mars today', 'Second']   # a filled word missing
    problems, _ = contents_problems(tmp_path, pages, heads, listed, ['', ''], runs=runs)
    assert len(problems) == 1 and '«Map of Mars today»' in problems[0]


def test_the_contents_gate_does_not_take_an_outlined_entrys_copy_for_the_next_entry(tmp_path):
    heads, listed, markers = [('2 Second', 3), ('Second', 4)], ['', 'Second'], ['1', '2']
    runs = [[('2 Second', True)], None]   # the first entry, all outline, reads «2 Second» like marker 2 and «Second»
    pages = [['cover'], ['Title'], ['Contents', '1 2 Second2 Second'], ['2 Second', 'Text.'], ['Second', 'Text.']]
    problems, skipped = contents_problems(tmp_path, pages, heads, listed, markers, runs=runs)   # written twice, or once and
    assert problems == [] and any(n.startswith('«Second»: the outlined entry before it') for n in skipped)   # then «2 Second»
    pages[2] = ['Contents', '1 2 Second2 Second', '2 Second']   # twice, then the next entry: each in its own place
    assert contents_problems(tmp_path, pages, heads, listed, markers, runs=runs) == ([], [])


def test_reading_repeated_outline_pieces_costs_their_text_not_their_combinations():
    import time
    started = time.monotonic()
    ends = pdfnav._outlined_ends('a' * 48, 0, [('a', True)] * 24)   # 2**24 copy choices, 25 distinct ends
    assert ends == list(range(48, 23, -1)) and time.monotonic() - started < 1
