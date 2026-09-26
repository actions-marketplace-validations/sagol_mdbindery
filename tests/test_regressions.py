"""Regression tests for problems found in the pre-release audits."""
import html
import re
import zipfile

import pytest

from conftest import needs_epubcheck, needs_pandoc
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
@needs_epubcheck
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
    s = build(config.load(book), out_dir=tmp_path / 'out', run_ace=False, log=_quiet)
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
@needs_epubcheck
def test_metadata_is_literal_text(tmp_path):
    book = _book(tmp_path / 'b', {'01-a.md': '# A\n\nText.\n'}, None)
    (book / 'mdbindery.yaml').write_text(
        f'metadata:\n  title: "Using <div> tags *and* C_sharp_ [draft]"\n  identifier: {ID}\n'
        '  description: "Covers *nix tools & <b>markup</b>, mail me@example.org"\noptions:\n  ace: false\n')
    s = build(config.load(book), out_dir=tmp_path / 'out', run_ace=False, log=_quiet)
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
