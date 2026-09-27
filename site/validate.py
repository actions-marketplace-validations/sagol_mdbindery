#!/usr/bin/env python3
"""Check published examples and local references against the checked-out CLI."""
import contextlib
import io
import json
import re
import shlex
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

SITE = Path(__file__).resolve().parent
ROOT = SITE.parent
sys.path.insert(0, str(ROOT / 'src'))

import yaml
from mdbindery import __version__, config
from mdbindery.cli import parser
from stage import PUBLIC_FILES


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids, self.references, self.targets = [], [], []
        self.blocks, self.json_ld, self.codes = [], [], set()
        self.pre, self.script = None, None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ids.append(attrs['id'])
        for key in ('href', 'src'):
            if attrs.get(key):
                self.references.append(attrs[key])
        for key in ('aria-controls', 'aria-labelledby', 'data-copy-target'):
            self.targets.extend(attrs.get(key, '').split())
        if tag == 'pre':
            self.pre = []
        if tag == 'script' and attrs.get('type') == 'application/ld+json':
            self.script = []

    def handle_endtag(self, tag):
        if tag == 'pre' and self.pre is not None:
            self.blocks.append(''.join(self.pre))
            self.pre = None
        if tag == 'script' and self.script is not None:
            self.json_ld.append(''.join(self.script))
            self.script = None

    def handle_data(self, text):
        if self.pre is not None:
            self.pre.append(text)
        if self.script is not None:
            self.script.append(text)
        if re.fullmatch(r'MB\d{3}', text.strip()):
            self.codes.add(text.strip())


def main():
    errors = []
    commands = examples = 0

    def require(condition, message):
        if not condition:
            errors.append(message)

    for name in PUBLIC_FILES:
        p = SITE / name
        require(p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(SITE),
                f'public asset missing or outside site/: {name}')
    page = Page()
    page.feed((SITE / 'index.html').read_text(encoding='utf-8'))
    require(not [k for k, n in Counter(page.ids).items() if n > 1], 'duplicate HTML IDs')
    require(bool(page.json_ld), 'missing JSON-LD')
    for text in page.json_ld:
        data = json.loads(text)
        for node in data.get('@graph', []):
            if node.get('@type') == 'SoftwareApplication':
                require(node.get('softwareVersion') == __version__, 'JSON-LD version differs from package')
    for target in page.targets:
        require(target in page.ids, f'ARIA/copy target missing: {target}')

    def local_reference(reference):
        url = urlsplit(reference)
        if url.scheme or url.netloc:
            return
        name = unquote(url.path).lstrip('/') or 'index.html'
        if name in ('.', './'):
            name = 'index.html'
        require(name in PUBLIC_FILES, f'link target not in published assets: {reference}')
        if name == 'index.html' and url.fragment:
            require(unquote(url.fragment) in page.ids, f'broken fragment: {reference}')

    for reference in page.references:
        local_reference(reference)
    for name in ('agents.json', '.well-known/agent.json', 'site.webmanifest'):
        data = json.loads((SITE / name).read_text(encoding='utf-8'))
        if 'version' in data:
            require(data['version'] == __version__, f'{name}: version differs from package')
        for icon in data.get('icons', []):
            local_reference(icon['src'])
    ET.parse(SITE / 'sitemap.xml')
    for reference in re.findall(r'url\(\s*[\'"]?([^\s\)\'"]+)', (SITE / 'styles.css').read_text()):
        local_reference(reference)

    source = '\n'.join(p.read_text(encoding='utf-8') for p in (ROOT / 'src/mdbindery').glob('*.py'))
    source_codes = set(re.findall(r'[\'"](MB\d{3})[\'"]', source))
    require(page.codes == source_codes,
            f'HTML diagnostic codes differ: missing {sorted(source_codes - page.codes)}, extra {sorted(page.codes - source_codes)}')

    blocks = [('index.html', block) for block in page.blocks]
    for name in ('llms.txt', 'llms-full.txt'):
        text = (SITE / name).read_text(encoding='utf-8')
        blocks.extend((name, block) for block in re.findall(r'^```[^\n]*\n(.*?)^```[ \t]*$', text, re.S | re.M))
        prose = re.sub(r'^```[^\n]*\n.*?^```[ \t]*$', '', text, flags=re.S | re.M)
        prose = re.sub(r'`+[^`]*`+', '', prose)
        for reference in re.findall(r'\]\(([^)]+)\)', prose):
            local_reference(reference)
        if name == 'llms-full.txt':
            codes = set(re.findall(r'^\| `(MB\d{3})`', text, re.M))
            require(codes == source_codes, 'LLM diagnostic table differs from source codes')

    cli = parser()
    for name, block in blocks:
        if re.match(r'^(?:slug|source_dir|metadata|options|files):', block):
            examples += 1
            try:
                data = yaml.safe_load(block)
                require(isinstance(data, dict), f'{name}: config example must be a mapping')
                if not isinstance(data, dict):
                    continue
                unknown = config.unknown_keys(data, config.DEFAULTS)
                require(not unknown, f'{name}: unknown config keys: {unknown}')
                config.validate(config.deep_merge(config.DEFAULTS, data))
                for entry in data.get('files', []):
                    if isinstance(entry, dict):
                        require(not set(entry) - config.FILE_KEYS,
                                f'{name}: unsupported file keys: {sorted(set(entry) - config.FILE_KEYS)}')
                    else:
                        require(isinstance(entry, str), f'{name}: invalid file entry')
            except (ValueError, TypeError, config.ConfigError, yaml.YAMLError) as exc:
                errors.append(f'{name}: invalid config example: {exc}')
        for line in block.splitlines():
            line = re.sub(r'^\s*(?:\$\s*|- run:\s*)', '', line).strip()
            # Separate shell command segments; never execute documentation.
            lexer = shlex.shlex(line, posix=True, punctuation_chars=';&|')
            lexer.whitespace_split = True
            try:
                tokens = list(lexer)
            except ValueError:
                if line.startswith('mdbindery '):
                    errors.append(f'{name}: malformed shell quoting: {line}')
                continue
            segments, segment = [], []
            for token in tokens + [';']:
                if token and all(c in ';&|' for c in token):
                    segments.append(segment)
                    segment = []
                else:
                    segment.append(token)
            for args in segments:
                if not args or args[0] != 'mdbindery':
                    continue
                commands += 1
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    try:
                        cli.parse_args(args[1:])
                    except SystemExit as exc:
                        require(exc.code == 0, f'{name}: invalid CLI example: {line}')
    require(examples >= 2, 'expected configuration examples in HTML and LLM reference')
    require(commands > 0, 'no runnable CLI examples found')
    if errors:
        for error in errors:
            print(f'error: {error}', file=sys.stderr)
        return 1
    print(f'Site valid: {examples} configuration examples, {commands} CLI commands, '
          f'{len(source_codes)} diagnostic codes, JSON/JSON-LD and local references.')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, ET.ParseError) as exc:
        sys.exit(f'site validation failed: {exc}')
