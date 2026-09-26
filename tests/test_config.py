
import pytest

from mdbindery import config


def write(p, text):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding='utf-8')


def test_inferred_order_title_rights_and_cover(tmp_path):
    write(tmp_path / 'README.md', '# My Book\n')
    write(tmp_path / '10-ten.md', '# Ten\n')
    write(tmp_path / '2-two.md', '# Two\n')
    write(tmp_path / 'appendix-a.md', '# A\n')
    write(tmp_path / 'CONTRIBUTING.md', '# How to contribute\n')
    write(tmp_path / 'LICENSE', 'SPDX-License-Identifier: CC-BY-4.0\n')
    (tmp_path / 'images').mkdir()
    (tmp_path / 'images' / 'cover.jpg').write_bytes(b'x')
    cfg = config.load(tmp_path)
    assert [f['file'] for f in cfg['files']] == ['README.md', '2-two.md', '10-ten.md', 'appendix-a.md']
    assert cfg.meta['title'] == 'My Book'
    assert cfg.meta['rights'] == 'CC BY 4.0'
    assert cfg['cover']['image'] == 'images/cover.jpg'
    assert cfg['slug'] == 'my-book'
    assert cfg.path is None and 'files (reading order)' in cfg.inferred


def test_chapters_folder_is_used(tmp_path):
    write(tmp_path / 'README.md', '# Book\n')
    write(tmp_path / 'chapters' / '01-a.md', '# A\n')
    write(tmp_path / 'notes.md', '# not a chapter\n')
    cfg = config.load(tmp_path)
    assert [f['file'] for f in cfg['files']] == ['README.md', 'chapters/01-a.md']


def test_language_guess(tmp_path):
    write(tmp_path / '01.md', '# Глава\n\nЭто текст на русском языке, достаточно длинный для проверки.\n')
    assert config.load(tmp_path).meta['lang'] == 'ru'


def test_unknown_keys_are_reported(tmp_path):
    write(tmp_path / '01.md', '# A\n')
    write(tmp_path / 'mdbindery.yaml', 'metadata:\n  title: X\n  tittle: Y\noptions:\n  toc_dept: 2\n')
    cfg = config.load(tmp_path)
    joined = ' '.join(cfg.warnings)
    assert 'options.toc_dept (did you mean "toc_depth"?)' in joined and 'metadata.tittle' in joined


def test_unknown_top_level_key_is_an_error(tmp_path):
    write(tmp_path / '01.md', '# A\n')
    write(tmp_path / 'mdbindery.yaml', 'metdata:\n  title: X\n')
    with pytest.raises(config.ConfigError, match='did you mean "metadata"'):
        config.load(tmp_path)


@pytest.mark.parametrize('yaml_text, message', [
    ('metadata:\n  lang: no\n', 'quotes'),
    ('options:\n  toc_depth: two\n', 'toc_depth must be a number'),
    ('options:\n  mermaid_scale: "2&calc.exe"\n', 'mermaid_scale must be a number'),
    ('options:\n  drop_lines: ["[x"]\n', 'invalid pattern'),
    ('options:\n  css: nope.css\n', 'file not found'),
    ('slug: ../../leak\n', 'slug may use'),
    ('files:\n  - ../outside.md\n', 'relative to the book folder'),
    ('metadata:\n  title: [unclosed\n', r'mdbindery.yaml, line \d+, column \d+'),
])
def test_bad_values_are_config_errors(tmp_path, yaml_text, message):
    write(tmp_path / '01.md', '# A\n')
    write(tmp_path / 'mdbindery.yaml', yaml_text)
    with pytest.raises(config.ConfigError, match=message):
        config.load(tmp_path)


def test_scalar_values_are_coerced(tmp_path):
    write(tmp_path / '01.md', '# A\n')
    write(tmp_path / 'mdbindery.yaml', "metadata:\n  title: 1984\n  date: 1965-05-01\n  authors: Jane Doe\n"
          "  identifier: ~\nfiles:\n  - ./01.md\n")
    cfg = config.load(tmp_path)
    assert cfg.meta['title'] == '1984' and cfg.meta['date'] == '1965-05-01'
    assert cfg.meta['authors'] == ['Jane Doe'] and cfg.meta['identifier'] == ''
    assert cfg['files'][0]['file'] == '01.md'


def test_untrusted_paths_must_stay_in_the_repository(tmp_path):
    write(tmp_path / 'secret.css', 'x')
    write(tmp_path / 'repo' / '01.md', '# A\n')
    write(tmp_path / 'repo' / 'mdbindery.yaml', 'options:\n  css: ../secret.css\n')
    config.load(tmp_path / 'repo')  # a local book may use a shared stylesheet
    with pytest.raises(config.ConfigError, match='inside the repository'):
        config.load(tmp_path / 'repo', trusted=False, repo_root=tmp_path / 'repo')


def test_reading_order_from_toc_and_names(tmp_path):
    for n in ('ch1', 'ch2', 'apA', 'foreword'):
        write(tmp_path / f'{n}.md', f'# {n}\n')
    write(tmp_path / 'README.md', '# Book\n')
    cfg = config.load(tmp_path)
    assert [f['file'] for f in cfg['files']] == ['README.md', 'foreword.md', 'ch1.md', 'ch2.md', 'apA.md']
    write(tmp_path / 'toc.md', '* [Two](ch2.md)\n* [One](ch1.md)\n* [Preface](../preface.md)\n')
    cfg = config.load(tmp_path)
    assert [f['file'] for f in cfg['files']][:3] == ['README.md', 'ch2.md', 'ch1.md']
    assert 'toc.md' not in [f['file'] for f in cfg['files']] and cfg.order_source.startswith('toc.md')


def test_numbered_files_win_over_readme_links(tmp_path):
    write(tmp_path / 'README.md', '# Book\n\nSee [chapter 2](02-b.md) first.\n\n- [A](01-a.md)\n- [B](02-b.md)\n'
          '- [C](03-c.md)\n')
    for n in ('01-a', '02-b', '03-c', 'appendix-a'):
        write(tmp_path / f'{n}.md', f'# {n}\n')
    cfg = config.load(tmp_path)
    assert [f['file'] for f in cfg['files']] == ['README.md', '01-a.md', '02-b.md', '03-c.md', 'appendix-a.md']
    assert cfg.order_source == 'file names'


def test_mdbook_layout(tmp_path):
    write(tmp_path / 'book.toml', '[book]\ntitle = "The Book"\nauthors = ["A. Author"]\nsrc = "src"\n')
    write(tmp_path / 'src' / 'SUMMARY.md', '# Summary\n\n[Intro](title-page.md)\n\n- [One](ch01.md)\n'
          '    - [Sub](ch01-01.md)\n- [Draft]()\n')
    for n in ('title-page', 'ch01', 'ch01-01', 'unused'):
        write(tmp_path / 'src' / f'{n}.md', f'# {n}\n')
    cfg = config.load(tmp_path)
    assert cfg.source == (tmp_path / 'src').resolve() and cfg.mdbook
    assert [f['file'] for f in cfg['files']] == ['title-page.md', 'ch01.md', 'ch01-01.md']
    assert cfg.meta['title'] == 'The Book' and cfg.meta['authors'] == ['A. Author']


@pytest.mark.parametrize('text, label', [
    ('GNU LESSER GENERAL PUBLIC LICENSE\nVersion 3\n... GNU General Public License ...', 'GNU LGPL'),
    ('GNU AFFERO GENERAL PUBLIC LICENSE\n', 'GNU AGPL'),
    ('Creative Commons Attribution-ShareAlike 3.0 Unported\n', 'CC BY-SA 3.0'),
    ('SPDX-License-Identifier: CC-BY-NC-4.0\n', 'CC BY-NC 4.0'),
])
def test_license_names(tmp_path, text, label):
    write(tmp_path / 'LICENSE', text)
    assert config.detect_rights(tmp_path) == label


def test_external_config_with_source_dir(tmp_path):
    book = tmp_path / 'book'
    write(book / '01.md', '# A\n')
    write(tmp_path / 'build' / 'mdbindery.yaml', 'source_dir: ../book\nmetadata:\n  title: T\n')
    cfg = config.load(tmp_path / 'build' / 'mdbindery.yaml')
    assert cfg.source == book.resolve() and cfg.base == (tmp_path / 'build').resolve()


def test_bad_values_raise(tmp_path):
    write(tmp_path / '01.md', '# A\n')
    write(tmp_path / 'mdbindery.yaml', 'options:\n  citations: footnotes\n')
    with pytest.raises(config.ConfigError):
        config.load(tmp_path)


def test_identifier_is_saved(tmp_path):
    write(tmp_path / '01.md', '# A\n')
    write(tmp_path / 'mdbindery.yaml', 'metadata:\n  title: T\n  identifier:\n')
    cfg = config.load(tmp_path)
    assert config.save_identifier(cfg, 'urn:uuid:1234')
    assert 'identifier: urn:uuid:1234' in (tmp_path / 'mdbindery.yaml').read_text()


def test_starter_yaml_keeps_existing_values(tmp_path):
    write(tmp_path / '01-a.md', '# A\n')
    write(tmp_path / 'mdbindery.yaml', 'metadata:\n  title: T\n  authors: [Jane]\n  subtitle: S\n'
          '  identifier: urn:uuid:keep-me\noptions:\n  toc_depth: 3\n  drop_lines: ["^x"]\n')
    text = config.starter_yaml(config.load(tmp_path))
    write(tmp_path / 'mdbindery.yaml', text)
    again = config.load(tmp_path)
    assert again.meta['identifier'] == 'urn:uuid:keep-me' and again.meta['authors'] == ['Jane']
    assert again.meta['subtitle'] == 'S' and again.opts['toc_depth'] == 3 and again.opts['drop_lines'] == ['^x']


def test_starter_yaml_round_trips(tmp_path):
    write(tmp_path / 'README.md', '# Book: a subtitle\n')
    write(tmp_path / '01-a.md', '# A\n')
    cfg = config.load(tmp_path)
    write(tmp_path / 'mdbindery.yaml', config.starter_yaml(cfg))
    again = config.load(tmp_path)
    assert again.meta['title'] == 'Book: a subtitle'
    assert [f['file'] for f in again['files']] == ['README.md', '01-a.md']
    assert not again.warnings
