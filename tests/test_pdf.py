"""PDF integration and EPUB compatibility checks. Never build source fixtures in place."""
import json
import re
import unicodedata
import urllib.parse
import os
from pathlib import Path

import pytest
from PIL import Image
from pypdf import PdfReader, PdfWriter

from conftest import EXAMPLES, FIXTURES, needs_pandoc, validate_if_installed
from mdbindery import config, pdfnav, tools
from mdbindery.build import BuildError, build
from mdbindery.cli import main, parser
from mdbindery.pdf import validate_pdf


def quiet(*args):
    pass


@pytest.fixture
def browser(monkeypatch):
    try:
        tools.puppeteer_runtime()
    except RuntimeError:
        if os.environ.get('MDBINDERY_REQUIRE_TOOLS'):
            pytest.fail('PDF tests require installed Node/Puppeteer')
        pytest.skip('Node/Puppeteer not installed')
    # The CI runner already disables Chromium sandbox for Mermaid/Ace. PDF requires explicit opt-out.
    if os.environ.get('CI') or (hasattr(os, 'geteuid') and os.geteuid() == 0):
        monkeypatch.setenv('MDBINDERY_NO_SANDBOX', '1')


def small_book(tmp_path, body='Visible paragraph with words that must survive export.'):
    book = tmp_path / 'book'
    book.mkdir()
    (book / '01-chapter.md').write_text('# First chapter\n\n' + body + '\n', encoding='utf-8')
    (book / 'mdbindery.yaml').write_text('metadata:\n  title: A PDF book\n  identifier: urn:uuid:test\n'
                                       '  date: 2026-09-26\noptions:\n  mermaid: placeholder\n', encoding='utf-8')
    return config.load(book)


@pytest.mark.parametrize('settings', [None, False, [], {'page_size': 'A3'}, {'margin_mm': 0},
                                      {'margin_mm': 100}, {'margin_mm': float('nan')},
                                      {'page_numbers': 'perhaps'}])
def test_pdf_settings_reject_invalid_values(settings):
    data = config.deep_merge(config.DEFAULTS, {'options': {'pdf': settings}})
    with pytest.raises(config.ConfigError, match='options.pdf'):
        config.validate(data)


def test_pdf_cli_is_opt_in():
    assert parser().parse_args(['build']).format == 'epub'
    assert parser().parse_args(['build', '--format', 'pdf']).format == 'pdf'
    with pytest.raises(SystemExit):
        parser().parse_args(['build', '--format', 'docx'])


@needs_pandoc
def test_missing_browser_keeps_old_pdf_and_epub_reports(tmp_path, monkeypatch):
    cfg = small_book(tmp_path)
    out = tmp_path / 'out'
    (out / 'reports').mkdir(parents=True)
    old = out / f'{cfg["slug"]}.pdf'
    old.write_bytes(b'previous PDF')
    (out / 'reports' / 'build.json').write_text('EPUB report')
    monkeypatch.setattr(tools, 'puppeteer_runtime', lambda: (_ for _ in ()).throw(RuntimeError('missing browser')))
    with pytest.raises(BuildError, match='missing browser'):
        build(cfg, out_dir=out, output_format='pdf', log=quiet)
    report = json.loads((out / 'reports' / 'pdf' / 'build.json').read_text())
    assert report['failed_stage'] == 'pdf_dependencies'
    assert 'earlier build' in report['artifact']
    assert old.read_bytes() == b'previous PDF'
    assert (out / 'reports' / 'build.json').read_text() == 'EPUB report'


def test_pdf_rejects_empty_document(tmp_path):
    path = tmp_path / 'empty.pdf'
    PdfWriter().write(path)
    with pytest.raises(BuildError, match='PDF cannot be read'):
        validate_pdf(path, 'Expected content', config.DEFAULTS['options'])


@needs_pandoc
def test_epub_never_calls_pdf_renderer(copy_book, tmp_path, monkeypatch):
    from mdbindery import pdf
    def forbidden(*args, **kwargs):
        pytest.fail('EPUB must not use PDF dependencies or renderer')
    monkeypatch.setattr(pdf, 'requirements', forbidden)
    monkeypatch.setattr(pdf, 'render', forbidden)
    cfg = validate_if_installed(config.load(copy_book(FIXTURES / 'ru-book')))
    cfg.opts['mermaid'] = 'placeholder'
    summary = build(cfg, out_dir=tmp_path / 'out', run_ace=False, log=quiet)
    assert summary['ok'] and 'pdf' not in summary
    assert set(summary['gates']) >= {'wordcount', 'epubcheck', 'ace'}


@needs_pandoc
def test_pdf_sample_and_epub_can_share_output(copy_book, tmp_path, browser):
    from mdbindery.preview import preview
    cfg = validate_if_installed(config.load(copy_book(EXAMPLES / 'sample-book')))
    out = tmp_path / 'out'
    epub = build(cfg, out_dir=out, run_ace=False, log=quiet)
    epub_bytes = Path(epub['epub']).read_bytes()
    report_bytes = (out / 'reports' / 'build.json').read_bytes()
    summary = build(cfg, out_dir=out, output_format='pdf', log=quiet)
    assert summary['ok'], summary
    assert 'epubcheck' not in summary['gates'] and 'ace' not in summary['gates']
    assert Path(epub['epub']).read_bytes() == epub_bytes
    assert (out / 'reports' / 'build.json').read_bytes() == report_bytes
    assert (out / 'reports' / 'pdf' / 'build.json').is_file()
    reader = PdfReader(summary['pdf'])
    text = '\n'.join(p.extract_text() or '' for p in reader.pages)
    assert len(reader.pages) >= 5
    assert 'Writing a Book in Markdown' in text and 'Sample Author' in text
    assert 'Contributing' not in text
    assert 'Why Markdown' in text and 'Checklist' in text
    assert any('/XObject' in p['/Resources'] for p in reader.pages)
    annotations = [a.get_object() for p in reader.pages for a in p.get('/Annots', [])]
    assert any(a.get('/Dest') or a.get('/A', {}).get('/S') == '/GoTo' for a in annotations)
    assert any(a.get('/A', {}).get('/S') == '/URI' for a in annotations)
    # Reused browser discovery must still produce actual EPUB screenshots.
    shots = preview(epub['epub'], tmp_path / 'shots', pages=['text/ch001.xhtml'])
    assert shots and Path(shots[0]).read_bytes().startswith(b'\x89PNG')
    strict = dict(cfg.opts, wordcount_tolerance=0, wordcount_min_words=0)
    check = validate_pdf(summary['pdf'], text + ' MISSING_SENTINEL_XYZ', strict)
    assert check['result'] == 'fail' and check['missing_words'] >= 1


@needs_pandoc
def test_pdf_russian_unicode_paths_letter_and_no_page_numbers(copy_book, tmp_path, browser):
    book = copy_book(FIXTURES / 'ru-book')
    moved = tmp_path / 'Книга с пробелами'
    book.rename(moved)
    cfg = config.load(moved)
    cfg.opts['pdf'].update(page_size='Letter', margin_mm=15, page_numbers=False)
    summary = build(cfg, out_dir=tmp_path / 'Выход с пробелами', output_format='pdf', log=quiet)
    assert summary['ok'], summary
    reader = PdfReader(summary['pdf'])
    text = '\n'.join(p.extract_text() or '' for p in reader.pages)
    assert 'Пробная книга' in text and '[Milchin]' in text and 'кавычками' in text
    assert float(reader.pages[0].mediabox.width) == pytest.approx(612, abs=1)
    assert float(reader.pages[0].mediabox.height) == pytest.approx(792, abs=1)


@needs_pandoc
@pytest.mark.parametrize('resource', ['https://example.invalid/blocked.png', 'file:///etc/passwd'])
def test_pdf_blocks_css_resource_reads_and_preserves_previous_output(tmp_path, browser, resource):
    cfg = small_book(tmp_path)
    css = cfg.base / 'bad.css'
    css.write_text('body { background-image: url("' + resource + '"); }')
    cfg.opts['extra_css'] = str(css)
    out = tmp_path / 'out'
    out.mkdir()
    previous = out / f'{cfg["slug"]}.pdf'
    previous.write_bytes(b'previous PDF')
    with pytest.raises(BuildError, match='PDF resources or internal links failed'):
        build(cfg, out_dir=out, output_format='pdf', log=quiet)
    assert previous.read_bytes() == b'previous PDF'
    assert not list(out.glob('*.part'))
    report = json.loads((out / 'reports' / 'pdf' / 'build.json').read_text())
    assert not report['ok'] and report['failed_stage'] == 'pdf'


@needs_pandoc
def test_pdf_cli_failure_writes_separate_log(tmp_path, monkeypatch):
    cfg = small_book(tmp_path)
    monkeypatch.setattr(tools, 'puppeteer_runtime', lambda: (_ for _ in ()).throw(RuntimeError('missing browser')))
    out = tmp_path / 'out'
    assert main(['build', str(cfg.base), '--format', 'pdf', '--out', str(out), '--quiet']) == 2
    assert 'missing browser' in (out / 'reports' / 'pdf' / 'build.log').read_text()


@needs_pandoc
def test_pdf_literal_metadata_and_script_input(tmp_path, browser):
    cfg = small_book(tmp_path, 'Text with [a link](#first-chapter).\n\n<script>throw new Error("RUN");</script>')
    cfg.meta['title'] = 'Using <div> & C_sharp_ [draft]'
    cfg.opts['toc'] = False
    summary = build(cfg, out_dir=tmp_path / 'out', output_format='pdf', log=quiet)
    assert summary['ok'], summary
    reader = PdfReader(summary['pdf'])
    text = '\n'.join(p.extract_text() or '' for p in reader.pages)
    assert cfg.meta['title'] in text
    assert 'throw new Error' not in text


@needs_pandoc
def test_pdf_hidden_body_fails_text_gate(tmp_path, browser):
    cfg = small_book(tmp_path, ' '.join('word' + str(i) for i in range(100)))
    css = cfg.base / 'hide.css'
    css.write_text('body { visibility: hidden; }')
    cfg.opts['extra_css'] = str(css)
    cfg.opts['toc'] = False   # with contents, the hidden chapter heading stops the build first (the next test)
    summary = build(cfg, out_dir=tmp_path / 'out', output_format='pdf', log=quiet)
    assert not summary['ok'] and summary['gates']['pdf']['result'] == 'fail'
    assert summary['gates']['pdf']['missing_words'] >= 100


@needs_pandoc
def test_pdf_contents_entry_for_a_hidden_heading_stops_the_build(tmp_path, browser):
    cfg = small_book(tmp_path)
    css = cfg.base / 'hide.css'
    css.write_text('h1:not(.title) { visibility: hidden; }')
    cfg.opts['extra_css'] = str(css)
    with pytest.raises(BuildError, match="isn't printed"):
        build(cfg, out_dir=tmp_path / 'out', output_format='pdf', log=quiet)
    assert not list((tmp_path / 'out').glob('*.pdf*'))   # no PDF, and no temporary file left


@needs_pandoc
def test_pdf_missing_font_is_a_build_error(tmp_path, browser):
    cfg = small_book(tmp_path)
    cfg.opts['embed_fonts'] = ['fonts/missing.ttf']
    with pytest.raises(BuildError, match='PDF asset not found'):
        build(cfg, out_dir=tmp_path / 'out', output_format='pdf', log=quiet)


@needs_pandoc
def test_pdf_does_not_automatically_disable_sandbox(tmp_path, browser, monkeypatch):
    from mdbindery import pdf
    cfg = small_book(tmp_path)
    monkeypatch.delenv('MDBINDERY_NO_SANDBOX', raising=False)
    monkeypatch.setattr(tools, 'no_sandbox', lambda: True)
    original = pdf.run
    launches = []
    def fail_browser(command, **kwargs):
        if str(command[1]).endswith('pdf.js'):
            launches.append(json.loads(Path(command[2]).read_text()))
            raise BuildError('No usable sandbox')
        return original(command, **kwargs)
    monkeypatch.setattr(pdf, 'run', fail_browser)
    with pytest.raises(BuildError, match='No usable sandbox'):
        build(cfg, out_dir=tmp_path / 'out', output_format='pdf', log=quiet)
    assert len(launches) == 1 and launches[0]['args'] == []


@needs_pandoc
def test_pdf_without_identifier_preserves_source_config(tmp_path, browser):
    cfg = small_book(tmp_path)
    path = cfg.base / 'mdbindery.yaml'
    path.write_text(path.read_text().replace('  identifier: urn:uuid:test\n', ''))
    before = path.read_bytes()
    cfg = config.load(cfg.base)
    assert not cfg.meta['identifier']
    summary = build(cfg, out_dir=tmp_path / 'out', output_format='pdf', log=quiet)
    assert summary['ok'], summary
    assert path.read_bytes() == before
    assert not cfg.meta['identifier']


@needs_pandoc
def test_pdf_missing_python_extra_fails_before_analysis(tmp_path, monkeypatch):
    import sys
    from mdbindery import build as pipeline
    cfg = small_book(tmp_path)
    def forbidden(*args, **kwargs):
        pytest.fail('Missing PDF dependencies must fail before chapter preparation')
    monkeypatch.setitem(sys.modules, 'pypdf', None)
    monkeypatch.setattr(pipeline, 'analyze', forbidden)
    out = tmp_path / 'out'
    with pytest.raises(BuildError, match='PDF needs pypdf'):
        build(cfg, out_dir=out, output_format='pdf', log=quiet)
    report = json.loads((out / 'reports' / 'pdf' / 'build.json').read_text())
    assert report['failed_stage'] == 'pdf_dependencies' and report['format'] == 'pdf'


@needs_pandoc
def test_epub_preview_with_symlinked_temp_directory(copy_book, tmp_path, browser, monkeypatch):
    from mdbindery import preview as preview_module
    cfg = validate_if_installed(config.load(copy_book(FIXTURES / 'ru-book')))
    summary = build(cfg, out_dir=tmp_path / 'out', run_ace=False, log=quiet)
    real = tmp_path / 'real-temp'
    real.mkdir()
    alias = tmp_path / 'temp-alias'
    try:
        alias.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip('Creating directory symlinks requires privileges on this system')
    original = preview_module.tempfile.mkdtemp
    def aliased_temp(**kwargs):
        return original(dir=alias, **kwargs)
    monkeypatch.setattr(preview_module.tempfile, 'mkdtemp', aliased_temp)
    shots = preview_module.preview(summary['epub'], tmp_path / 'shots', pages=['text/ch001.xhtml'])
    assert shots and Path(shots[0]).read_bytes().startswith(b'\x89PNG')
    assert not list(real.iterdir())


def nav_book(tmp_path, files, lang='ru', toc=True, toc_depth=2, toc_title='', rights='© 2026 «Автор» & Co', css='', extra=''):
    """A small book for the outline and metadata checks: each file is one chapter on its own page."""
    book = tmp_path / 'book'
    book.mkdir()
    for name, text in files.items():
        (book / name).write_text(text, encoding='utf-8')
    if css:
        (book / 'extra.css').write_text(css, encoding='utf-8')
    (book / 'mdbindery.yaml').write_text(
        'metadata:\n  title: "Навигация & <тест>"\n  authors: [Анна Первая, "Bo & Co"]\n  identifier: urn:uuid:test\n'
        f'  date: 2026-10-20\n  lang: {lang}\n  rights: {json.dumps(rights)}\n  description: "Описание & <ещё>"\n'
        '  subjects: [Марс, "A & B"]\n  publisher: Издатель\n'
        f'options:\n  mermaid: placeholder\n  toc: {str(toc).lower()}\n  toc_depth: {toc_depth}\n  toc_title: {json.dumps(toc_title)}\n'
        + ('  extra_css: extra.css\n' if css else '') + extra, encoding='utf-8')
    return config.load(book)


def outline_of(reader):
    out = []

    def walk(items, depth):
        for item in items:
            if isinstance(item, list):
                walk(item, depth + 1)
            else:
                out.append((str(item.title), depth, reader.get_destination_page_number(item)))
    walk(reader.outline, 1)
    return out


CHAPTERS = {'01.md': '# Первая глава\n\nТекст первой главы.\n\n## Раздел один\n\nЕщё текст.\n',
            '02.md': '# Вторая глава\n\nТекст второй главы.\n\n### Глубже\n\nСовсем глубоко.\n',
            '03.md': '# Третья глава\n\nТекст третьей главы.\n'}


@needs_pandoc
def test_pdf_outline_metadata_and_front_matter(tmp_path, browser):
    summary = build(nav_book(tmp_path, CHAPTERS), out_dir=tmp_path / 'out', output_format='pdf', log=quiet)
    assert summary['ok'], summary['gates']
    gates = summary['gates']
    assert [gates['pdf']['words']] + [gates['pdf'][k]['result'] for k in ('outline', 'front_matter', 'metadata')] == ['pass'] * 4
    reader = PdfReader(summary['pdf'])
    found = outline_of(reader)
    assert [(t, d) for t, d, _ in found] == [('Первая глава', 1), ('Раздел один', 2), ('Вторая глава', 1), ('Третья глава', 1)]
    pages = [p for _, _, p in found]
    assert pages[0] < pages[2] < pages[3] and pages[1] == pages[0]   # chapters on their own pages; the section on its chapter's
    for title, _, page in found:
        assert title in reader.pages[page].extract_text()
    info = reader.metadata
    assert (info['/Title'], info['/Author'], info['/Subject'], info['/Keywords']) == (
        'Навигация & <тест>', 'Анна Первая; Bo & Co', 'Описание & <ещё>', 'Марс, A & B')
    assert reader.trailer['/Root']['/Lang'] == 'ru' and '/StructTreeRoot' in reader.trailer['/Root']
    xmp = reader.trailer['/Root']['/Metadata'].get_object().get_data().decode('utf-8')
    assert '<rdf:Seq><rdf:li>Анна Первая</rdf:li><rdf:li>Bo &amp; Co</rdf:li></rdf:Seq>' in xmp and '<dc:publisher>' in xmp
    title_page = next(i for i, p in enumerate(reader.pages) if 'Навигация' in (p.extract_text() or ''))
    assert '© 2026 «Автор» & Co' in reader.pages[title_page].extract_text()
    assert 'Содержание' in reader.pages[title_page + 1].extract_text()
    links = sum(1 for p in reader.pages for a in (p.get('/Annots') or []) if a.get_object().get('/Subtype') == '/Link')
    assert links == 4   # the four contents links; the hidden locators add none


@needs_pandoc
@pytest.mark.parametrize('lang, toc_title, heading', [('de', 'Inhalt', 'Inhalt'), ('de', '', None), ('en-US', '', 'Contents')])
def test_pdf_contents_heading_follows_toc_title(tmp_path, browser, lang, toc_title, heading):
    summary = build(nav_book(tmp_path, CHAPTERS, lang=lang, toc_title=toc_title), out_dir=tmp_path / 'out', output_format='pdf', log=quiet)
    assert summary['ok'], summary['gates']
    front = summary['gates']['pdf']['front_matter']
    reader = PdfReader(summary['pdf'])
    contents = next(i for i, p in enumerate(reader.pages) if 'Первая глава' in (p.extract_text() or ''))
    if heading:
        assert heading in reader.pages[contents].extract_text() and not front['not_applicable'][1:]
    else:
        assert any('no title for this language' in n for n in front['not_applicable'])


@needs_pandoc
def test_pdf_without_contents_still_checks_the_rights_line(tmp_path, browser):
    summary = build(nav_book(tmp_path, CHAPTERS, toc=False), out_dir=tmp_path / 'out', output_format='pdf', log=quiet)
    assert summary['ok'], summary['gates']
    assert PdfReader(summary['pdf']).outline == []
    front = summary['gates']['pdf']['front_matter']
    assert front['result'] == 'pass' and any('contents disabled' in n for n in front['not_applicable'])


@needs_pandoc
@pytest.mark.parametrize('depth, entries', [(1, 3), (2, 4), (6, 5)])
def test_pdf_outline_follows_toc_depth(tmp_path, browser, depth, entries):
    summary = build(nav_book(tmp_path, CHAPTERS, toc_depth=depth), out_dir=tmp_path / 'out', output_format='pdf', log=quiet)
    assert summary['ok'], summary['gates']
    found = outline_of(PdfReader(summary['pdf']))
    assert len(found) == entries
    if depth == 6:
        assert ('Глубже', 2) in [(t, d) for t, d, _ in found]   # a skipped level nests under its chapter, as the contents does


@needs_pandoc
def test_pdf_repeated_titles_and_two_headings_on_one_page_keep_their_own_destinations(tmp_path, browser):
    files = {'01.md': '# Интерлюдия\n\nПервая.\n', '02.md': '# Интерлюдия\n\nВторая.\n\n## Альфа\n\nТекст.\n\n## Бета\n\nТекст.\n'}
    summary = build(nav_book(tmp_path, files), out_dir=tmp_path / 'out', output_format='pdf', log=quiet)
    assert summary['ok'], summary['gates']
    found = outline_of(PdfReader(summary['pdf']))
    assert [t for t, _, _ in found] == ['Интерлюдия', 'Интерлюдия', 'Альфа', 'Бета']
    assert found[0][2] < found[1][2] == found[2][2] == found[3][2]


@needs_pandoc
@pytest.mark.parametrize('heading', ['# Вторая глава', '# Вторая *глава*'])   # Markdown gives nothing inside a heading an id
def test_pdf_display_contents_heading_stops_the_build(tmp_path, browser, heading):
    chapters = dict(CHAPTERS, **{'02.md': CHAPTERS['02.md'].replace('# Вторая глава', heading)})
    with pytest.raises(BuildError, match='«Вторая глава» points to a heading with no box of its own'):
        build(nav_book(tmp_path, chapters, css='body > h1:nth-of-type(2) { display: contents; }'), out_dir=tmp_path / 'out',
              output_format='pdf', log=quiet)


@needs_pandoc
def test_pdf_navigation_gives_no_element_an_id_the_books_css_could_see(tmp_path, browser):
    files = {'01.md': '# Map *of Mars* today\n\nText.\n', '02.md': '# Second\n\nText.\n'}
    css = 'body > h1:first-of-type { display: contents; } body > h1 > [id] { display: none; }'   # an id would hide the em
    with pytest.raises(BuildError, match='no element in it that has both a box and an id'):
        build(nav_book(tmp_path, files, lang='en-US', css=css), out_dir=tmp_path / 'out', output_format='pdf', log=quiet)


@needs_pandoc
@pytest.mark.parametrize('css', ['nav#TOC a { -webkit-text-fill-color: transparent; -webkit-text-stroke: 1px black; }',
                                 'nav#TOC a::before { content: "Prefixword "; -webkit-text-fill-color: transparent; '
                                 '-webkit-text-stroke: 1px black; }'])   # a clear fill, a visible stroke, as text or generated
def test_pdf_outlined_contents_text_counts_as_drawn(tmp_path, browser, css):
    files = {'01.md': '# First\n\nText.\n', '02.md': '# Second\n\nText.\n'}
    summary = build(nav_book(tmp_path, files, lang='en-US', css=css), out_dir=tmp_path / 'out', output_format='pdf', log=quiet)
    assert summary['ok'], summary['gates']['pdf']
    assert summary['gates']['pdf']['outline']['not_checked'] == []   # read in place, the outline text as Chrome writes it


@needs_pandoc
def test_pdf_an_entry_partly_drawn_as_an_outline_keeps_the_contents_check(tmp_path, browser):
    files = {'01.md': '# Map *of Mars* today\n\nText.\n', '02.md': '# Second\n\nText.\n'}
    css = 'nav#TOC li:first-child em { -webkit-text-fill-color: transparent; -webkit-text-stroke: 1px black; }'
    summary = build(nav_book(tmp_path, files, lang='en-US', css=css), out_dir=tmp_path / 'out', output_format='pdf', log=quiet)
    assert summary['ok'], summary['gates']['pdf']
    assert summary['gates']['pdf']['outline']['not_checked'] == []   # the contents text was read, every entry in place


@needs_pandoc
def test_pdf_words_print_css_hides_in_the_contents_are_not_missing(tmp_path, browser):
    hidden = ' '.join(f'word{k}' for k in range(10))   # 30 words the contents leave out, over the 25-word floor
    files = {f'0{n}.md': f'# Part{n} *{hidden}*\n\nText.\n' for n in (1, 2, 3)}
    summary = build(nav_book(tmp_path, files, lang='en-US', css='nav#TOC em { display: none; }'), out_dir=tmp_path / 'out',
                    output_format='pdf', log=quiet)
    assert summary['ok'] and summary['gates']['pdf']['missing_words'] < 25, summary['gates']['pdf']
    assert [t for t, _, _ in outline_of(PdfReader(summary['pdf']))] == ['Part1', 'Part2', 'Part3']


@needs_pandoc
def test_pdf_a_heading_whose_text_is_generated_prints(tmp_path, browser):
    files = {'01.md': '# First\n\nText.\n', '02.md': '# Second\n\nText.\n'}
    css = 'h1[id$="first"] { font-size: 0; } h1[id$="first"]::before { content: "First"; font-size: 16px; }'   # only the
    summary = build(nav_book(tmp_path, files, lang='en-US', css=css), out_dir=tmp_path / 'out', output_format='pdf', log=quiet)
    assert summary['ok'], summary['gates']['pdf']   # generated copy of its words prints
    assert [t for t, _, _ in outline_of(PdfReader(summary['pdf']))] == ['First', 'Second']


@needs_pandoc
@pytest.mark.parametrize('css', [
    'nav#TOC li { visibility: hidden; list-style-type: decimal; } nav#TOC a { visibility: visible; }',   # the links print,
    'nav#TOC li { list-style-type: decimal; } nav#TOC li::marker { color: transparent; }',   # Chrome still writes these
])
def test_pdf_markers_are_expected_as_chrome_writes_them(tmp_path, browser, css):
    files = {'01.md': '# First\n\nText.\n', '02.md': '# Second\n\nText.\n'}   # the first case's markers do not; the second's
    summary = build(nav_book(tmp_path, files, lang='en-US', css=css), out_dir=tmp_path / 'out', output_format='pdf', log=quiet)
    assert summary['ok'], summary['gates']['pdf']   # numbers are unseen but in the page text
    assert summary['gates']['pdf']['outline']['not_checked'] == []


@needs_pandoc
@pytest.mark.parametrize('css', ['nav#TOC img { filter: grayscale(1); }', 'body > h1 img { filter: grayscale(1) blur(1px); }'])
def test_pdf_an_image_under_a_filter_that_keeps_it_visible_prints(tmp_path, browser, css):
    book = nav_book(tmp_path, {'01.md': '# ![Logo](logo.png)\n\nText.\n', '02.md': '# Second\n\nText.\n'}, lang='en-US', css=css)
    Image.new('RGB', (20, 20), 'white').save(book.base / 'logo.png')
    summary = build(book, out_dir=tmp_path / 'out', output_format='pdf', log=quiet)
    assert summary['ok'], summary['gates']['pdf']
    assert [t for t, _, _ in outline_of(PdfReader(summary['pdf']))] == ['Logo', 'Second']


@needs_pandoc
@pytest.mark.parametrize('css', ['nav#TOC img { object-fit: none; object-position: left top; }',
                                 'body > h1 img { width: 40px; object-fit: contain; object-position: 100% 0; }',
                                 'nav#TOC img { object-fit: none; object-position: calc(50% + 1px) 50%; }',
                                 'nav#TOC img { width: 40px; object-fit: none; object-position: right 2px bottom 2px; }',
                                 'nav#TOC a { display: inline-block; width: 80px; overflow: hidden; } '   # half the image
                                 'nav#TOC img { box-sizing: content-box; width: 20px; height: 20px; padding-left: 70px; }',
                                 'nav#TOC a { display: inline-block; width: 80px; overflow: hidden; } '   # scaled to half:
                                 'nav#TOC img { box-sizing: content-box; width: 20px; height: 20px; padding-left: 100px; '   # its
                                 'transform: scale(.5); transform-origin: left top; }',   # pixels at 50-60px, inside the link
                                 'nav#TOC img { transform: rotate(1deg); }'])   # rotated, pixels in place
def test_pdf_an_image_whose_content_stays_in_its_box_prints(tmp_path, browser, css):
    book = nav_book(tmp_path, {'01.md': '# ![Logo](logo.png)\n\nText.\n', '02.md': '# Second\n\nText.\n'}, lang='en-US', css=css)
    Image.new('RGB', (20, 20), 'white').save(book.base / 'logo.png')
    summary = build(book, out_dir=tmp_path / 'out', output_format='pdf', log=quiet)
    assert summary['ok'], summary['gates']['pdf']


@needs_pandoc
def test_pdf_a_space_of_no_size_stays_out_of_the_bookmark(tmp_path, browser):
    files = {'01.md': '# *A* *B*\n\nText.\n', '02.md': '# Second\n\nText.\n'}
    css = 'nav#TOC li:first-child a { font-size: 0; } nav#TOC em { font-size: 16px; }'   # the contents print «AB»
    summary = build(nav_book(tmp_path, files, lang='en-US', css=css), out_dir=tmp_path / 'out', output_format='pdf', log=quiet)
    assert summary['ok'], summary['gates']['pdf']
    assert [t for t, _, _ in outline_of(PdfReader(summary['pdf']))] == ['AB', 'Second']


@needs_pandoc
def test_pdf_a_title_print_css_generates_is_on_the_title_page(tmp_path, browser):
    css = ('header#title-block-header .title { font-size: 0; } '   # the configured title, drawn only as generated text
           'header#title-block-header .title::before { content: "Навигация & <тест>"; font-size: 16px; }')
    files = {'01.md': '# First\n\nText.\n', '02.md': '# Second\n\nText.\n'}
    summary = build(nav_book(tmp_path, files, css=css), out_dir=tmp_path / 'out', output_format='pdf', log=quiet)
    assert summary['ok'] and summary['gates']['pdf']['front_matter']['result'] == 'pass', summary['gates']['pdf']


@needs_pandoc
@pytest.mark.parametrize('ink', ['-webkit-text-stroke: 1px black;', 'text-shadow: 0 0 1px black;'])
def test_pdf_a_title_drawn_as_an_outline_or_a_shadow_is_its_own(tmp_path, browser, ink):
    css = f'header#title-block-header .title {{ -webkit-text-fill-color: transparent; {ink} }}'
    files = {'01.md': '# First\n\nText.\n', '02.md': '# Second\n\nText.\n'}
    summary = build(nav_book(tmp_path, files, css=css), out_dir=tmp_path / 'out', output_format='pdf', log=quiet)
    assert summary['ok'] and summary['gates']['pdf']['front_matter']['result'] == 'pass', summary['gates']['pdf']


@needs_pandoc
def test_pdf_the_title_must_be_drawn_by_the_title_itself(tmp_path, browser):
    css = ('header#title-block-header .title { font-size: 0; } '   # the title element draws other words; the title's own
           'header#title-block-header .title::before { content: "Unrelated"; font-size: 16px; }')   # are in the rights line
    files = {'01.md': '# First\n\nText.\n', '02.md': '# Second\n\nText.\n'}
    summary = build(nav_book(tmp_path, files, css=css, rights='Навигация & <тест> © 2026'), out_dir=tmp_path / 'out',
                    output_format='pdf', log=quiet)
    assert not summary['ok'] and 'the title is not on the title page' in summary['gates']['pdf']['front_matter']['problems']


@needs_pandoc
@pytest.mark.parametrize('lang, css, label', [
    ('en-US', 'nav#TOC a { text-transform: capitalize; }', 'North-East Wind.Of Mars'),   # words start after punctuation too
    ('x-private', 'nav#TOC a { text-transform: uppercase; }', 'NORTH-EAST WIND.OF MARS'),   # a tag casing rejects
])
def test_pdf_bookmark_case_follows_what_chrome_prints(tmp_path, browser, lang, css, label):
    files = {'01.md': '# north-east wind.of mars\n\nText.\n', '02.md': '# Second\n\nText.\n'}
    summary = build(nav_book(tmp_path, files, lang=lang, css=css), out_dir=tmp_path / 'out', output_format='pdf', log=quiet)
    assert summary['ok'], summary['gates']['pdf']
    reader = PdfReader(summary['pdf'])
    assert label in ''.join(p.extract_text() or '' for p in reader.pages)   # what Chrome printed in the contents
    assert [t for t, _, _ in outline_of(reader)][0] == label


@needs_pandoc
@pytest.mark.parametrize('css', [
    'nav#TOC a { text-transform: uppercase; } nav#TOC span { visibility: hidden; }',   # no span in the book: only a probe
    'nav#TOC a { visibility: hidden; text-transform: uppercase; } nav#TOC a::before { visibility: visible; } '   # would be
    'nav#TOC li:first-child a::before { content: "First"; } nav#TOC li:nth-child(2) a::before { content: "Second"; }',   # hidden
])
def test_pdf_case_is_read_whatever_hides_the_elements_around_it(tmp_path, browser, css):
    files = {'01.md': '# First\n\nText.\n', '02.md': '# Second\n\nText.\n'}
    summary = build(nav_book(tmp_path, files, lang='en-US', css=css), out_dir=tmp_path / 'out', output_format='pdf', log=quiet)
    assert summary['ok'], summary['gates']['pdf']
    assert [t for t, _, _ in outline_of(PdfReader(summary['pdf']))] == ['FIRST', 'SECOND']


@needs_pandoc
@pytest.mark.parametrize('heading, label', [('<em>e&#x301;</em>clair', 'ÉClair'), ('<strong>a&#x301;</strong>bc', 'ÁBc')])
def test_pdf_capitalize_after_a_combining_mark_matches_print(tmp_path, browser, heading, label):
    files = {'01.md': f'# {heading}\n\nText.\n', '02.md': '# Second\n\nText.\n'}   # a decomposed letter in its own element:
    css = 'nav#TOC a { text-transform: capitalize; }'   # Chrome starts a new word after the mark
    summary = build(nav_book(tmp_path, files, lang='en-US', css=css), out_dir=tmp_path / 'out', output_format='pdf', log=quiet)
    assert summary['ok'], summary['gates']['pdf']
    reader = PdfReader(summary['pdf'])
    assert label in unicodedata.normalize('NFC', ''.join(p.extract_text() or '' for p in reader.pages))   # what Chrome printed
    assert unicodedata.normalize('NFC', [t for t, _, _ in outline_of(reader)][0]) == label


@needs_pandoc
def test_pdf_the_title_element_must_hold_the_title_words_whole(tmp_path, browser):
    css = ('header#title-block-header .title { font-size: 0; } '   # its letters run on into a longer word: «тест» is
           'header#title-block-header .title::before { content: "Навигация тестовая"; font-size: 16px; }')   # not «тестовая»
    files = {'01.md': '# First\n\nText.\n', '02.md': '# Second\n\nText.\n'}
    summary = build(nav_book(tmp_path, files, css=css), out_dir=tmp_path / 'out', output_format='pdf', log=quiet)
    assert not summary['ok'] and 'the title is not on the title page' in summary['gates']['pdf']['front_matter']['problems']


@needs_pandoc
def test_pdf_lowercase_of_separate_pieces_matches_print(tmp_path, browser):
    files = {'01.md': '# *Ο*Σ\n\nText.\n', '02.md': '# Second\n\nText.\n'}   # Chrome lowercases each piece alone: no final sigma
    summary = build(nav_book(tmp_path, files, lang='el', css='nav#TOC a { text-transform: lowercase; }'), out_dir=tmp_path / 'out',
                    output_format='pdf', log=quiet)
    assert summary['ok'], summary['gates']['pdf']
    reader = PdfReader(summary['pdf'])
    assert 'οσ' in ''.join(p.extract_text() or '' for p in reader.pages)   # what Chrome printed
    assert [t for t, _, _ in outline_of(reader)][0] == 'οσ'


@needs_pandoc
def test_pdf_a_rights_line_of_symbols_alone_is_found(tmp_path, browser):
    files = {'01.md': '# First\n\nText.\n', '02.md': '# Second\n\nText.\n'}
    summary = build(nav_book(tmp_path, files, rights='©'), out_dir=tmp_path / 'out', output_format='pdf', log=quiet)
    assert summary['ok'] and summary['gates']['pdf']['front_matter']['result'] == 'pass', summary['gates']['pdf']


@needs_pandoc
def test_pdf_a_hidden_heading_with_a_visible_part_prints(tmp_path, browser):
    files = {'01.md': '# Map *of Mars* today\n\nText.\n', '02.md': '# Second\n\nText.\n'}
    css = 'h1:has(em) { visibility: hidden; } h1 em { visibility: visible; }'   # only «of Mars» prints; the heading has a box
    summary = build(nav_book(tmp_path, files, lang='en-US', css=css), out_dir=tmp_path / 'out', output_format='pdf', log=quiet)
    assert summary['ok'], summary['gates']['pdf']
    assert [t for t, _, _ in outline_of(PdfReader(summary['pdf']))] == ['Map of Mars today', 'Second']


@needs_pandoc
@pytest.mark.parametrize('css', ['header#title-block-header { display: contents; }', 'nav#TOC { display: contents; }'])
def test_pdf_front_matter_without_a_box_of_its_own_is_still_found(tmp_path, browser, css):
    summary = build(nav_book(tmp_path, CHAPTERS, css=css), out_dir=tmp_path / 'out', output_format='pdf', log=quiet)
    assert summary['ok'], summary['gates']['pdf']
    assert summary['gates']['pdf']['front_matter']['result'] == 'pass'


@needs_pandoc
@pytest.mark.parametrize('css, prose, veil', [
    ('body > h1:nth-of-type(2) { display: none; }', '', False),
    ('body > h1:nth-of-type(2) { visibility: hidden; }', 'Слова Вторая глава повторены здесь в тексте.', False),   # the label is still on the page
    ('.veil { visibility: hidden; }', '', True),   # hidden through a parent (raw HTML, which GFM passes through)
])
def test_pdf_contents_entry_whose_heading_is_not_printed_stops_the_build(tmp_path, browser, css, prose, veil):
    heading = '<div class="veil">\n\n# Вторая глава\n\n</div>\n\n' if veil else '# Вторая глава\n\n'
    files = dict(CHAPTERS, **{'02.md': heading + prose + '\n\nТекст второй главы.\n'})
    with pytest.raises(BuildError, match="«Вторая глава» points to a heading that isn't printed"):
        build(nav_book(tmp_path, files, css=css), out_dir=tmp_path / 'out', output_format='pdf', log=quiet)


@needs_pandoc
def test_pdf_math_headings_carry_their_rendered_labels(tmp_path, browser):
    files = {'01.md': '# Energy $E=mc^2$\n\nText.\n', '02.md': '# Water $\\mathrm{H_2O}$\n\nText.\n'}
    summary = build(nav_book(tmp_path, files, lang='en-US'), out_dir=tmp_path / 'out', output_format='pdf', log=quiet)
    assert summary['ok'], summary['gates']
    labels = [t for t, _, _ in outline_of(PdfReader(summary['pdf']))]
    assert labels == ['Energy E=mc2', 'Water H2O'] and summary['gates']['pdf']['outline']['result'] == 'pass'


@needs_pandoc
def test_pdf_bookmarks_name_images_by_their_alt_text(tmp_path, browser):
    book = nav_book(tmp_path, {'01.md': '# ![Logo](logo.png)\n\nText.\n', '02.md': '# Map ![of Mars](logo.png) today\n\nText.\n'}, lang='en-US')
    Image.new('RGB', (20, 20), 'white').save(book.base / 'logo.png')
    summary = build(book, out_dir=tmp_path / 'out', output_format='pdf', log=quiet)
    assert summary['ok'], summary['gates']
    labels = [t for t, _, _ in outline_of(PdfReader(summary['pdf']))]
    assert labels == ['Logo', 'Map of Mars today']
    assert any('Logo' in n for n in summary['gates']['pdf']['outline']['not_checked'])   # an image-only heading has no page text


@needs_pandoc
@pytest.mark.parametrize('css, labels', [
    ('nav#TOC em { display: none; }', ['Map today', 'Second']),
    ('nav#TOC em { visibility: hidden; }', ['Map today', 'Second']),
    ('nav#TOC li:first-child a { visibility: hidden; } nav#TOC em { visibility: visible; }', ['of Mars', 'Second']),
])
def test_pdf_bookmarks_hold_only_what_the_printed_contents_show(tmp_path, browser, css, labels):
    files = {'01.md': '# Map *of Mars* today\n\nText.\n', '02.md': '# Second\n\nText.\n'}
    summary = build(nav_book(tmp_path, files, lang='en-US', css=css), out_dir=tmp_path / 'out', output_format='pdf', log=quiet)
    assert summary['ok'], summary['gates']
    assert [t for t, _, _ in outline_of(PdfReader(summary['pdf']))] == labels


@needs_pandoc
@pytest.mark.parametrize('css, labels', [
    ('nav#TOC a::before { content: "Chapter "; }', ['Chapter Map of Mars today', 'Chapter Second']),
    ('nav#TOC em::after { content: "\\201C!\\201D" " " attr(class); }', ['Map of Mars“!” today', 'Second']),
    ('nav#TOC a::after { content: url("data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7") " \\"x\\"" / "spoken only"; }', ['Map of Mars today "x"', 'Second "x"']),
    ('nav#TOC a::before { content: "Chapter "; visibility: hidden; }', ['Map of Mars today', 'Second']),
    ('nav#TOC a::before { content: "Chapter "; display: none; }', ['Map of Mars today', 'Second']),
    ('nav#TOC a::before { content: "Ghostword "; font-size: 0; }', ['Map of Mars today', 'Second']),   # drawn at no size
    ('nav#TOC a::before { content: "Ghostword "; clip-path: inset(50%); }', ['Map of Mars today', 'Second']),
    ('nav#TOC a::before { content: "Ghostword "; display: inline-block; transform: scale(0); }', ['Map of Mars today', 'Second']),
    ('nav#TOC a::before { content: "Ghostword "; filter: opacity(0); }', ['Map of Mars today', 'Second']),   # its own filter
    ('nav#TOC a::before { content: "Ghostword"; display: inline-block; width: 0; overflow: hidden; }',   # its own box of no
     ['Map of Mars today', 'Second']),   # size clips it all
    ('nav#TOC a::before { content: "Ghostword"; display: inline-block; height: 0; overflow: clip; }', ['Map of Mars today', 'Second']),
    ('nav#TOC a::before { content: "Ghostword"; display: inline-block; box-sizing: border-box; width: 2px; border-left: 1px solid; '
     'border-right: 1px solid; overflow: hidden; }', ['Map of Mars today', 'Second']),   # a border box with no padding box left
    ('nav#TOC a::before { content: "Ghostword"; display: inline-block; width: 0; padding-right: 100px; overflow: clip; '
     'overflow-clip-margin: content-box; white-space: nowrap; }', ['Map of Mars today', 'Second']),   # clipped at its empty content box
    ('nav#TOC a::before { content: "Ghostword"; display: inline-block; height: 0; padding-bottom: 40px; overflow: clip; '
     'overflow-clip-margin: content-box; }', ['Map of Mars today', 'Second']),
    ('nav#TOC a { display: block; height: 0; overflow: visible; } nav#TOC a::before { content: "Chapter "; }',   # a host of no
     ['Chapter Map of Mars today', 'Chapter Second']),   # height whose overflow prints
    ('nav#TOC a::before { content: "Chapter "; margin-left: 4px; }', ['Chapter Map of Mars today', 'Chapter Second']),   # a small one
    ('nav#TOC a::before { content: "Chapter "; display: inline-block; padding-top: 2px; }', ['Chapter Map of Mars today', 'Chapter Second']),
    ('nav#TOC li:first-child { margin-bottom: 120px; } nav#TOC li:first-child a { display: inline-block; width: 120px; height: 1.3em; '
     'overflow: clip; overflow-clip-margin: 100px; } nav#TOC li:first-child a::after { content: " and a long generated tail that wraps"; }',
     ['Map of Mars today and a long generated tail that wraps', 'Second']),   # the wrapped lines fall inside the clip margin
    ('nav#TOC li { height: 160px; overflow: hidden; } nav#TOC a { display: block; } '   # a block prefix whose top margin is already
     'nav#TOC a::before { content: "Chapter "; display: block; margin-top: 100px; }',   # in the layout (collapsed through its link),
     ['Chapter Map of Mars today', 'Chapter Second']),   # all of it inside the clipping item
    ('nav#TOC li:first-child a { display: inline-block; width: 400px; overflow: hidden; white-space: nowrap; }',   # a clip that
     ['Map of Mars today', 'Second']),   # cuts nothing
    ('nav#TOC a { display: block; } nav#TOC a::after { content: " suffix"; margin-left: 4px; }',   # a block's suffix starts after
     ['Map of Mars today suffix', 'Second suffix']),   # its last text, not at the block's right edge
    ('nav#TOC a { text-transform: uppercase; }', ['MAP OF MARS TODAY', 'SECOND']),   # the case the contents print
    ('nav#TOC a { text-transform: capitalize; }', ['Map Of Mars Today', 'Second']),
])
def test_pdf_bookmarks_hold_the_text_print_css_generates_in_the_contents(tmp_path, browser, css, labels):
    files = {'01.md': '# Map *of Mars* today\n\nText.\n', '02.md': '# Second\n\nText.\n'}
    summary = build(nav_book(tmp_path, files, lang='en-US', css=css), out_dir=tmp_path / 'out', output_format='pdf', log=quiet)
    assert summary['ok'], summary['gates']
    assert [t for t, _, _ in outline_of(PdfReader(summary['pdf']))] == labels


@needs_pandoc
@pytest.mark.parametrize('css, named', [
    ('nav#TOC li { counter-increment: entry; } nav#TOC a::before { content: counter(entry) ". "; }', 'counter(entry)'),
    ('nav#TOC a::before { content: open-quote; } nav#TOC a::after { content: close-quote; }', 'open-quote'),
    ('nav#TOC a::before { content: "Ghostword"; position: absolute; left: -9999px; }', '::before moved by position: absolute'),
    ('nav#TOC a::before { content: "Ghostword"; position: relative; left: 9999px; }', '::before moved by position: relative'),
    ('nav#TOC a::before { content: "Ghostword"; display: inline-block; transform: translateX(9999px); }', '::before moved by'),
    ('nav#TOC a::before { content: "Ghostword"; display: inline-block; translate: 9999px; }', '::before moved by'),   # the
    ('nav#TOC a::before { content: "Ghostword"; display: inline-block; transform: translateX(0); }', '::before moved by'),
    ('nav#TOC a::after { content: " Ghostword"; margin-left: 9999px; }', '::after moved out of view'),   # its text still lands
    # in the page text, away from the entry
    ('nav#TOC a { display: inline-block; width: 80px; overflow: hidden; } nav#TOC a::after { content: "Ghost"; padding-left: 9999px; }',
     '::after moved out of view'),   # its own padding, clipped by its element
    ('nav#TOC a::before { content: "Ghostword"; display: inline-block; width: 12px; overflow: hidden; }',
     '::before clipping its own overflow'),   # some of it may show: which part cannot be measured
    ('nav#TOC li:first-child a { display: inline-block; width: 120px; height: 1.3em; overflow: hidden; } '
     'nav#TOC li:first-child a::after { content: " and a long generated tail that wraps"; }',
     '::after inside an element that cuts off part of its content'),   # its later lines are cut, its glyphs may stay in the text
    ('nav#TOC a { display: inline-block; height: 20px; overflow: hidden; } nav#TOC a::before { content: "Ghostword"; '
     'display: inline-block; vertical-align: top; padding-top: 100px; }', '::before inside an element that cuts off part'),   # pushed
    # below its clipping host while the entry's own words stay in view: the host's content runs past it
    ('nav#TOC a::before { content: "Ghostword"; display: inline-block; width: 0; padding-right: 100px; overflow: hidden; '
     'white-space: nowrap; }', '::before clipping its own overflow'),   # no content width, but its padding box shows the text
    ('nav#TOC a::before { content: "Ghostword"; display: inline-block; width: 0; overflow: clip; overflow-clip-margin: 100px; }',
     '::before clipping its own overflow'),   # a clip margin gives it room too
    ('nav#TOC a::before { content: "Ghostword"; display: inline-block; width: 0; padding-right: 100px; overflow: clip; '
     'overflow-clip-margin: content-box 20px; white-space: nowrap; }', '::before clipping its own overflow'),   # content box, grown
])   # individual transform properties move it too; even the identity puts its text after the contents in the page text
def test_pdf_contents_text_from_a_counter_or_quote_stops_the_build(tmp_path, browser, css, named):
    files = {'01.md': '# First\n\nText.\n', '02.md': '# Second\n\nText.\n'}
    with pytest.raises(BuildError, match=re.escape(f'«First» shows text that print CSS generates with {named}')):
        build(nav_book(tmp_path, files, lang='en-US', css=css), out_dir=tmp_path / 'out', output_format='pdf', log=quiet)


@needs_pandoc
@pytest.mark.parametrize('css', [
    'nav#TOC li:first-child a { display: inline-block; width: 12px; overflow: hidden; white-space: nowrap; vertical-align: top; }',
    'nav#TOC li:first-child a { display: inline-block; width: 12px; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }',
    'nav#TOC li:first-child { width: 12px; overflow: hidden; white-space: nowrap; }',   # cut by a parent
    'nav#TOC li:first-child { width: 40px; height: 1.3em; overflow: hidden; }',   # its second line cut away
    'nav#TOC li:first-child a { display: inline-block; height: 4px; line-height: 4px; overflow: hidden; vertical-align: top; }',   # a
    # central sliver: each edge loses less than half the line, together far more
    'nav#TOC li:first-child a { display: inline-block; width: 12px; overflow: clip; overflow-clip-margin: 2px; white-space: nowrap; }',
    'nav#TOC li:first-child a { display: inline-block; width: 12px; overflow: hidden; overflow-clip-margin: 150px; white-space: nowrap; }',
    'nav#TOC li:first-child a { display: inline-block; width: 24px; border-left: 40px solid; overflow: hidden; white-space: nowrap; '
    'transform: scale(0.5); transform-origin: 0 0; }',   # scaled, and still too narrow
    'nav#TOC li:first-child a { display: inline-block; width: 12px; overflow-x: clip; overflow-y: visible; overflow-clip-margin: 150px; '
    'white-space: nowrap; }',   # Chrome 148 and 155 ignore the margin when only one axis clips: the ink stops at the box
])   # a clip margin moves only an overflow: clip edge, and only with both axes clipped
def test_pdf_contents_entry_partly_clipped_stops_the_build(tmp_path, browser, css):
    files = {'01.md': '# First words here\n\nText.\n', '02.md': '# Second\n\nText.\n'}
    with pytest.raises(BuildError, match='«First words here» is only partly visible in the printed contents'):
        build(nav_book(tmp_path, files, lang='en-US', css=css), out_dir=tmp_path / 'out', output_format='pdf', log=quiet)


@needs_pandoc
@pytest.mark.parametrize('css', ['nav#TOC li { overflow: hidden; line-height: 1; }', 'nav#TOC a { display: inline-block; overflow: hidden; '
                                 'line-height: 0.8; }',   # the line box trims only the tops and bottoms of the letters
                                 'nav#TOC li:first-child a { display: inline-block; width: 12px; overflow: clip; overflow-clip-margin: 150px; '
                                 'white-space: nowrap; }',   # the clip edge is 150px out: all of it shows
                                 'nav#TOC a { display: inline-block; width: 200px; border-left: 40px solid; overflow: hidden; '
                                 'transform: scale(0.5); transform-origin: 0 0; white-space: nowrap; }',   # a scaled border
                                 'nav#TOC li { transform: scale(0.5); transform-origin: 0 0; } nav#TOC a { display: inline-block; '
                                 'width: 200px; border-left: 40px solid; overflow: hidden; white-space: nowrap; }',   # scaled above
                                 'nav#TOC li:first-child { width: 40px; height: 1.3em; overflow-x: clip; }'])   # clipped across only:
                                 # the second line shows below
def test_pdf_contents_entry_in_a_tight_clipping_line_is_listed(tmp_path, browser, css):
    files = {'01.md': '# First words here\n\nText.\n', '02.md': '# Second\n\nText.\n'}
    summary = build(nav_book(tmp_path, files, lang='en-US', css=css), out_dir=tmp_path / 'out', output_format='pdf', log=quiet)
    assert summary['ok'], summary['gates']
    assert [t for t, _, _ in outline_of(PdfReader(summary['pdf']))] == ['First words here', 'Second']


@needs_pandoc
def test_pdf_contents_entry_with_nothing_visible_stops_the_build(tmp_path, browser):
    files = {'01.md': '# First\n\nText.\n', '02.md': '# Second\n\nText.\n'}
    css = 'nav#TOC li:nth-child(2) a { visibility: hidden; }'   # its words still lay out, unseen
    with pytest.raises(BuildError, match='«Second» is hidden in the printed contents'):
        build(nav_book(tmp_path, files, lang='en-US', css=css), out_dir=tmp_path / 'out', output_format='pdf', log=quiet)


@needs_pandoc
@pytest.mark.parametrize('hidden', ['nav#TOC li:first-child a', 'nav#TOC li:first-child'])
def test_pdf_generated_text_of_a_hidden_entry_does_not_list_it(tmp_path, browser, hidden):
    files = {'01.md': '# First\n\nText.\n', '02.md': '# Second\n\nText.\n'}
    css = f'{hidden} {{ display: none; }} nav#TOC a::before {{ content: "Chapter "; }}'   # the pseudo's own display is still inline
    with pytest.raises(BuildError, match='«First» is hidden in the printed contents'):
        build(nav_book(tmp_path, files, lang='en-US', css=css), out_dir=tmp_path / 'out', output_format='pdf', log=quiet)


@needs_pandoc
@pytest.mark.parametrize('css', [
    'nav#TOC li:first-child { height: 0; overflow: hidden; }',
    'nav#TOC li::marker { content: counter(list-item) ". "; } nav#TOC li:first-child { height: 0; overflow: hidden; }',   # a marker
    'nav#TOC li:first-child a { display: block; height: 0; overflow: hidden; }',   # that skips the contents text check
    'nav#TOC li:first-child a { display: block; text-indent: -9999px; }',   # its first line, ::before included, off the page
])
def test_pdf_generated_text_inside_a_clipped_entry_does_not_list_it(tmp_path, browser, css):
    files = {'01.md': '# First\n\nText.\n', '02.md': '# Second\n\nText.\n'}
    css += ' nav#TOC a::before { content: "Chapter "; }'
    with pytest.raises(BuildError, match='«First» is hidden in the printed contents'):
        build(nav_book(tmp_path, files, lang='en-US', css=css), out_dir=tmp_path / 'out', output_format='pdf', log=quiet)


@needs_pandoc
@pytest.mark.parametrize('css', ['nav#TOC li:first-child a { opacity: 0; }', 'nav#TOC li:first-child { opacity: 0; }',
                                 'nav#TOC li:first-child a { color: transparent; }', 'nav#TOC li:first-child a { color: rgb(0 0 0 / 0%); }',
                                 'nav#TOC li:first-child a { -webkit-text-fill-color: transparent; }',
                                 'nav#TOC li:first-child a { color: color(display-p3 1 0 1 / 0); }',
                                 'nav#TOC li:first-child a { display: inline-block; transform: scale(0); }',
                                 'nav#TOC li:first-child a { display: inline-block; transform: rotate(45deg) scaleX(0); }',
                                 'nav#TOC li:first-child a { font-size: 0; }', 'nav#TOC li:first-child a { position: absolute; left: -9999px; }',
                                 'nav#TOC li:first-child a { position: absolute; left: 9999px; }',
                                 'nav#TOC li:first-child a { display: inline-block; clip-path: inset(50%); }',
                                 'nav#TOC li:first-child a { display: inline-block; width: 0; overflow: hidden; }',
                                 'nav#TOC li:first-child a { filter: opacity(0); }',
                                 'nav#TOC li:first-child a { -webkit-text-fill-color: transparent; text-shadow: 1px 1px 0 rgba(0, 0, 0, 0); }',
                                 'nav#TOC li:first-child a { color: oklch(0.5 0.1 120 / 0); }'])
def test_pdf_contents_entry_drawn_invisibly_stops_the_build(tmp_path, browser, css):
    files = {'01.md': '# First\n\nText.\n', '02.md': '# Second\n\nText.\n'}
    with pytest.raises(BuildError, match='«First» is hidden in the printed contents'):
        build(nav_book(tmp_path, files, lang='en-US', css=css), out_dir=tmp_path / 'out', output_format='pdf', log=quiet)


@needs_pandoc
@pytest.mark.parametrize('color', ['color(display-p3 1 0 0)', 'color(display-p3 0 0 0 / 0.5)', 'oklch(0.4 0.1 30)', 'rgb(10 20 30 / 60%)'])
def test_pdf_contents_entry_in_any_visible_colour_is_listed(tmp_path, browser, color):
    files = {'01.md': '# First\n\nText.\n', '02.md': '# Second\n\nText.\n'}
    summary = build(nav_book(tmp_path, files, lang='en-US', css=f'nav#TOC a {{ color: {color}; }}'), out_dir=tmp_path / 'out',
                    output_format='pdf', log=quiet)
    assert summary['ok'], summary['gates']
    assert [t for t, _, _ in outline_of(PdfReader(summary['pdf']))] == ['First', 'Second']


@needs_pandoc
def test_pdf_navigation_adds_nothing_among_a_headings_own_elements(tmp_path, browser):
    files = {'01.md': '# Map *of Mars* today\n\nText.\n', '02.md': '# Second *part*\n\nText.\n'}
    css = 'body > h1 > :first-child { display: none; }'   # author CSS keyed on a heading's first element
    summary = build(nav_book(tmp_path, files, lang='en-US', css=css), out_dir=tmp_path / 'out', output_format='pdf', log=quiet)
    assert summary['ok'], summary['gates']
    reader = PdfReader(summary['pdf'])
    first = next(page for _, _, page in outline_of(reader))
    text = pdfnav.normalized(reader.pages[first].extract_text())
    assert 'maptoday' in text and 'ofmars' not in text   # the emphasis is still the first element, so it is the one hidden


@needs_pandoc
@pytest.mark.parametrize('css, message', [
    ('body > h1 img { display: none; }', "points to a heading that isn't printed"),   # the heading's only content gone
    ('body > h1 img { transform: rotate(45deg) scaleX(0); }', "points to a heading that isn't printed"),   # no area, a box left
    ('nav#TOC img { transform: scale(0); }', 'is hidden in the printed contents'),   # the entry's only content drawn at no size
    ('nav#TOC img { transform: rotate(45deg) scaleX(0); }', 'is hidden in the printed contents'),
    ('body > h1 img { clip-path: inset(50%); }', "points to a heading that isn't printed"),   # a box and a size, nothing drawn
    ('nav#TOC img { clip-path: inset(50%); }', 'is hidden in the printed contents'),
    ('nav#TOC li:first-child a { display: inline-block; width: 0; overflow: hidden; }', 'is hidden in the printed contents'),
    ('nav#TOC img { position: absolute; left: 9999px; }', 'is hidden in the printed contents'),   # past the printable width
    ('nav#TOC img { filter: opacity(0); }', 'is hidden in the printed contents'),   # a filter's result cannot be told
    ('nav#TOC img { width: 1000px; height: 20px; margin-left: -990px; object-fit: none; object-position: 0 0; transform: rotate(1deg); }',
     'is hidden in the printed contents'),   # turned, its pixels off the page in a box that reaches onto it
    ('body > h1 img { filter: opacity(0); }', "points to a heading that isn't printed"),
    ('nav#TOC img { scale: 0 1; rotate: 45deg; }', 'is hidden in the printed contents'),   # the scale property collapses
    ('body > h1 img { scale: 0 1; rotate: 45deg; }', "points to a heading that isn't printed"),   # it as transform does
    ('nav#TOC img { object-fit: none; object-position: 9999px 50%; }', 'is hidden in the printed contents'),   # its content
    ('body > h1 img { object-fit: none; object-position: 9999px 50%; }', "points to a heading that isn't printed"),   # outside
    ('nav#TOC img { object-fit: fill; object-position: 9999px 50%; }', 'is hidden in the printed contents'),   # fill moves too
    ('nav#TOC img { box-sizing: content-box; width: 20px; height: 20px; padding: 10px; object-fit: none; object-position: 25px 0; }',
     'is hidden in the printed contents'),   # in the padding, outside the content box
    ('nav#TOC a { display: inline-block; width: 80px; overflow: hidden; } '   # the padding shows inside the clipping link,
     'nav#TOC img { box-sizing: content-box; width: 20px; height: 20px; padding-left: 100px; }', 'is hidden in the printed contents'),
    ('nav#TOC img { box-sizing: content-box; width: 20px; height: 20px; padding-left: 2000px; margin-left: -500px; }',   # the
     'is hidden in the printed contents'),   # pixels are past the page while the padding box crosses it
    ('nav#TOC a { display: inline-block; width: 80px; overflow: hidden; } nav#TOC img { box-sizing: content-box; width: 20px; '
     'height: 20px; padding-left: 200px; transform: scale(.5); transform-origin: left top; }',   # scaled pixels at 100-110px,
     'is hidden in the printed contents'),   # past the 80px link
    ('nav#TOC img { rotate: 0deg; object-fit: none; object-position: 9999px 50%; }', 'is hidden in the printed contents'),   # a
    ('nav#TOC img { object-fit: fill; object-position: 9999px 50%; rotate: 0deg; }', 'is hidden in the printed contents'),   # turn,
    ('nav#TOC img { object-fit: fill; object-position: 9999px 50%; transform: rotate(1deg); }', 'is hidden in the printed contents'),
    ('nav#TOC img { rotate: 1turn; object-fit: none; object-position: 9999px 50%; }', 'is hidden in the printed contents'),
] + [(f'nav#TOC a {{ display: inline-block; width: 50px; height: 20px; overflow: hidden; }} nav#TOC img {{ width: 100px; height: '
      f'40px; object-fit: none; object-position: left top; {turn} }}', 'is hidden in the printed contents')   # the pixels, at the
     for turn in ('transform: rotate(180deg);', 'transform: scale(-1, -1);', 'scale: -1;', 'transform: rotateY(180deg) rotateX(180deg);')]
  + [('nav#TOC a { display: inline-block; width: 50px; overflow: hidden; } nav#TOC img { box-sizing: content-box; width: 20px; '
      'height: 20px; padding-left: 100px; transform: rotate(1deg); }', 'is hidden in the printed contents')])   # turned, filling its
# content box, only its padding inside the 50px link; above, the pixels at the top left are
# turned to the bottom right, past the 50 by 20 link; identity or real, a turn never stands in for pixels outside the box
def test_pdf_image_only_entries_must_print(tmp_path, browser, css, message):
    book = nav_book(tmp_path, {'01.md': '# ![Logo](logo.png)\n\nText.\n', '02.md': '# Second\n\nText.\n'}, lang='en-US', css=css)
    Image.new('RGB', (20, 20), 'white').save(book.base / 'logo.png')
    with pytest.raises(BuildError, match=f'«Logo» {message}'):
        build(book, out_dir=tmp_path / 'out', output_format='pdf', log=quiet)


@needs_pandoc
def test_pdf_heading_drawn_invisibly_is_not_printed(tmp_path, browser):
    files = {'01.md': '# First\n\nText.\n', '02.md': '# Second\n\nText.\n'}
    with pytest.raises(BuildError, match="«Second» points to a heading that isn't printed"):
        build(nav_book(tmp_path, files, lang='en-US', css='body > h1:nth-of-type(2) { opacity: 0; }'), out_dir=tmp_path / 'out',
              output_format='pdf', log=quiet)


@needs_pandoc
def test_pdf_contents_gate_reads_a_last_contents_page_the_first_chapter_shares(tmp_path, browser):
    files = {f'{n:02}.md': f'# Chapter{"abcdefgh"[n]}word\n\nText.\n' for n in range(8)}
    css = ('nav#TOC li { font-size: 90px; line-height: 1.6; } nav#TOC { break-after: auto !important; } '
           'h1:not(.title) { break-before: auto !important; }')   # a two-page contents the first chapter follows on its last page
    summary = build(nav_book(tmp_path, files, lang='en-US', css=css), out_dir=tmp_path / 'out', output_format='pdf', log=quiet)
    reader = PdfReader(summary['pdf'])
    first_heading = min(page for _, _, page in outline_of(reader))
    contents = pdfnav.named_destinations(reader)[pdfnav.CONTENTS]
    assert first_heading > reader.get_destination_page_number(contents)   # the contents runs onto the first chapter's page
    assert 'chapterhword' in pdfnav.normalized(reader.pages[first_heading].extract_text()).split('chapterawordtext')[0]
    assert summary['ok'], summary['gates']['pdf']['outline']


def kept_out(tmp_path, files, css, entry, lang='en-US'):
    """A contents entry print keeps out never passes: the page refuses it as hidden, or the outline gate misses it."""
    try:
        summary = build(nav_book(tmp_path, files, lang=lang, css=css), out_dir=tmp_path / 'out', output_format='pdf', log=quiet)
    except BuildError as error:
        assert f'«{entry}» is hidden in the printed contents' in str(error)
        return
    outline = summary['gates']['pdf']['outline']
    assert not summary['ok'] and any(f'«{entry}» is not in the printed contents text' in p for p in outline['problems']), outline


@needs_pandoc
def test_pdf_contents_gate_never_finds_a_hidden_entry_in_the_chapter_text_after_it(tmp_path, browser):
    files = {f'{n:02}.md': f'# Chapter{"abcdefgh"[n]}word\n\nText.\n' for n in range(8)}
    files['00.md'] = '# Chapterqword\n\nThe Chapterhword is told later, after Chapterqword ends.\n'   # the hidden entry's words on
    # the shared page, and the first heading's words again after them, where a cut at their last occurrence would land
    files['07.md'] = '# Chapterhword\n\nText.\n'
    css = ('nav#TOC li { font-size: 90px; line-height: 1.6; } nav#TOC { break-after: auto !important; } '
           'h1:not(.title) { break-before: auto !important; } nav#TOC li:last-child a { display: inline-block; clip-path: inset(50%); }')
    kept_out(tmp_path, files, css, 'Chapterhword')


@needs_pandoc
def test_pdf_contents_gate_takes_no_letters_between_entries(tmp_path, browser):
    files = {'01.md': '# One\n\nBetaword appears here.\n', '02.md': '# Betaword\n\nText.\n'}   # a short heading, then the words
    css = ('nav#TOC { break-after: auto !important; } h1:not(.title) { break-before: auto !important; } '
           'nav#TOC li:last-child a { display: inline-block; clip-path: inset(50%); }')
    kept_out(tmp_path, files, css, 'Betaword')


@needs_pandoc
@pytest.mark.parametrize('lang, files, css, entry', [
    ('fr', {'01.md': '# Alphaword\n\nText.\n'}, 'nav#TOC a { display: inline-block; clip-path: inset(50%); }', 'Alphaword'),
    ('fr', {'01.md': '# Alphaword\n\nText.\n'}, 'nav#TOC { break-after: auto !important; } h1:not(.title) { break-before: auto !important; } '
                                               'nav#TOC a { display: inline-block; clip-path: inset(50%); }', 'Alphaword'),
    ('en-US', {'01.md': '# 1\n\nBetaword appears here.\n', '02.md': '# Betaword\n\nText.\n'},   # a numeric heading, then the words
     'nav#TOC { break-after: auto !important; } h1:not(.title) { break-before: auto !important; } '
     'nav#TOC li:last-child a { display: inline-block; clip-path: inset(50%); }', 'Betaword'),
])
def test_pdf_contents_gate_finds_no_entry_outside_the_printed_contents(tmp_path, browser, lang, files, css, entry):
    kept_out(tmp_path, files, css, entry, lang)


@needs_pandoc
@pytest.mark.parametrize('css, numbers', [
    ('nav#TOC ul { list-style-type: lower-alpha; }', True),
    ('nav#TOC ul { list-style-type: upper-roman; }', True),
    ('nav#TOC ul { list-style-type: decimal; }', True),
    ('nav#TOC ul { list-style-type: decimal; } nav#TOC li:first-child { display: block; }', True),   # the next items print 1 and 2
    ('', False),   # unnumbered pages: a contents entry "3" on page 3 is no footer
])
def test_pdf_contents_gate_accepts_list_markers_and_unnumbered_pages(tmp_path, browser, css, numbers):
    files = {'01.md': '# First\n\nText.\n', '02.md': '# Second\n\nText.\n', '03.md': '# 3\n\nText.\n'}   # "3", last on page 3
    extra = '' if numbers else '  pdf:\n    page_numbers: false\n'
    summary = build(nav_book(tmp_path, files, lang='en-US', css=css, extra=extra), out_dir=tmp_path / 'out', output_format='pdf', log=quiet)
    assert summary['ok'], summary['gates']['pdf']['outline']


@needs_pandoc
@pytest.mark.parametrize('css, rights, problem', [
    ('header#title-block-header .title { display: none; }', 'Навигация & <тест>', 'the title is not on the title page'),   # its words
    ('header#title-block-header p.rights { visibility: hidden; }', '© 2026', 'the rights line is not on the title page'),   # elsewhere
    ('nav#TOC > h2 { opacity: 0; }', '© 2026', 'the contents heading is not on the first contents page'),
    ('header#title-block-header .title { width: 30px; overflow: hidden; white-space: nowrap; }', 'Навигация & <тест>',
     'the title is only partly visible on the title page'),   # its whole text may stay in the page text, cut glyphs included
    ('header#title-block-header p.rights { width: 12px; overflow: hidden; white-space: nowrap; }', 'All rights reserved 2026',
     'the rights line is only partly visible on the title page'),
    ('nav#TOC > h2 { width: 12px; overflow: hidden; white-space: nowrap; }', '© 2026',
     'the contents heading is only partly visible on the first contents page'),
    ('header#title-block-header .author { break-before: page; }', '', 'the title block does not fit on the title page'),   # no
])   # rights line to show it
def test_pdf_front_matter_gate_checks_the_elements_themselves(tmp_path, browser, css, rights, problem):
    files = {'01.md': '# First\n\nСодержание.\n', '02.md': '# Second\n\nText.\n'}
    summary = build(nav_book(tmp_path, files, rights=rights, css=css), out_dir=tmp_path / 'out', output_format='pdf', log=quiet)
    assert any(p.startswith(problem) for p in summary['gates']['pdf']['front_matter']['problems']), summary['gates']['pdf']['front_matter']


@needs_pandoc
@pytest.mark.parametrize('rule', ['nav#TOC ul { list-style: decimal url("%s"); }', 'nav#TOC ul { list-style-type: decimal; } '
                                  'nav#TOC li::marker { content: url("%s"); }'])   # the image prints, never its URL
def test_pdf_an_image_list_marker_leaves_the_contents_text_unchecked(tmp_path, browser, rule):
    files = {'01.md': '# First\n\nText.\n', '02.md': '# Second\n\nText.\n'}
    css = rule % ('data:image/svg+xml,'
                  '%3Csvg xmlns=%27http://www.w3.org/2000/svg%27 width=%278%27 height=%278%27%3E%3Crect width=%278%27 height=%278%27/%3E%3C/svg%3E')
    summary = build(nav_book(tmp_path, files, lang='en-US', css=css), out_dir=tmp_path / 'out', output_format='pdf', log=quiet)
    outline = summary['gates']['pdf']['outline']   # the image prints when it loads; decimal is only its fallback
    assert summary['ok'] and any('list marker' in n for n in outline['not_checked']), outline


@needs_pandoc
@pytest.mark.parametrize('css', ['nav#TOC img { width: 100px; height: 40px; object-fit: contain; transform: rotate(1deg); }',
                                 'nav#TOC img { width: 100px; height: 40px; object-fit: none; transform: rotate(1deg); }'])
def test_pdf_a_turned_letterboxed_image_inside_the_page_prints(tmp_path, browser, css):
    book = nav_book(tmp_path, {'01.md': '# ![Logo](logo.png)\n\nText.\n', '02.md': '# Second\n\nText.\n'}, lang='en-US', css=css)
    Image.new('RGB', (20, 20), 'blue').save(book.base / 'logo.png')   # its pixels fill only part of the box, all of it on the page
    summary = build(book, out_dir=tmp_path / 'out', output_format='pdf', log=quiet)
    assert summary['ok'], summary['gates']


@needs_pandoc
def test_pdf_custom_list_counters_leave_the_contents_text_unchecked(tmp_path, browser):
    files = {'01.md': '# First\n\nText.\n', '02.md': '# Second\n\nText.\n'}
    css = 'nav#TOC ul { list-style-type: decimal; } nav#TOC li { counter-increment: list-item 2; }'   # it prints 2 and 4
    summary = build(nav_book(tmp_path, files, lang='en-US', css=css), out_dir=tmp_path / 'out', output_format='pdf', log=quiet)
    outline = summary['gates']['pdf']['outline']
    assert summary['ok'] and any('list marker' in n for n in outline['not_checked']), outline


def named_book(tmp_path, files, title, authors, css):   # nav_book with its own title and authors, no rights line
    book = nav_book(tmp_path, files, lang='en-US', rights='', css=css)
    yaml = book.base / 'mdbindery.yaml'
    yaml.write_text(yaml.read_text(encoding='utf-8').replace('title: "Навигация & <тест>"', f'title: {json.dumps(title)}')
                    .replace('authors: [Анна Первая, "Bo & Co"]', f'authors: {json.dumps(authors)}'), encoding='utf-8')
    return config.load(book.base)


@needs_pandoc
@pytest.mark.parametrize('css, ok', [
    ('header#title-block-header .date { display: none; } header#title-block-header .author { break-before: page; }', False),
    ('header#title-block-header .date { display: none; }', True),   # the same words, all on the title page
])
@pytest.mark.parametrize('title, author', [('Alice', 'Alice'), ('Alice', '©'), ('Be an Artist', 'Bea'), ('Alice', '2')])   # a word the title
def test_pdf_a_title_block_word_the_title_repeats_must_print_on_the_title_page_too(tmp_path, browser, css, ok, title, author):
    files = {'01.md': '# First\n\nText.\n', '02.md': '# Second\n\nText.\n'}   # repeats, symbols only, letters across words, the footer's number
    summary = build(named_book(tmp_path, files, title, [author], css), out_dir=tmp_path / 'out', output_format='pdf', log=quiet)
    problems = summary['gates']['pdf']['front_matter']['problems']
    assert (problems == []) if ok else any(p.startswith('the title block does not fit on the title page') for p in problems), problems


@needs_pandoc
def test_pdf_an_image_entry_without_alt_text_stops_the_build(tmp_path, browser):
    book = nav_book(tmp_path, {'01.md': '# ![](logo.png) Word\n\nText.\n', '02.md': '# Second\n\nText.\n'}, lang='en-US',
                    css='nav#TOC li:first-child a { color: transparent; }')   # its word drawn invisibly, an image with no alt text left
    Image.new('RGB', (20, 20), 'blue').save(book.base / 'logo.png')
    with pytest.raises(BuildError, match='contents entry 1 shows nothing a bookmark title can hold'):
        build(book, out_dir=tmp_path / 'out', output_format='pdf', log=quiet)


@needs_pandoc
@pytest.mark.parametrize('turn', ['1turn', '400grad'])   # Chrome computes both as 360deg
def test_pdf_an_identity_turn_in_any_unit_leaves_a_partly_clipped_image_drawn(tmp_path, browser, turn):
    css = ('nav#TOC a { display: inline-block; width: 50px; overflow: hidden; } '   # the box is cut at 50px, the pixels at 0-20px
           f'nav#TOC img {{ width: 100px; height: 40px; object-fit: none; object-position: left top; rotate: {turn}; }}')
    book = nav_book(tmp_path, {'01.md': '# ![Logo](logo.png)\n\nText.\n', '02.md': '# Second\n\nText.\n'}, lang='en-US', css=css)
    Image.new('RGB', (20, 20), 'blue').save(book.base / 'logo.png')
    summary = build(book, out_dir=tmp_path / 'out', output_format='pdf', log=quiet)
    assert summary['ok'], summary['gates']


@needs_pandoc
def test_pdf_an_image_entry_under_a_boxless_clipping_ancestor_prints(tmp_path, browser):
    book = nav_book(tmp_path, {'01.md': '# ![Logo](logo.png)\n\nText.\n', '02.md': '# Second\n\nText.\n'}, lang='en-US',
                    css='nav#TOC li:first-child { display: contents; overflow: hidden; }')   # overflow does nothing without a box
    Image.new('RGB', (20, 20), 'white').save(book.base / 'logo.png')
    summary = build(book, out_dir=tmp_path / 'out', output_format='pdf', log=quiet)
    assert summary['ok'], summary['gates']['pdf']


@needs_pandoc
def test_pdf_contents_links_carry_no_attribute_the_books_css_could_see(tmp_path, browser):
    files = {'01.md': '# First\n\nText.\n', '02.md': '# Second\n\nText.\n'}
    css = 'nav#TOC a:not([data-mdb-dest]) { display: none; }'   # matches every contents link pandoc wrote
    with pytest.raises(BuildError, match='«First» is hidden in the printed contents'):
        build(nav_book(tmp_path, files, lang='en-US', css=css), out_dir=tmp_path / 'out', output_format='pdf', log=quiet)


@needs_pandoc
@pytest.mark.parametrize('css, ok', [('html:has(head > a) body { color: red; }', False),   # the hidden links turn the text red
                                     ('html:has(head > a) body { cursor: pointer; }', True)])   # nothing printed changes
def test_pdf_css_that_sees_the_locator_links_must_print_the_same(tmp_path, browser, css, ok):
    files = {'01.md': '# First\n\nText.\n', '02.md': '# Second\n\nText.\n'}
    book = nav_book(tmp_path, files, lang='en-US', css=css)
    if ok:
        assert build(book, out_dir=tmp_path / 'out', output_format='pdf', log=quiet)['ok']
    else:
        with pytest.raises(BuildError, match='hidden navigation links to the document head \\(page \\d+\\)'):
            build(book, out_dir=tmp_path / 'out', output_format='pdf', log=quiet)


@needs_pandoc
def test_pdf_locator_links_change_no_body_structure(tmp_path, browser):
    files = {'01.md': '# First\n\nKeptword.\n\nHiddenword.\n', '02.md': '# Second\n\nText.\n\nLastword.\n'}
    css = 'body > p:last-child { display: none; }'   # the book's last paragraph, as the author's CSS selects it
    summary = build(nav_book(tmp_path, files, lang='en-US', css=css), out_dir=tmp_path / 'out', output_format='pdf', log=quiet)
    assert summary['ok'], summary['gates']['pdf']
    reader = PdfReader(summary['pdf'])
    assert 'lastword' not in pdfnav.normalized(''.join(p.extract_text() or '' for p in reader.pages))


@needs_pandoc
@pytest.mark.parametrize('css', ['body > h1 { transform: translateZ(1px); }', 'nav#TOC a { display: inline-block; transform: translateZ(1px); }'])
def test_pdf_a_3d_transform_that_keeps_its_area_draws(tmp_path, browser, css):
    summary = build(nav_book(tmp_path, CHAPTERS, css=css), out_dir=tmp_path / 'out', output_format='pdf', log=quiet)
    assert summary['ok'], summary['gates']['pdf']


@needs_pandoc
def test_pdf_generated_text_of_a_hidden_part_stays_out_of_the_bookmark(tmp_path, browser):
    files = {'01.md': '# Map *of Mars* today\n\nText.\n', '02.md': '# Second\n\nText.\n'}
    css = 'nav#TOC em { display: none; } nav#TOC em::after { content: "!"; }'
    summary = build(nav_book(tmp_path, files, lang='en-US', css=css), out_dir=tmp_path / 'out', output_format='pdf', log=quiet)
    assert [t for t, _, _ in outline_of(PdfReader(summary['pdf']))] == ['Map today', 'Second']


@needs_pandoc
def test_pdf_contents_entry_hidden_in_print_stops_the_build(tmp_path, browser):
    css = 'nav#TOC li:nth-child(2) { display: none; }'
    with pytest.raises(BuildError, match='«Вторая глава» is hidden in the printed contents'):
        build(nav_book(tmp_path, CHAPTERS, css=css), out_dir=tmp_path / 'out', output_format='pdf', log=quiet)


@needs_pandoc
def test_pdf_contents_links_without_a_box_of_their_own_still_count_as_printed(tmp_path, browser):
    summary = build(nav_book(tmp_path, CHAPTERS, css='nav#TOC a { display: contents; }'), out_dir=tmp_path / 'out', output_format='pdf', log=quiet)
    assert summary['ok'], summary['gates']
    assert len(outline_of(PdfReader(summary['pdf']))) == 4


@needs_pandoc
def test_pdf_contents_entry_hidden_by_its_href_stops_the_build(tmp_path, browser):
    files = {'01.md': '# First\n\nText.\n', '02.md': '# Second\n\nText.\n'}
    css = 'nav#TOC a[href$="second"] { display: none; }'   # author CSS keyed on the entry's own href
    with pytest.raises(BuildError, match='«Second» is hidden in the printed contents'):
        build(nav_book(tmp_path, files, lang='en-US', css=css), out_dir=tmp_path / 'out', output_format='pdf', log=quiet)
