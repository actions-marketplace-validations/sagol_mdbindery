"""Download and install mdbindery's external tools into the tool home.

Everything is user-space, pinned, and checksum-verified: pandoc, EPUBCheck,
a Java runtime (only if no Java 11+ is present), Node.js, mermaid-cli, and
DAISY Ace with Puppeteer's headless Chrome.
"""
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tarfile
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

from . import tools

PANDOC_VERSION = '3.11'
PANDOC = {  # (os, arch) -> (asset, sha256)
    ('linux', 'x64'): ('pandoc-3.11-linux-amd64.tar.gz', '37edb3bbcf722f921a009941bf5874e2e0c09263226c9b4a2d980788cb062ab6'),
    ('linux', 'arm64'): ('pandoc-3.11-linux-arm64.tar.gz', '56ed5566ec41d22ec9ee0704e6ac0b98ba102e92384efd5306173a22d314c79a'),
    ('mac', 'arm64'): ('pandoc-3.11-arm64-macOS.zip', '15806bedf9517bfead72e88fe6a6696635c3691efbb6e152173440e9c5bb50b4'),
    ('mac', 'x64'): ('pandoc-3.11-x86_64-macOS.zip', '3b1c1b57f160112c821d02f23d946ede8b7f57a6ccf4632a25a512d334a9291f'),
    ('win', 'x64'): ('pandoc-3.11-windows-x86_64.zip', '2ab72baf2399450e148ddf7a2a8689806c42e1bba71862b57e220fd9b8456d3d'),
    ('win', 'arm64'): ('pandoc-3.11-windows-x86_64.zip', '2ab72baf2399450e148ddf7a2a8689806c42e1bba71862b57e220fd9b8456d3d'),
}
EPUBCHECK_VERSION = '5.4.0'
EPUBCHECK_SHA = '33350c61038e71dfb3d45a76aed04bf5481e6d5500cb780f6e98db8bbd15a28c'
NODE_VERSION = '24.21.0'
NODE = {
    ('linux', 'x64'): ('node-v24.21.0-linux-x64.tar.xz', 'fd8e59d5a511510f6a298afb548f18c7d2b1be404d8b4a27d94fbe49f56cb2d6'),
    ('linux', 'arm64'): ('node-v24.21.0-linux-arm64.tar.xz', '6ad1325edbdb5649c379b75a237147a666c95d4f9ae8d340fef2d1575d289ad2'),
    ('mac', 'arm64'): ('node-v24.21.0-darwin-arm64.tar.gz', 'bed7eea5325e1108f32ce5228ddd6a5f0f08a499ee42aa7442aea583702f6057'),
    ('mac', 'x64'): ('node-v24.21.0-darwin-x64.tar.gz', '1462cb3b3046b815cf8ea436d3da450ec1a9f11dac7e5a46b0ada5305d7e8097'),
    ('win', 'x64'): ('node-v24.21.0-win-x64.zip', '158f7685b44de51f6c0df1d153526cbcd3e1bc739a8dfc607721cef75de9e541'),
    ('win', 'arm64'): ('node-v24.21.0-win-arm64.zip', '8779b1bde1d39f8d420e3b57aa657b39891af434d3de44a919044cec06785921'),
}
NPM_PACKAGES = ['@mermaid-js/mermaid-cli@12.0.0', '@daisy/ace@1.4.6']
JRE_MAJOR = 21


def _os():
    return 'win' if tools.IS_WIN else ('mac' if tools.IS_MAC else 'linux')


def say(msg):
    print(msg, flush=True)


def download(url, dest, sha256=None):
    req = urllib.request.Request(url, headers={'User-Agent': 'mdbindery-installer'})
    h = hashlib.sha256()
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, 'wb') as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            h.update(chunk)
            f.write(chunk)
    if sha256 and h.hexdigest() != sha256.lower():
        raise RuntimeError(f'checksum mismatch for {url}\n  expected {sha256}\n  got      {h.hexdigest()}')


def _inside(path, root):
    try:
        Path(os.path.realpath(path)).relative_to(os.path.realpath(root))
        return True
    except ValueError:
        return False


def extract(archive, dest):
    """Unpack a zip or tar archive into dest; members may not leave dest (names or links)."""
    dest.mkdir(parents=True, exist_ok=True)
    root = Path(os.path.realpath(dest))
    if archive.name.endswith('.zip'):
        with zipfile.ZipFile(archive) as z:
            dirs = []
            for info in z.infolist():
                if not _inside(root / info.filename, root):
                    raise RuntimeError(f'unsafe path in archive: {info.filename}')
                target = Path(z.extract(info, root))
                mode = (info.external_attr >> 16) & 0o777
                if mode and not tools.IS_WIN:
                    if target.is_dir():
                        dirs.append((target, mode))  # applied last: a read-only folder would block its files
                    else:
                        os.chmod(target, mode)
            for d, mode in reversed(dirs):
                os.chmod(d, mode | stat.S_IWUSR)
    else:
        with tarfile.open(archive) as t:
            members = t.getmembers()
            for m in members:
                if not _inside(root / m.name, root):
                    raise RuntimeError(f'unsafe path in archive: {m.name}')
                if m.issym() or m.islnk():
                    link = m.linkname if m.islnk() else os.path.join(os.path.dirname(m.name), m.linkname)
                    if os.path.isabs(m.linkname) or not _inside(root / link, root):
                        raise RuntimeError(f'unsafe link in archive: {m.name} -> {m.linkname}')
                if not (m.isfile() or m.isdir() or m.issym() or m.islnk()):
                    raise RuntimeError(f'unsupported member in archive: {m.name}')
            if hasattr(tarfile, 'data_filter'):
                t.extractall(root, filter='data')
            else:
                t.extractall(root)


def _staging(target):
    """A fresh staging folder next to target (same file system, so the final switch is a rename)."""
    staged = target.with_name(f'.staging-{target.name}')
    if staged.exists():
        shutil.rmtree(staged)
    return staged


def _swap_in(staged, target, check=None):
    """Replace target with a staged folder; the old one stays until the new one passes check(target)."""
    old = target.with_name(f'.old-{target.name}')
    if old.exists():
        shutil.rmtree(old)
    if target.exists():
        target.rename(old)
    try:
        staged.rename(target)
        if check:
            check(target)
    except BaseException:
        if old.exists():
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
            old.rename(target)
        raise
    shutil.rmtree(old, ignore_errors=True)


def _place(found_binary, target, version, smoke=None, check=None, bin_style=True):
    """Install the folder holding a binary (or its parent if it sits in bin/) as target, transactionally.

    smoke: arguments the installed binary must start with (for example ('--version',)) before the switch
    is final; its path inside target is taken from where it was found, whatever the archive's layout.
    """
    p = Path(found_binary)
    root = p.parent.parent if (bin_style and p.parent.name == 'bin') else p.parent
    rel = p.relative_to(root)
    staged = _staging(target)
    shutil.move(str(root), str(staged))
    _marker(staged, version)  # the marker always describes the folder it sits in
    if smoke is not None:
        check = _runs(rel, *smoke)
    _swap_in(staged, target, check)


def _runs(*args):
    """A check that the installed program starts: args[0] is relative to the installed folder."""
    def check(folder):
        exe = folder / args[0]
        r = tools.run_process([exe, *args[1:]], timeout=120, tail=4096)
        if r.returncode != 0:
            raise RuntimeError(f'{exe} does not run after installation: {(r.stderr or r.stdout).strip()[-300:]}')
    return check


def _make_executable(path):
    if not tools.IS_WIN and path.exists():
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _marker(dirpath, version):
    (dirpath / '.mdbindery-version').write_text(version)


def _installed(dirpath, version):
    m = dirpath / '.mdbindery-version'
    return m.exists() and m.read_text().strip() == version


def install_pandoc(tmp, force=False):
    target = tools.tools_dir() / 'pandoc'
    if _installed(target, PANDOC_VERSION) and not force:
        say(f'pandoc {PANDOC_VERSION}: already installed')
        return
    key = (_os(), tools.arch())
    if key not in PANDOC:
        raise RuntimeError(f'no pandoc build for {key}; install pandoc {PANDOC_VERSION} yourself and put it on PATH')
    asset, sha = PANDOC[key]
    say(f'pandoc {PANDOC_VERSION}: downloading {asset}')
    arc = tmp / asset
    download(f'https://github.com/jgm/pandoc/releases/download/{PANDOC_VERSION}/{asset}', arc, sha)
    ex = tmp / 'pandoc-x'
    extract(arc, ex)
    if tools.IS_WIN:
        exe = next(p for p in ex.rglob('pandoc.exe') if p.is_file())
    else:
        exe = next(p for p in ex.rglob('pandoc') if p.is_file() and p.parent.name == 'bin')
    _make_executable(exe)
    _place(exe, target, PANDOC_VERSION, smoke=('--version',))


def install_epubcheck(tmp, force=False):
    target = tools.tools_dir() / 'epubcheck'
    if _installed(target, EPUBCHECK_VERSION) and not force:
        say(f'EPUBCheck {EPUBCHECK_VERSION}: already installed')
        return
    say(f'EPUBCheck {EPUBCHECK_VERSION}: downloading')
    arc = tmp / 'epubcheck.zip'
    download(f'https://github.com/w3c/epubcheck/releases/download/v{EPUBCHECK_VERSION}/epubcheck-{EPUBCHECK_VERSION}.zip',
             arc, EPUBCHECK_SHA)
    staged = _staging(target)
    extract(arc, staged)
    _marker(staged, EPUBCHECK_VERSION)

    def has_jar(folder):
        if not any(folder.glob('**/epubcheck.jar')):
            raise RuntimeError('epubcheck.jar missing from the EPUBCheck download')
    _swap_in(staged, target, has_jar)


def install_jre(tmp, mode='auto', force=False):
    target = tools.tools_dir() / 'jre'
    java = tools.find('java')
    if mode == 'never':
        return
    if mode == 'auto' and java and (tools.java_version(java) or 0) >= 11 and not (force and target.exists()):
        say(f'Java: using {java} (version {tools.java_version(java)})')
        return
    if _installed(target, str(JRE_MAJOR)) and not force:
        say('Java runtime: already installed')
        return
    osname = {'linux': 'linux', 'mac': 'mac', 'win': 'windows'}[_os()]
    a = {'x64': 'x64', 'arm64': 'aarch64'}.get(tools.arch(), tools.arch())
    api = (f'https://api.adoptium.net/v3/assets/latest/{JRE_MAJOR}/hotspot'
           f'?architecture={a}&image_type=jre&os={osname}&vendor=eclipse')
    req = urllib.request.Request(api, headers={'User-Agent': 'mdbindery-installer'})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.load(r)
    pkg = next(x['binary']['package'] for x in data if x['binary']['package']['name'].endswith(('.tar.gz', '.zip')))
    say(f"Java runtime: downloading {pkg['name']} (Eclipse Temurin)")
    arc = tmp / pkg['name']
    download(pkg['link'], arc, pkg['checksum'])
    ex = tmp / 'jre-x'
    extract(arc, ex)
    exe = next(p for p in ex.rglob('java.exe' if tools.IS_WIN else 'java') if p.is_file() and p.parent.name == 'bin')
    _make_executable(exe)
    _place(exe, target, str(JRE_MAJOR), smoke=('-version',))


def install_node(tmp, force=False):
    target = tools.tools_dir() / 'node'
    if _installed(target, NODE_VERSION) and not force:
        say(f'Node.js {NODE_VERSION}: already installed')
        return
    key = (_os(), tools.arch())
    if key not in NODE:
        raise RuntimeError(f'no Node.js build for {key}')
    asset, sha = NODE[key]
    say(f'Node.js {NODE_VERSION}: downloading {asset}')
    arc = tmp / asset
    download(f'https://nodejs.org/dist/v{NODE_VERSION}/{asset}', arc, sha)
    ex = tmp / 'node-x'
    extract(arc, ex)
    if tools.IS_WIN:
        exe = next(p for p in ex.rglob('node.exe') if p.is_file())
    else:
        exe = next(p for p in ex.rglob('node') if p.is_file() and p.parent.name == 'bin')
    _place(exe, target, NODE_VERSION, smoke=('--version',), bin_style=not tools.IS_WIN)
    tools.clear_cache()


def _run(cmd, env, timeout=1800):
    r = tools.run_process(cmd, env=env, timeout=tools.deadline(timeout), tail=65536)
    if r.timed_out:
        raise RuntimeError(f"command did not finish within {tools.deadline(timeout):.0f} s: {' '.join(map(str, cmd))}")
    if r.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(map(str, cmd))}\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}")
    return r


def install_npm_packages(force=False):
    prefix = tools.npm_prefix()
    marker = prefix / '.mdbindery-version'
    want = ' '.join(NPM_PACKAGES)
    cache = tools.tools_dir() / 'npm-cache'
    env = tools.tool_env()
    env['npm_config_cache'] = str(cache)          # inside the tool home: removed on uninstall
    env['npm_config_update_notifier'] = 'false'
    if marker.exists() and marker.read_text().strip() == want and not force:
        say('mermaid-cli and Ace: already installed')
    else:
        npm = tools.command('npm')
        if not npm:
            raise RuntimeError('npm not found after installing Node.js')
        env['PUPPETEER_SKIP_DOWNLOAD'] = '1'       # browsers are installed explicitly below
        env['ELECTRON_SKIP_BINARY_DOWNLOAD'] = '1'  # Ace's Electron runner is not used
        say(f'npm: installing {want}')
        staged = _staging(prefix)  # the working copy stays until the new one is complete
        staged.mkdir(parents=True)
        _run(npm + ['install', '-g', '--prefix', str(staged), '--no-fund', '--no-audit', *NPM_PACKAGES], env)
        (staged / '.mdbindery-version').write_text(want)

        def has_packages(folder):
            mods = folder / ('node_modules' if tools.IS_WIN else 'lib/node_modules')
            for pkg in ('@mermaid-js/mermaid-cli', '@daisy/ace'):
                if not (mods / pkg / 'package.json').is_file():
                    raise RuntimeError(f'npm did not install {pkg}')
        _swap_in(staged, prefix, has_packages)
        tools.clear_cache()
    # every Puppeteer copy fetches the headless Chrome build it expects
    node = tools.find('node')
    for pkg in sorted(tools.npm_modules_dir().rglob('node_modules/puppeteer/package.json')):
        meta = json.loads(pkg.read_text())
        bin_rel = meta.get('bin', {}).get('puppeteer') if isinstance(meta.get('bin'), dict) else meta.get('bin')
        if not bin_rel:
            continue
        say(f"Puppeteer {meta.get('version')}: installing headless Chrome")
        _run([node, str(pkg.parent / bin_rel), 'browsers', 'install', 'chrome-headless-shell'], env, timeout=1200)
    shutil.rmtree(cache, ignore_errors=True)


def self_test():
    """Tool status: a dict of name -> version string or None, plus 'notes'."""
    status, notes = {}, {}

    def version(name, cmd, timeout=60, env=None):
        if not cmd:
            return None
        try:
            r = tools.run_process(cmd, env=env, timeout=timeout, tail=65536)
        except OSError as e:
            detail = str(e)
        else:
            output = (r.stdout + r.stderr).strip()
            if r.returncode == 0 and output:
                return output
            detail = (r.stderr or r.stdout).strip() or f'exit {r.returncode}; no version output'
        notes[name] = 'installed but does not run: ' + detail.split('\n')[0][:200]
        return None

    p = tools.find('pandoc')
    output = version('pandoc', [p, '--version'] if p else None)
    status['pandoc'] = output.split('\n')[0] if output else None
    old = tools.old_pandoc_on_path()
    if old and not p:
        notes['pandoc'] = f'{old} on PATH is older than 3.8 and is not used'
    ec = tools.epubcheck_cmd()
    status['epubcheck'] = None
    if ec:
        output = version('epubcheck', ec + ['--version'], timeout=120)
        m = re.search(r'EPUBCheck v[\d.]+', output or '')
        if m:
            status['epubcheck'] = m.group(0)
        elif output:
            notes['epubcheck'] = 'unrecognized version output: ' + output.split('\n')[0][:200]
    elif tools.epubcheck_jar():
        notes['epubcheck'] = 'needs Java 11 or newer'
    j = tools.find('java')
    status['java'] = f'{j} (version {tools.java_version(j)})' if j else None
    n = tools.find('node')
    status['node'] = version('node', [n, '--version']) if n else None
    try:
        status['mermaid'] = mermaid_ok()
    except OSError as e:
        status['mermaid'] = 'installed but cannot render: ' + str(e)[:200]
    a = tools.command('ace')
    status['ace'] = version('ace', a + ['--version'], env=tools.ace_env(), timeout=120) if a else None
    try:
        import PIL
        import yaml
        status['python'] = f"{sys.version.split()[0]} (PyYAML {yaml.__version__}, Pillow {PIL.__version__})"
    except ImportError as e:
        status['python'] = f'{sys.version.split()[0]} (missing: {e.name})'
    status['notes'] = notes
    return status


def mermaid_ok():
    cmd = tools.command('mmdc')
    if not cmd:
        return None
    with tempfile.TemporaryDirectory() as d:
        src, out = Path(d) / 't.mmd', Path(d) / 't.png'
        src.write_text('graph LR\n  A-->B\n')

        def render():
            return tools.run_process(cmd + ['-q', '-i', str(src), '-o', str(out), '-b', 'white',
                                            '-p', str(tools.puppeteer_config())],
                                     env=tools.tool_env(), timeout=180, tail=65536)
        r = render()
        if r.returncode != 0 and tools.sandbox_error(r.stderr + r.stdout) and not tools.no_sandbox():
            tools.disable_sandbox()
            r = render()
        if r.returncode == 0 and out.exists() and out.stat().st_size > 0:
            return 'renders PNG' + (' (Chrome sandbox off)' if tools.no_sandbox() else '')
        return 'installed but cannot render: ' + (r.stderr.strip().split('\n') or [''])[-1][:200]


def _lock():
    """One install-tools at a time per tool home; a lock older than three hours counts as abandoned."""
    path = tools.tools_dir() / '.install.lock'
    for _ in range(2):
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f'{os.getpid()}\n'.encode())
            os.close(fd)
            return path
        except FileExistsError:
            try:
                age = time.time() - path.stat().st_mtime
            except FileNotFoundError:  # the other run just finished
                continue
            if age < 3 * 3600:
                raise RuntimeError(f'another `mdbindery install-tools` is running (lock file {path}); '
                                   'delete that file if it is not')
            path.unlink(missing_ok=True)
    raise RuntimeError(f'cannot take the install lock {path}')


def install_all(no_node=False, jre='auto', force=False):
    tools.tools_dir().mkdir(parents=True, exist_ok=True)
    lock = _lock()
    try:
        return _install_all(no_node, jre, force)
    finally:
        lock.unlink()
        tools.clear_cache()


def _install_all(no_node, jre, force):
    say(f'mdbindery tool home: {tools.home()}')
    optional_failed = []
    with tempfile.TemporaryDirectory(prefix='mdbindery-install-') as d:
        tmp = Path(d)
        install_pandoc(tmp, force)
        install_epubcheck(tmp, force)
        install_jre(tmp, jre, force)
        tools.clear_cache()
        if not no_node:
            # charts, Ace, and preview are optional: a failure here must not hide the required tools
            try:
                install_node(tmp, force)
                install_npm_packages(force)
            except Exception as e:  # noqa: BLE001
                optional_failed.append(str(e).split('\n')[0][:300])
                say(f'warning: Node.js tools not installed: {optional_failed[-1]}')
                say('  charts become placeholders, Ace and preview are unavailable; run install-tools again later')
    tools.puppeteer_config()
    status = self_test()
    if optional_failed:
        status['notes']['node'] = 'install failed: ' + optional_failed[0]
    return status
