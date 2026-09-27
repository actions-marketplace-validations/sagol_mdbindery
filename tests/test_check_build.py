import hashlib
import zipfile

from conftest import EXAMPLES, FIXTURES, HAVE_MMDC, needs_epubcheck, needs_pandoc, validate_if_installed
from mdbindery import config
from mdbindery.build import build
from mdbindery.check import check, to_json, to_markdown


@needs_pandoc
def test_check_finds_every_planted_problem(copy_book):
    rep = check(str(copy_book(FIXTURES / 'broken-book')), render=True, log=lambda *_: None)
    codes = {f['code'] for f in rep.findings}
    expected = {'MB102', 'MB103', 'MB105', 'MB106', 'MB108', 'MB200', 'MB204', 'MB300', 'MB301', 'MB302',
                'MB304', 'MB400', 'MB401', 'MB402', 'MB403', 'MB500', 'MB600'}
    assert expected <= codes, expected - codes
    assert not rep.ok
    by = {(f['code'], f['file']): f for f in rep.findings}
    assert by[('MB200', '01-intro.md')]['line'] == 5
    assert by[('MB401', '01-intro.md')]['line'] == 7
    assert '# mdbindery check' in to_markdown(rep) and '"ok": false' in to_json(rep)


@needs_pandoc
def test_sample_book_is_clean(copy_book):
    rep = check(str(copy_book(EXAMPLES / 'sample-book')), render=False, log=lambda *_: None)
    assert rep.ok, [f for f in rep.findings if f['severity'] == 'error']
    warnings = [f for f in rep.findings if f['severity'] == 'warning']
    # without mermaid-cli the sample's chart would become a placeholder, and check says so
    assert [f['code'] for f in warnings] == ([] if HAVE_MMDC else ['MB700']), warnings


@needs_pandoc
@needs_epubcheck
def test_sample_book_builds_and_passes_gates(copy_book, tmp_path):
    book = copy_book(EXAMPLES / 'sample-book')
    cfg = config.load(book)
    s = build(cfg, out_dir=tmp_path / 'out', run_ace=False, log=lambda *_: None)
    assert s['ok'], s['failed_gates']
    assert s['gates']['epubcheck']['result'] == 'pass'
    with zipfile.ZipFile(s['epub']) as z:
        names = z.namelist()
        text = ''.join(z.read(n).decode('utf-8') for n in names if n.endswith('.xhtml'))
    assert names[0] == 'mimetype'
    assert 'class="full-page"' in text and '<figcaption>' in text and 'class="card"' in text
    assert 'id="k01-ref-1"' in text and 'class="inline"' in text
    assert 'Contributing' not in text  # dropped section


@needs_pandoc
def test_builds_are_reproducible(copy_book, tmp_path):
    book = copy_book(FIXTURES / 'ru-book')
    digests = []
    for i in range(2):
        s = build(validate_if_installed(config.load(book)), out_dir=tmp_path / f'o{i}', run_ace=False, log=lambda *_: None)
        assert s['ok'], s['failed_gates']
        digests.append(hashlib.sha256(open(s['epub'], 'rb').read()).hexdigest())
    assert digests[0] == digests[1]


@needs_pandoc
def test_russian_book(copy_book, tmp_path):
    book = copy_book(FIXTURES / 'ru-book')
    s = build(validate_if_installed(config.load(book)), out_dir=tmp_path / 'out', run_ace=False, log=lambda *_: None)
    assert s['ok']
    with zipfile.ZipFile(s['epub']) as z:
        opf = next(z.read(n).decode() for n in z.namelist() if n.endswith('.opf'))
        ch = ''.join(z.read(n).decode() for n in z.namelist() if 'ch00' in n)
    assert '<dc:language>ru</dc:language>' in opf
    assert '[Milchin]' in ch and 'k01-выбор-материала' in ch and '«кавычками»' in ch


def _book(tmp_path, files, config=''):
    for name, text in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding='utf-8')
    if config:
        (tmp_path / 'mdbindery.yaml').write_text(config, encoding='utf-8')
    return tmp_path


@needs_pandoc
def test_structure_problems_are_repaired_consistently(tmp_path):
    """No level-1 heading, text above the title, a link outside the book without source_url,
    and split_level 2 must still give a valid EPUB whose word counts match."""
    book = _book(tmp_path / 'b', {
        '01-one.md': '# One\n\nFirst chapter text with enough words to count properly here.\n\n## Part\n\nMore text.\n',
        '02-two.md': '## Starts at level two\n\nSecond chapter body text, see the [license](LICENSE).\n',
        '03-three.md': 'Stray text above the title.\n\n# Three\n\nThird chapter body text.\n',
        '04-plain.md': 'Just text, no headings at all in this file.\n',
        'LICENSE': 'MIT\n',
    }, 'metadata:\n  title: T\n  identifier: urn:uuid:00000000-0000-4000-8000-000000000002\n'
       'options:\n  split_level: 2\n  ace: false\n')
    s = build(validate_if_installed(config.load(book)), out_dir=tmp_path / 'out', run_ace=False, log=lambda *_: None)
    assert s['ok'], (s['failed_gates'], s['gates'].get('wordcount'), s['gates'].get('epubcheck'))
    with zipfile.ZipFile(s['epub']) as z:
        nav = z.read('EPUB/nav.xhtml').decode()
    assert 'Starts at level two' in nav and 'Plain' in nav and '>Three<' in nav


def test_init_config_saves_identifier(tmp_path):
    book = _book(tmp_path, {'README.md': '# Book\n', '01-a.md': '# A\n'})
    cfg = config.load(book)
    (book / 'mdbindery.yaml').write_text(config.starter_yaml(cfg), encoding='utf-8')
    cfg = config.load(book)
    assert config.save_identifier(cfg, 'urn:uuid:abc')
    assert 'identifier: urn:uuid:abc' in (book / 'mdbindery.yaml').read_text()


@needs_pandoc
def test_check_respects_drop_lines_and_html_alt_rules(tmp_path):
    book = _book(tmp_path, {
        '01-a.md': ('# A\n\n![badge](https://img.shields.io/badge/x-y-blue)\n\n'
                    'Autolink <https://example.org> and <jane@example.org>.\n\n'
                    '<img src="images/p.png" alt="">\n\n<img src="images/p.png">\n\n![Root](/images/p.png)\n'),
    }, 'metadata:\n  title: T\n  authors: [X]\n  rights: MIT\noptions:\n  drop_lines: [\'img\\.shields\\.io\']\n')
    from PIL import Image
    (book / 'images').mkdir()
    Image.new('RGB', (10, 10)).save(book / 'images' / 'p.png')
    rep = check(str(book), render=False, log=lambda *_: None)
    codes = [(f['code'], f['line']) for f in rep.findings]
    assert not any(c == 'MB401' for c, _ in codes)          # badge line dropped
    assert not any(c == 'MB500' for c, _ in codes)          # autolinks are not HTML
    assert ('MB402', 9) in codes and ('MB402', 7) not in codes  # alt="" is decorative, no alt is not
    assert not any(c == 'MB400' for c, _ in codes)          # /images/... resolves from the book root


@needs_pandoc
def test_check_build_does_not_touch_config(tmp_path):
    book = _book(tmp_path, {'01-a.md': '# A\n\nText.\n'},
                 'metadata:\n  title: T\n  identifier:\noptions:\n  epubcheck: false\n')
    before = (book / 'mdbindery.yaml').read_text()
    check(str(book), do_build=True, render=False, log=lambda *_: None)
    assert (book / 'mdbindery.yaml').read_text() == before
