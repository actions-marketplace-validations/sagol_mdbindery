"""PDF integration and EPUB compatibility checks. Never build source fixtures in place."""
import json
import os
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter

from conftest import EXAMPLES, FIXTURES, needs_pandoc, validate_if_installed
from mdbindery import config, tools
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
    summary = build(cfg, out_dir=tmp_path / 'out', output_format='pdf', log=quiet)
    assert not summary['ok'] and summary['gates']['pdf']['result'] == 'fail'
    assert summary['gates']['pdf']['missing_words'] >= 100


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
