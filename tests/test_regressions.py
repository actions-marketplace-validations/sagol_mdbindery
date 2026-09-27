"""Regression tests for problems found in the pre-release audits."""
import html
import re
import zipfile

import pytest

from conftest import needs_pandoc, validate_if_installed
from mdbindery import cli, config, tools
from mdbindery.build import BuildError, analyze, build
from mdbindery.check import check

ID = 'urn:uuid:00000000-0000-4000-8000-000000000009'


def _book(root, files, cfg=''):
    root.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(text, bytes):
            p.write_bytes(text)
        else:
            p.write_text(text, encoding='utf-8')
    if cfg is not None:
        (root / 'mdbindery.yaml').write_text(f'metadata:\n  title: T\n  identifier: {ID}\n' + cfg, encoding='utf-8')
    return root


def _xhtml(epub):
    with zipfile.ZipFile(epub) as z:
        return ''.join(z.read(n).decode('utf-8') for n in z.namelist() if n.endswith('.xhtml'))


def _quiet(*_):
    pass


@needs_pandoc
def test_content_survives_conversion(tmp_path):
    book = _book(tmp_path / 'b', {
        '01-a.md': ('# A\n\nCited [1]. Code `a[1]` and:\n\n```python\ndef f():\n    return arr[1]\n\n\n'
                    'def g():\n    pass\n```\n\n    indented[1] = 0\n\n$v[1]$ and https://x.example/a[1]\n\n'
                    '> <p>Quoted <a href="02-b.md#sec">link</a></p>\n>\n> <Listing number="1">\n>\n> Inside.\n>\n'
                    '> </Listing>\n\nx <img src="images/p.png" alt="R&amp;D"> y and '
                    '<a href="https://example.org/?a=1&amp;b=2">q</a>.\n\n'
                    'Note[^n].\n\n[^n]: The note.\n\n## References\n\n[1]: https://ref.example "Ref"\n'),
        '02-b.md': '# B\n\n## Sec\n\nText.\n',
    }, 'options:\n  ace: false\n')
    from PIL import Image
    (book / 'images').mkdir()
    Image.new('RGB', (10, 10), 'white').save(book / 'images' / 'p.png')
    s = build(validate_if_installed(config.load(book)), out_dir=tmp_path / 'out', run_ace=False, log=_quiet)
    assert s['ok'], (s['failed_gates'], s['gates'])
    x = _xhtml(s['epub'])
    plain = html.unescape(re.sub(r'<[^>]+>', '', x))
    assert 'return arr[1]\n\n\ndef g()' in plain                   # code intact, blank lines kept
    assert 'indented[1] = 0' in plain and 'a[1]</code>' in x
    assert 'class="citation"' in x and 'k00-ref-1"' in x
    assert 'Listing' not in x and 'Inside.' in x                   # unknown tag dropped, text kept
    assert 'href="ch002.xhtml#k01-sec"' in x                        # link inside quoted HTML resolved
    assert 'alt="R&amp;D"' in x and '?a=1&amp;b=2"' in x            # entities decoded once
    assert 'role="doc-backlink">1.</a>' in x                        # numbered endnote with a back-link


@needs_pandoc
def test_links_that_leave_the_book_folder(tmp_path):
    repo = tmp_path / 'repo'
    _book(repo, {'preface.md': '# P\n', 'src/code.py': 'x = 1\n'}, None)
    book = _book(repo / 'book', {'01-a.md': '# A\n\n[preface](../preface.md), [code](../src/code.py), '
                                            '[root](/src/code.py), [gone](../missing.md)\n'},
                 'source_url: https://github.com/o/r/blob/main/book/\n')
    cfg = config.load(book, repo_root=repo)
    (tmp_path / 'w').mkdir()
    a = analyze(cfg, tmp_path / 'w', log=_quiet)
    ext = {e['path']: e for e in a['files']['01-a.md']['report']['external']}
    assert ext['../preface.md']['exists'] and ext['../src/code.py']['exists']
    assert not ext['../missing.md']['exists']
    linked = (tmp_path / 'w' / 'linked.json').read_text()
    assert 'https://github.com/o/r/blob/main/preface.md' in linked
    assert 'https://github.com/o/r/blob/main/src/code.py' in linked


@needs_pandoc
def test_title_promotion_skips_anchors_and_comments(tmp_path):
    book = _book(tmp_path / 'b', {'01-a.md': '<!-- old headings -->\n<a id="old"></a>\n\n## The match\n\nText.\n',
                                  '02-b.md': '## Intro\n\nText.\n'},
                 'files:\n  - 01-a.md\n  - file: 02-b.md\n    title: Intro\n')
    (tmp_path / 'w').mkdir()
    a = analyze(config.load(book), tmp_path / 'w', log=_quiet)
    assert a['files']['01-a.md']['report']['h1_fix'] == 'promoted'
    assert a['h1']['k00'] == 'k00-the-match'
    assert a['h1']['k01'] == 'k01-intro-1'                          # the title heading gets a unique id


@needs_pandoc
def test_untrusted_book_cannot_embed_outside_images(tmp_path):
    from PIL import Image
    Image.new('RGB', (5, 5)).save(tmp_path / 'secret.png')
    book = _book(tmp_path / 'repo', {'01-a.md': '# A\n\n![s](../secret.png)\n\n![abs](/etc/hostname)\n'}, '')
    cfg = config.load(book, trusted=False, repo_root=book)
    (tmp_path / 'w').mkdir()
    a = analyze(cfg, tmp_path / 'w', log=_quiet)
    status = {i['src']: i['status'] for i in a['files']['01-a.md']['report']['images']}
    assert status == {'../secret.png': 'outside', '/etc/hostname': 'missing'}


@needs_pandoc
def test_metadata_is_literal_text(tmp_path):
    book = _book(tmp_path / 'b', {'01-a.md': '# A\n\nText.\n'}, None)
    (book / 'mdbindery.yaml').write_text(
        f'metadata:\n  title: "Using <div> tags *and* C_sharp_ [draft]"\n  identifier: {ID}\n'
        '  description: "Covers *nix tools & <b>markup</b>, mail me@example.org"\noptions:\n  ace: false\n')
    s = build(validate_if_installed(config.load(book)), out_dir=tmp_path / 'out', run_ace=False, log=_quiet)
    with zipfile.ZipFile(s['epub']) as z:
        opf = next(z.read(n).decode() for n in z.namelist() if n.endswith('.opf'))
    assert 'Using &lt;div&gt; tags *and* C_sharp_ [draft]' in opf
    assert 'Covers *nix tools &amp; &lt;b&gt;markup&lt;/b&gt;, mail me@example.org' in opf


@needs_pandoc
def test_build_keeps_foreign_files_in_reports(tmp_path):
    book = _book(tmp_path / 'b', {'01-a.md': '# A\n\nText.\n'}, 'options:\n  ace: false\n  epubcheck: false\n')
    out = tmp_path / 'out'
    (out / 'reports').mkdir(parents=True)
    (out / 'reports' / 'q3-report.txt').write_text('mine')
    (out / 'reports' / 'build.json').write_text('stale')
    build(config.load(book), out_dir=out, run_ace=False, log=_quiet)
    assert (out / 'reports' / 'q3-report.txt').read_text() == 'mine'
    assert (out / 'reports' / 'build.json').read_text() != 'stale'


@needs_pandoc
def test_build_input_errors(tmp_path):
    empty = _book(tmp_path / 'e', {}, '')
    with pytest.raises(BuildError, match='no Markdown files'):
        build(config.load(empty), out_dir=tmp_path / 'o1', log=_quiet)
    assert 'identifier' in (empty / 'mdbindery.yaml').read_text()
    latin = _book(tmp_path / 'l', {'01-a.md': '# Café\n'.encode('latin-1')}, '')
    with pytest.raises(BuildError, match='not valid UTF-8'):
        build(config.load(latin), out_dir=tmp_path / 'o2', log=_quiet)


@needs_pandoc
def test_check_build_reports_failed_gates(tmp_path, monkeypatch):
    book = _book(tmp_path / 'b', {'01-a.md': '# A\n\nText.\n'}, 'options:\n  ace: false\n')
    monkeypatch.setattr(tools, 'epubcheck_cmd', lambda: None)
    rep = check(str(book), do_build=True, render=False, log=_quiet)
    assert not rep.ok
    assert any(f['code'] == 'MB904' and 'epubcheck' in f['message'] for f in rep.findings)


@needs_pandoc
def test_check_reads_comments_and_indented_code_correctly(tmp_path):
    book = _book(tmp_path / 'b', {'01-a.md': ('<!-- markdownlint-disable -->\n# A\n\n<!--\n# Old\n![o](gone.png)\n'
                                               '<iframe></iframe>\n-->\n\nText:\n\n    <script src="a.js"></script>\n\n'
                                               '- step\n\n    ```bash\n    echo <YOUR_NAME>\n    ```\n\n'
                                               'Price $5 and $HOME/bin or $PATH.\n')}, 'metadata:\n  authors: [X]\n'
                 '  rights: MIT\n')
    rep = check(str(book), render=False, log=_quiet)
    codes = {f['code'] for f in rep.findings}
    assert not codes & {'MB107', 'MB400', 'MB500', 'MB110'}, rep.findings


def test_cli_errors_are_one_line(tmp_path, capsys):
    assert cli.main(['init', str(tmp_path / 'missing')]) == 2
    assert cli.main(['preview', str(tmp_path / 'no.epub'), str(tmp_path / 'shots')]) == 2
    (tmp_path / 'x.md').write_text('# x')
    assert cli.main(['preview', str(tmp_path / 'x.md'), str(tmp_path / 'shots')]) == 2
    assert not (tmp_path / 'shots').exists()
    assert cli.main(['check', str(tmp_path / 'nope')]) == 2
    err = capsys.readouterr().err
    assert 'Traceback' not in err and 'folder not found' in err
    assert cli.main([]) == 0


def test_init_force_keeps_identifier_and_makes_a_backup(tmp_path):
    book = _book(tmp_path, {'01-a.md': '# A\n'}, 'options:\n  toc_depth: 3\n')
    assert cli.main(['init', str(book)]) == 1
    assert cli.main(['init', str(book), '--force']) == 0
    text = (book / 'mdbindery.yaml').read_text()
    assert ID in text and 'toc_depth: 3' in text
    assert (book / 'mdbindery.yaml.bak').exists()
    empty = tmp_path / 'empty'
    empty.mkdir()
    assert cli.main(['init', str(empty)]) == 1 and not (empty / 'mdbindery.yaml').exists()


@needs_pandoc
def test_image_url_of_the_same_repository_uses_the_local_file(tmp_path):
    from PIL import Image
    book = _book(tmp_path / 'b', {'01-a.md': ('# A\n\n![Chart](https://github.com/O/R/blob/main/images/p.png?raw=true)\n\n'
                                              '![Other](https://raw.githubusercontent.com/o/r/main/images/p.png)\n\n'
                                              '![Remote](https://example.org/x.png)\n')},
                 'source_url: https://github.com/o/r/blob/main/\n')
    (book / 'images').mkdir()
    Image.new('RGB', (10, 10)).save(book / 'images' / 'p.png')
    (tmp_path / 'w').mkdir()
    a = analyze(config.load(book), tmp_path / 'w', log=_quiet)
    imgs = a['files']['01-a.md']['report']['images']
    assert [(i['status'], i.get('local_copy')) for i in imgs] == [('ok', 'images/p.png'), ('ok', 'images/p.png'),
                                                                  ('remote', None)]
    linked = (tmp_path / 'w' / 'linked.json').read_text()
    assert '"missing-image"' in linked and '"Remote]"' in linked      # a text placeholder, not a broken path


@needs_pandoc
def test_links_from_the_repository_root_and_folder_index_pages(tmp_path):
    repo = tmp_path / 'repo'
    book = _book(repo / 'book', {'01-a.md': '# A\n\n[two](/book/02-b.md#sec), [guide](guide/index.html), [dir](guide/)\n',
                                 '02-b.md': '# B\n\n## Sec\n', 'guide/README.md': '# Guide\n'},
                 'files: [01-a.md, 02-b.md, guide/README.md]\n')
    (tmp_path / 'w').mkdir()
    a = analyze(config.load(book, repo_root=repo), tmp_path / 'w', log=_quiet)
    rep = a['files']['01-a.md']['report']
    assert rep['external'] == [] and rep['html_links'] == 2
    assert not a['links']['unresolved']


@needs_pandoc
def test_title_override_keeps_anchors_in_the_heading(tmp_path):
    book = _book(tmp_path / 'b', {'01-a.md': '# Old <a id="keep"></a>\n\nText.\n',
                                  '02-b.md': '# B\n\n[back](01-a.md#keep)\n'},
                 'files:\n  - file: 01-a.md\n    title: New\n  - 02-b.md\n')
    (tmp_path / 'w').mkdir()
    a = analyze(config.load(book), tmp_path / 'w', log=_quiet)
    assert not a['links']['unresolved'] and 'k00-keep' in a['files']['01-a.md']['report']['ids']


def test_image_definitions_are_not_citations():
    from mdbindery.markdown import prepass
    src = '# T\n\n![Pic][pic] and [Smith]\n\n[pic]: images/a.png "A"\n[logo]: img/logo.svg\n[Smith]: https://s.example "S"\n'
    _, stats = prepass(src, {}, {'citations': 'refdefs', 'citation_labels': 'all', 'reference_headings': []})
    assert [c['label'] for c in stats['citations']] == ['Smith']


@needs_pandoc
def test_check_false_positives_are_gone(tmp_path):
    book = _book(tmp_path / 'b', {'01-a.md': ('---\ntitle: X\n---\n\n# A\n\nUse `![a](x.png)` in Markdown, set '
                                               '[`build.dir`] and write <YOUR_NAME> here.\n\n> Quote[^q].\n>\n'
                                               '> [^q]: A note in the quote.\n\n[`build.dir`]: https://x.example/b\n')},
                 'metadata:\n  authors: [X]\n  rights: MIT\n')
    rep = check(str(book), render=False, log=_quiet)
    codes = {f['code'] for f in rep.findings}
    assert 'MB111' in codes
    assert not codes & {'MB400', 'MB304', 'MB300', 'MB500', 'MB110'}, rep.findings


def test_config_details(tmp_path):
    lic = tmp_path / 'lic'
    lic.mkdir()
    (lic / 'LICENSE').write_text('                                 Apache License\n'
                                 '                           Version 2.0, January 2004\n')
    assert config.detect_rights(lic) == 'Apache License 2.0'
    mb = tmp_path / 'mb'
    _book(mb, {'book.toml': '[book]\ntitle = "T"\n', 'src/SUMMARY.md': '- [One](ch1.md)\n', 'src/ch1.md': '# One\n',
               'src/README.md': '# Readme\n'}, None)
    cfg = config.load(mb)
    assert [f['file'] for f in cfg['files']] == ['ch1.md']       # mdBook: README only if SUMMARY lists it
    ext = tmp_path / 'ext'
    ext.mkdir()
    (ext / 'mdbindery.yaml').write_text('source_dir: ../mb\n')
    assert config.load(ext / 'mdbindery.yaml').source == (mb / 'src').resolve()


def test_check_report_into_a_new_folder(tmp_path):
    book = _book(tmp_path / 'b', {'01-a.md': '# A\n'}, '')
    out = tmp_path / 'new' / 'dir' / 'r.md'
    assert cli.main(['check', str(book), '--no-render', '-q', '--report', str(out)]) in (0, 1)
    assert out.exists()


@needs_pandoc
def test_file_urls_and_single_outside_finding(tmp_path):
    from PIL import Image
    book = _book(tmp_path / 'b', {}, 'metadata:\n  authors: [X]\n  rights: MIT\n')
    (book / 'images').mkdir()
    Image.new('RGB', (10, 10)).save(book / 'images' / 'p.png')
    absolute = (book / 'images' / 'p.png').resolve().as_posix()
    (book / '01-a.md').write_text(f'# A\n\n![a](file:images/p.png) ![b](file://images/p.png) ![c](file://{absolute})\n')
    rep = check(str(book), render=False, log=_quiet)
    assert not [f for f in rep.findings if f['code'] in ('MB400', 'MB401')], rep.findings
    (tmp_path / 'w').mkdir()
    a = analyze(config.load(book), tmp_path / 'w', log=_quiet)
    assert [i['status'] for i in a['files']['01-a.md']['report']['images']] == ['ok', 'ok', 'ok']
    from PIL import Image as I2
    I2.new('RGB', (5, 5)).save(tmp_path / 'out.png')
    (book / '01-a.md').write_text('# A\n\n![o](../out.png)\n')
    from mdbindery.check import Report, _check
    r = _check(book, None, Report(str(book)), None, False, False, _quiet, remote=True, repo_root=book)
    assert [f['code'] for f in r.findings].count('MB406') == 1


@needs_pandoc
def test_mdbook_outside_git_figures_and_website_links(tmp_path):
    root = _book(tmp_path / 'mb', {
        'book.toml': '[book]\ntitle = "T"\n', 'listings/a.rs': 'fn main() {}\n',
        'src/SUMMARY.md': '- [One](ch1.md)\n',
        'src/ch1.md': ('# One\n\n```rust\n{{#include ../listings/a.rs}}\n```\n\n'
                       '<figure><img src="p.png" alt="P"><figcaption>Cap</figcaption></figure>\n\n'
                       '[guide](../guide/start.md)\n'),
    }, None)
    (root / 'mdbindery.yaml').write_text('source_url: https://docs.example.org/book/\n')
    from PIL import Image
    Image.new('RGB', (10, 10)).save(root / 'src' / 'p.png')
    cfg = config.load(root)
    assert cfg.repo_root == root.resolve() and cfg.mdbook
    (tmp_path / 'w').mkdir()
    a = analyze(cfg, tmp_path / 'w', log=_quiet)
    st, rep = a['files']['ch1.md']['stats'], a['files']['ch1.md']['report']
    assert st['includes'] == 1 and not st['include_errors']
    assert [(i['kind'], i['status']) for i in rep['images']] == [('figure', 'ok')]
    assert 'https://docs.example.org/guide/start.html' in (tmp_path / 'w' / 'linked.json').read_text()
    gitbook = _book(tmp_path / 'gb', {'SUMMARY.md': '- [A](a.md)\n', 'a.md': '# A\n'}, None)
    assert not config.load(gitbook).mdbook


# ------------------------------------------------------------ second audit (2026-09)

def _symlink(link, target):
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip('symlinks are not available here')


@needs_pandoc
def test_checked_repository_never_reads_through_symlinks(tmp_path):
    from PIL import Image
    (tmp_path / 'outside.md').write_text('# SENTINEL\n\nOutside text.\n')
    Image.new('RGB', (2, 2)).save(tmp_path / 'outside.png')
    repo = _book(tmp_path / 'repo', {'01-a.md': '# A\n\n![i](image.png)\n'}, None)
    _symlink(repo / '02-b.md', tmp_path / 'outside.md')
    _symlink(repo / 'image.png', tmp_path / 'outside.png')
    _symlink(repo / 'cover.png', tmp_path / 'outside.png')
    cfg = config.load(repo, trusted=False, repo_root=repo)
    assert [f['file'] for f in cfg['files']] == ['01-a.md'] and not cfg['cover']['image']
    (tmp_path / 'w').mkdir()
    a = analyze(cfg, tmp_path / 'w', log=_quiet)
    assert [i['status'] for i in a['files']['01-a.md']['report']['images']] == ['outside']
    assert len(config.load(repo)['files']) == 2  # a local book the user owns may use links
    (repo / 'mdbindery.yaml').write_text('files: [01-a.md, 02-b.md]\n')
    with pytest.raises(config.ConfigError, match='files entry 02-b.md points outside'):
        config.load(repo, trusted=False, repo_root=repo)
    (repo / 'mdbindery.yaml').unlink()
    (tmp_path / 'outside.yaml').write_text('metadata:\n  title: Outside\n')
    _symlink(repo / 'mdbindery.yaml', tmp_path / 'outside.yaml')
    with pytest.raises(config.ConfigError, match='points outside the repository'):
        config.load(repo, trusted=False, repo_root=repo)


def test_fetched_checkout_loses_escaping_symlinks(tmp_path):
    from mdbindery.check import Report, check_images, remove_escaping_symlinks
    (tmp_path / 'secret.png').write_bytes(b'x')
    repo = _book(tmp_path / 'repo', {'images/p.png': b'png', 'docs/a.md': '# A\n'}, None)
    _symlink(repo / 'images' / 'out.png', tmp_path / 'secret.png')
    _symlink(repo / 'docs' / 'in.png', repo / 'images' / 'p.png')
    assert remove_escaping_symlinks(repo) == ['images/out.png']
    assert (repo / 'docs' / 'in.png').is_symlink() and not (repo / 'images' / 'out.png').exists()
    # an image URL of the same repository is held to the same boundary as a relative path
    rep = Report(str(repo))
    line = '![x](https://github.com/o/r/raw/main/../secret.png)'
    check_images([line], repo / 'docs' / 'a.md', 'docs/a.md', rep, repo, repo, 'o/r', {}, strict_root=repo)
    assert [(f['code'], f['severity']) for f in rep.findings] == [('MB406', 'error')]


@needs_pandoc
def test_cards_keep_every_row_and_the_word_count_stays_exact(tmp_path, monkeypatch):
    table = ('<table>\n<thead><tr><th>Name</th><th>Value</th></tr><tr><th>sub a</th><th>sub b</th></tr></thead>\n'
             '<tbody><tr><td>Item</td><td>BODY</td></tr></tbody>\n'
             '<tfoot><tr><td>Total</td><td>' + 'FOOTER ' * 60 + '</td></tr></tfoot>\n</table>\n')
    book = _book(tmp_path / 'b', {'01-a.md': '# A\n\nIntro prose.\n\n' + table},
                 'options:\n  ace: false\n  epubcheck: false\n  cards:\n    files: [01-a.md]\n    min_columns: 2\n')
    s = build(config.load(book), out_dir=tmp_path / 'out', run_ace=False, log=_quiet)
    x = _xhtml(s['epub'])
    assert x.count('FOOTER') == 60 and 'sub a' in x and 'BODY' in x and 'class="card"' in x
    wc = s['gates']['wordcount']
    f = wc['files']['01-a.md']
    assert wc['result'] == 'pass' and f.get('compared', f['epub']) == f['source'], f
    # a chapter with cards is not exempt: prose lost from it fails the gate
    import mdbindery.build as build_mod
    real = build_mod.xhtml_text
    monkeypatch.setattr(build_mod, 'xhtml_text', lambda t: real(t).replace('FOOTER', ''))
    s = build(config.load(book), out_dir=tmp_path / 'out2', run_ace=False, log=_quiet)
    assert s['gates']['wordcount']['failing'] == ['01-a.md']


@needs_pandoc
def test_each_html_image_keeps_its_own_alt_text(tmp_path):
    from PIL import Image
    book = _book(tmp_path / 'b', {'01-a.md': ('# A\n\n<div>\n<img src="p.png" alt="A chart">\n'
                                              '<!-- <img src="p.png" alt="old"> -->\n<img src="p.png">\n</div>\n')},
                 'options:\n  ace: false\n  epubcheck: false\n')
    Image.new('RGB', (2, 2)).save(book / 'p.png')
    s = build(config.load(book), out_dir=tmp_path / 'out', run_ace=False, log=_quiet)
    assert [bool(i.get('alt')) for i in s['files']['01-a.md']['images']] == [True, False]
    with zipfile.ZipFile(s['epub']) as z:
        opf = next(z.read(n).decode() for n in z.namelist() if n.endswith('.opf'))
    assert '>alternativeText<' not in opf and 'some images have no text alternative' in opf


def test_config_rejects_non_finite_numbers_and_impossible_dates(tmp_path):
    for opt in ('wordcount_tolerance: .nan', 'toc_depth: .inf', 'mermaid_scale: -.inf'):
        book = _book(tmp_path / opt.split(':')[0], {'01-a.md': '# A\n'}, f'options:\n  {opt}\n')
        with pytest.raises(config.ConfigError, match='finite number'):
            config.load(book)
    for date, ok in (('2026-99-99', False), ('2026-02-30', False), ('26-09', False),
                     ('2026', True), ('2026-09', True), ('2026-09-26', True)):
        assert config.valid_date(date) is ok, date


def test_include_cycles_and_depth_are_reported(tmp_path):
    from mdbindery.markdown import INCLUDE_MAX_DEPTH, expand_includes
    (tmp_path / 'a.md').write_text('A {{#include b.md}}\n')
    (tmp_path / 'b.md').write_text('B {{#include a.md}}\n')
    text, n, errors = expand_includes('{{#include a.md}}', tmp_path, tmp_path, origin=tmp_path / 'ch.md')
    assert n == 2 and '{{#include a.md}}' in text
    assert [e for _, e in errors] == ['include cycle: ch.md -> a.md -> b.md -> a.md']
    for i in range(INCLUDE_MAX_DEPTH + 1):
        (tmp_path / f'd{i}.md').write_text(f'level{i} {{{{#include d{i + 1}.md}}}}' if i < INCLUDE_MAX_DEPTH else 'end')
    text, n, errors = expand_includes('{{#include d0.md}}', tmp_path, tmp_path, origin=tmp_path / 'ch.md')
    assert n == INCLUDE_MAX_DEPTH and 'end' not in text
    assert [e for _, e in errors] == [f'includes nested deeper than {INCLUDE_MAX_DEPTH} levels']


@needs_pandoc
def test_failed_build_leaves_its_own_diagnostics(tmp_path, monkeypatch, capsys):
    import mdbindery.build as build_mod
    book = _book(tmp_path / 'b', {'01-a.md': '# A\n\nText.\n'}, 'options:\n  ace: false\n  epubcheck: false\n')
    out = tmp_path / 'out'
    (out / 'reports').mkdir(parents=True)
    (out / 'reports' / 'build.json').write_text('previous report')
    (out / 't.epub').write_bytes(b'previous epub')

    def broken(*_a, **_k):
        raise BuildError('synthetic failure')
    monkeypatch.setattr(build_mod, 'gate_wordcount', broken)
    assert cli.main(['build', str(book), '--out', str(out), '--no-ace', '-q']) == 2
    import json
    s = json.loads((out / 'reports' / 'build.json').read_text())
    assert s['ok'] is False and s['failed_stage'] == 'wordcount' and 'synthetic failure' in s['error']
    assert s['provenance']['pandoc'] and 'epub' in s['timings']
    assert 'build error: synthetic failure' in (out / 'reports' / 'build.log').read_text()
    assert (out / 't.epub').read_bytes() != b'previous epub'  # this build's EPUB, not the earlier one
    monkeypatch.setattr(build_mod, 'analyze', broken)
    (out / 't.epub').write_bytes(b'previous epub')
    with pytest.raises(BuildError):
        build(config.load(book), out_dir=out, run_ace=False, log=_quiet)
    s = json.loads((out / 'reports' / 'build.json').read_text())
    assert s['failed_stage'] == 'analysis' and s['artifact'].startswith('an EPUB from an earlier build')


@needs_pandoc
def test_check_build_converts_each_file_once(tmp_path, monkeypatch):
    book = _book(tmp_path / 'b', {f'{i:02}.md': f'# Chapter {i}\n\nSome prose here.\n' for i in range(5)},
                 'metadata:\n  authors: [X]\n  rights: MIT\noptions:\n  ace: false\n  epubcheck: false\n')
    real, calls = tools.run_process, []

    def counted(cmd, *a, **k):
        if 'pandoc' in str(cmd[0]).lower():
            calls.append(cmd)
        return real(cmd, *a, **k)
    monkeypatch.setattr(tools, 'run_process', counted)
    assert build(config.load(book), out_dir=tmp_path / 'o1', run_ace=False, log=_quiet)['ok']
    alone = len(calls)
    calls.clear()
    assert check(str(book), do_build=True, render=False, log=_quiet).ok
    assert len(calls) == alone, (alone, len(calls))


def test_run_process_stops_the_whole_tree_on_timeout(tmp_path):
    import os
    import sys
    import time
    pid_file = tmp_path / 'child.pid'
    code = ('import subprocess, sys, time; '
            'p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"]); '
            f'open({str(pid_file)!r}, "w").write(str(p.pid)); print("x" * 10000); time.sleep(60)')
    start = time.monotonic()
    r = tools.run_process([sys.executable, '-c', code], timeout=tools.deadline(3), tail=100)
    assert r.returncode == -9 and r.timed_out and 'stopped after' in r.stderr
    assert time.monotonic() - start < 30 and len(r.stdout) <= 100
    if os.name == 'posix':
        child = int(pid_file.read_text())
        for _ in range(50):
            try:
                os.kill(child, 0)
            except ProcessLookupError:
                break
            time.sleep(0.1)
        else:
            pytest.fail('grandchild process still running')


def test_failed_tool_update_keeps_the_working_version(tmp_path, monkeypatch):
    from mdbindery import installer
    target = tmp_path / 'tools' / 'pandoc'
    (target / 'bin').mkdir(parents=True)
    (target / 'bin' / 'pandoc').write_text('old')
    (target / '.mdbindery-version').write_text('1.0')
    new = tmp_path / 'dl' / 'pandoc-2.0' / 'bin'
    new.mkdir(parents=True)
    (new / 'pandoc').write_text('new')

    def bad(folder):
        raise RuntimeError('does not run')
    with pytest.raises(RuntimeError, match='does not run'):
        installer._place(new / 'pandoc', target, '2.0', check=bad)
    assert (target / 'bin' / 'pandoc').read_text() == 'old' and installer._installed(target, '1.0')
    assert sorted(p.name for p in target.parent.iterdir()) == ['pandoc']
    new.mkdir(parents=True, exist_ok=True)
    (new / 'pandoc').write_text('new')
    installer._place(new / 'pandoc', target, '2.0', check=lambda folder: None)
    assert (target / 'bin' / 'pandoc').read_text() == 'new' and installer._installed(target, '2.0')
    assert sorted(p.name for p in target.parent.iterdir()) == ['pandoc']
    # the smoke test runs the binary where it landed, also when the archive has no bin/ (pandoc on Windows)
    flat = tmp_path / 'dl' / 'pandoc-3.0'
    flat.mkdir(parents=True)
    (flat / 'pandoc.exe').write_text('flat')
    started = []
    monkeypatch.setattr(installer, '_runs', lambda rel, *args: lambda folder: started.append((folder / rel, args)))
    installer._place(flat / 'pandoc.exe', target, '3.0', smoke=('--version',))
    assert started == [(target / 'pandoc.exe', ('--version',))] and (target / 'pandoc.exe').is_file()


def test_one_tool_install_at_a_time(tmp_path, monkeypatch):
    from mdbindery import installer
    monkeypatch.setenv('MDBINDERY_HOME', str(tmp_path))
    tools.tools_dir().mkdir(parents=True)
    lock = installer._lock()
    with pytest.raises(RuntimeError, match='another `mdbindery install-tools` is running'):
        installer._lock()
    lock.unlink()
    installer._lock().unlink()
