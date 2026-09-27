#!/usr/bin/env python3
"""Copy the public site files into a new, empty deployment directory."""
import shutil
import sys
from pathlib import Path

SITE = Path(__file__).resolve().parent
PUBLIC_FILES = (
    'index.html', 'styles.css', 'app.js', 'llms.txt', 'llms-full.txt',
    'agents.json', 'robots.txt', 'sitemap.xml', 'site.webmanifest',
    'favicon.svg', 'og-image.svg', 'og-image.png', '.nojekyll',
    '.well-known/agent.json',
)


def stage(destination):
    destination = Path(destination).resolve()
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise ValueError(f'destination must be an empty directory: {destination}')
    for name in PUBLIC_FILES:
        source = SITE / name
        if not source.is_file() or source.is_symlink() or not source.resolve().is_relative_to(SITE):
            raise ValueError(f'public asset must be a regular file inside site/: {name}')
    destination.mkdir(parents=True, exist_ok=True)
    for name in PUBLIC_FILES:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SITE / name, target)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit('usage: python3 site/stage.py DESTINATION')
    try:
        stage(sys.argv[1])
    except (OSError, ValueError) as exc:
        sys.exit(str(exc))
    print(f'Staged {len(PUBLIC_FILES)} public files.')
