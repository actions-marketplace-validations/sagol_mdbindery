import os
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'src'))

from mdbindery import tools  # noqa: E402

FIXTURES = ROOT / 'tests' / 'fixtures'
EXAMPLES = ROOT / 'examples'

# MDBINDERY_REQUIRE_TOOLS=1 (CI) turns these skips into failures
_require = bool(os.environ.get('MDBINDERY_REQUIRE_TOOLS'))
needs_pandoc = pytest.mark.skipif(not _require and not tools.find('pandoc'),
                                  reason='pandoc not installed (mdbindery install-tools)')
needs_epubcheck = pytest.mark.skipif(not _require and not tools.epubcheck_cmd(), reason='EPUBCheck not installed')
HAVE_EPUBCHECK = _require or bool(tools.epubcheck_cmd())
HAVE_MMDC = _require or bool(tools.command('mmdc'))


def validate_if_installed(cfg):
    """Content tests also run EPUBCheck when it is installed (always in CI); without it they check content only."""
    if not HAVE_EPUBCHECK:
        cfg.opts['epubcheck'] = False
    return cfg


@pytest.fixture
def copy_book(tmp_path):
    """Copy a fixture or example book into tmp_path so builds never write into the repo."""
    def _copy(src):
        dst = tmp_path / Path(src).name
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns('dist'))
        return dst
    return _copy
