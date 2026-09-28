"""Doctor must distinguish a working tool from a failed version probe."""
import subprocess

import pytest

from mdbindery import cli, installer, tools


@pytest.mark.parametrize('name', ['pandoc', 'epubcheck', 'node', 'ace'])
@pytest.mark.parametrize('failure', ['exit', 'timeout', 'launch', 'empty'])
def test_doctor_reports_failed_version_probes(name, failure, monkeypatch, capsys):
    versions = {'pandoc': 'pandoc 3.8', 'epubcheck': 'EPUBCheck v5.3.0',
                'node': 'v22.0.0', 'ace': '1.3.6'}
    monkeypatch.setattr(tools, 'find', lambda n: n if n in ('pandoc', 'node') else None)
    monkeypatch.setattr(tools, 'old_pandoc_on_path', lambda: None)
    monkeypatch.setattr(tools, 'epubcheck_cmd', lambda: ['epubcheck'])
    monkeypatch.setattr(tools, 'command', lambda n: ['ace'] if n == 'ace' else None)
    monkeypatch.setattr(tools, 'ace_env', lambda: {})
    monkeypatch.setattr(installer, 'mermaid_ok', lambda: None)

    def run(cmd, **kwargs):
        tool = cmd[0]
        if tool == name:
            if failure == 'launch':
                raise OSError('cannot start tool')
            if failure == 'empty':
                return tools.Completed(0, '', '', False)
            return tools.Completed(-9 if failure == 'timeout' else 1,
                                   versions[tool], 'probe failed', failure == 'timeout')
        # EPUBCheck may print its version on stderr.
        return tools.Completed(0, '' if tool == 'epubcheck' else versions[tool],
                               versions[tool] if tool == 'epubcheck' else '', False)

    monkeypatch.setattr(tools, 'run_process', run)
    status = installer.self_test()
    assert status[name] is None
    assert name in status['notes']
    for tool in versions.keys() - {name}:
        assert status[tool] == versions[tool]
    assert cli.main(['doctor']) == (1 if name in ('pandoc', 'epubcheck') else 0)
    assert 'internal error' not in capsys.readouterr().err


@pytest.mark.parametrize('name, output', [('pandoc', 'pandoc 3.8'), ('java', 'openjdk version "21.0.1"')])
@pytest.mark.parametrize('code', [0, 1])
def test_version_detection_requires_success(name, output, code, monkeypatch):
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: subprocess.CompletedProcess(
        a[0], code, output if name == 'pandoc' else '', output if name == 'java' else ''))
    tools.clear_cache()
    try:
        result = tools.pandoc_version('pandoc') if name == 'pandoc' else tools.java_version('java')
        expected = ((3, 8) if name == 'pandoc' else 21) if code == 0 else None
        assert result == expected
    finally:
        tools.clear_cache()


def test_doctor_reports_mermaid_launch_failure(monkeypatch):
    monkeypatch.setattr(tools, 'find', lambda n: 'pandoc' if n == 'pandoc' else None)
    monkeypatch.setattr(tools, 'old_pandoc_on_path', lambda: None)
    monkeypatch.setattr(tools, 'epubcheck_cmd', lambda: ['epubcheck'])
    monkeypatch.setattr(tools, 'command', lambda n: None)
    monkeypatch.setattr(tools, 'run_process', lambda cmd, **k: tools.Completed(
        0, 'pandoc 3.8' if cmd[0] == 'pandoc' else 'EPUBCheck v5.3.0', '', False))

    def broken_mermaid():
        raise OSError('node cannot start')

    monkeypatch.setattr(installer, 'mermaid_ok', broken_mermaid)
    assert 'cannot render' in installer.self_test()['mermaid']
    assert cli.main(['doctor']) == 0  # optional renderer cannot hide working required tools
