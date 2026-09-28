"""Fetch contracts, checkout boundaries, and failure cleanup."""
import importlib
import io
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

from mdbindery import tools

fetch_mod = importlib.import_module('mdbindery.check')


def test_local_fetch_has_complete_result_and_keeps_book(tmp_path):
    book = tmp_path / 'book'
    book.mkdir()
    (book / 'chapter.md').write_text('# Chapter\n\nText.\n', encoding='utf-8')
    local, cleanup, github, root, removed = fetch_mod.fetch(str(book))
    assert (local, cleanup, github, root, removed) == (book.resolve(), None, None, None, [])
    fetch_mod.check(str(book), render=False, log=lambda *_: None)
    assert (book / 'chapter.md').is_file()


def test_git_fetch_has_complete_result(tmp_path, monkeypatch):
    git = shutil.which('git')
    if not git:
        pytest.skip('git not installed')
    checkout = tmp_path / 'checkout'
    checkout.mkdir()
    monkeypatch.setattr(fetch_mod.tempfile, 'mkdtemp', lambda **k: str(checkout))
    source = tmp_path / 'source'
    source.mkdir()
    subprocess.run([git, 'init', str(source)], check=True, capture_output=True)
    (source / 'chapter.md').write_text('# Chapter\n\nText.\n', encoding='utf-8')
    subprocess.run([git, '-C', str(source), 'add', '.'], check=True, capture_output=True)
    subprocess.run([git, '-C', str(source), '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                    'commit', '-m', 'Fixture'], check=True, capture_output=True)
    local, cleanup, github, root, removed = fetch_mod.fetch(source.as_uri(), log=lambda *_: None)
    try:
        assert local == root and root.is_relative_to(cleanup.resolve())
        assert github is None and removed == []
        assert (local / 'chapter.md').read_text(encoding='utf-8') == '# Chapter\n\nText.\n'
    finally:
        shutil.rmtree(cleanup, ignore_errors=True)  # pytest also cleans read-only Git files on Windows
    assert (source / 'chapter.md').is_file()


def test_archive_fetch_keeps_subfolder_inside_repository(tmp_path, monkeypatch):
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w') as z:
        z.writestr('repo-main/docs/chapter.md', '# Chapter\n')
    monkeypatch.setattr(shutil, 'which', lambda _: None)
    monkeypatch.setattr(fetch_mod.urllib.request, 'urlopen', lambda *a, **k: io.BytesIO(archive.getvalue()))
    local, cleanup, github, root, removed = fetch_mod.fetch('https://github.com/o/r/tree/main/docs', log=lambda *_: None)
    try:
        assert local == root / 'docs' and root.is_relative_to(cleanup.resolve())
        assert github == {'owner': 'o', 'repo': 'r', 'branch': 'main', 'subdir': 'docs'}
        assert removed == [] and (local / 'chapter.md').is_file()
    finally:
        shutil.rmtree(cleanup)


@pytest.mark.parametrize('failure', ['timeout', 'interrupt'])
def test_failed_clone_cleans_checkout(tmp_path, monkeypatch, failure):
    checkout = tmp_path / 'checkout'
    checkout.mkdir()
    monkeypatch.setattr(fetch_mod.tempfile, 'mkdtemp', lambda **k: str(checkout))
    monkeypatch.setattr(shutil, 'which', lambda _: 'git')

    def run(cmd, **kwargs):
        assert kwargs['timeout'] > 0 and kwargs['tail'] == 65536
        dest = Path(cmd[-1])
        dest.mkdir()
        (dest / 'partial').write_text('partial', encoding='utf-8')
        if failure == 'interrupt':
            raise KeyboardInterrupt
        return tools.Completed(-9, '', 'clone stopped', True)

    monkeypatch.setattr(tools, 'run_process', run)
    error = KeyboardInterrupt if failure == 'interrupt' else RuntimeError
    with pytest.raises(error, match=None if failure == 'interrupt' else 'git clone timed out'):
        fetch_mod.fetch('https://example.invalid/book.git', log=lambda *_: None)
    assert not checkout.exists()


@pytest.mark.parametrize('fail', [False, True])
def test_remote_check_preserves_boundary_and_always_cleans_up(tmp_path, monkeypatch, fail):
    checkout = tmp_path / 'checkout'
    book = checkout / 'docs'
    book.mkdir(parents=True)
    monkeypatch.setattr(fetch_mod, 'fetch', lambda *a: (book, checkout, None, checkout, ['leak.md']))

    def inspect(local, config_path, report, github, do_build, render, log, remote=False, repo_root=None):
        assert local == book and remote and repo_root == checkout
        assert [(f['code'], f['file']) for f in report.findings] == [('MB407', 'leak.md')]
        if fail:
            raise RuntimeError('check failed')
        return report

    monkeypatch.setattr(fetch_mod, '_check', inspect)
    if fail:
        with pytest.raises(RuntimeError, match='check failed'):
            fetch_mod.check('https://example.invalid/book.git', log=lambda *_: None)
    else:
        assert fetch_mod.check('https://example.invalid/book.git', log=lambda *_: None).ok
    assert not checkout.exists()
