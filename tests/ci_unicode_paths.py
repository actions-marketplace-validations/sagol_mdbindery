"""CI check: build the sample book from a folder, and with a temp folder, whose names have
non-ASCII letters and spaces (Windows code pages, UNC-style path handling)."""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
base = Path(tempfile.mkdtemp(prefix='mdbindery-ci-'))
book = base / 'Книга с пробелами' / 'sample book'
tmp = base / 'врем папка'
shutil.copytree(ROOT / 'examples' / 'sample-book', book, ignore=shutil.ignore_patterns('dist'))
tmp.mkdir()
env = dict(os.environ, TMPDIR=str(tmp), TEMP=str(tmp), TMP=str(tmp))
r = subprocess.run(['mdbindery', 'build', str(book), '--no-ace'], env=env)
print('exit', r.returncode)
sys.exit(r.returncode)
