"""install.sh option handling, with a stand-in uv that records what it was asked to install: no network, no real install."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / 'install/install.sh'

FAKE_UV = """#!/bin/sh
printf '%s\\n' "$@" > "$UV_ARGS"
mkdir -p "$UV_TOOL_BIN_DIR"
printf '#!/bin/sh\\nexit 0\\n' > "$UV_TOOL_BIN_DIR/mdbindery"
chmod +x "$UV_TOOL_BIN_DIR/mdbindery"
"""


def run(tmp_path, *args):
    fake = tmp_path / 'fakebin'
    fake.mkdir(exist_ok=True)
    (fake / 'uv').write_text(FAKE_UV)
    (fake / 'uv').chmod(0o755)
    env = {'PATH': f'{fake}{os.pathsep}{os.environ["PATH"]}', 'HOME': str(tmp_path / 'home'), 'UV_ARGS': str(tmp_path / 'uv-args'),
           'MDBINDERY_HOME': str(tmp_path / 'tool home'), 'MDBINDERY_BIN': str(tmp_path / 'bin')}
    return subprocess.run(['bash', str(INSTALLER), *args], capture_output=True, text=True, env=env, timeout=60)


@pytest.mark.parametrize('name, encoded', [
    ('src dir', 'src%20dir'), ('source%20draft', 'source%2520draft'), ('mdb#copy', 'mdb%23copy'), ('a?b', 'a%3Fb'),
    ('книга', '%D0%BA%D0%BD%D0%B8%D0%B3%D0%B0')])
def test_local_source_becomes_a_fully_encoded_file_url(tmp_path, name, encoded):
    source = tmp_path / name
    source.mkdir()
    shutil.copy(ROOT / 'pyproject.toml', source / 'pyproject.toml')
    result = run(tmp_path, '--local', str(source), '--extras', 'pdf', '--no-tools')
    assert result.returncode == 0, result.stderr
    spec = (tmp_path / 'uv-args').read_text().splitlines()[-1]
    assert spec == f'mdbindery[pdf] @ file://{str(tmp_path).replace(" ", "%20")}/{encoded}'


def test_without_extras_the_plain_name_is_installed(tmp_path):
    shutil.copy(ROOT / 'pyproject.toml', tmp_path / 'pyproject.toml')
    assert run(tmp_path, '--local', str(tmp_path), '--no-tools').returncode == 0
    assert (tmp_path / 'uv-args').read_text().splitlines()[-1].startswith('mdbindery @ file://')


@pytest.mark.parametrize('value', ['PDF', 'pdf,', ',pdf', 'pdf extra', '../x'])
def test_malformed_extras_stop_before_anything_changes(tmp_path, value):
    result = run(tmp_path, '--extras', value, '--no-tools')
    assert result.returncode == 2
    assert 'names separated by commas' in result.stderr
    assert not (tmp_path / 'tool home').exists()


def test_extras_needs_a_value(tmp_path):
    result = run(tmp_path, '--extras')
    assert result.returncode == 2 and 'needs a value' in result.stderr
