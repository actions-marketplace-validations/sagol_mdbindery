"""Where mdbindery keeps its external tools, and how to find and run them."""
import functools
import json
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

IS_WIN = os.name == 'nt'
IS_MAC = sys.platform == 'darwin'
MIN_PANDOC = (3, 8)  # --syntax-highlighting


def home():
    """Tool home: $MDBINDERY_HOME, else a per-user data directory."""
    env = os.environ.get('MDBINDERY_HOME')
    if env:
        return Path(env).expanduser()
    return default_home()


def default_home():
    if IS_WIN:
        return Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local')) / 'mdbindery'
    if IS_MAC:
        return Path.home() / 'Library' / 'Application Support' / 'mdbindery'
    return Path(os.environ.get('XDG_DATA_HOME') or (Path.home() / '.local' / 'share')) / 'mdbindery'


def tools_dir():
    return home() / 'tools'


def arch():
    m = platform.machine().lower()
    if m in ('x86_64', 'amd64'):
        return 'x64'
    if m in ('arm64', 'aarch64'):
        return 'arm64'
    return m


def _exe(name):
    return name + ('.exe' if IS_WIN else '')


def npm_prefix():
    return tools_dir() / 'npm'


def npm_modules_dir():
    return npm_prefix() / 'node_modules' if IS_WIN else npm_prefix() / 'lib' / 'node_modules'


def puppeteer_cache():
    return tools_dir() / 'puppeteer'


# npm packages run as `node <script>`: no .cmd shims, so no Windows shell is involved
NODE_SCRIPTS = {
    'mmdc': ('@mermaid-js/mermaid-cli', 'mmdc'),
    'ace': ('@daisy/ace', 'ace-puppeteer'),
}


def _package_script(package, bin_name):
    pj = npm_modules_dir() / package / 'package.json'
    if not pj.is_file():
        return None
    try:
        b = json.loads(pj.read_text(encoding='utf-8')).get('bin')
    except (OSError, ValueError):
        return None
    rel = b.get(bin_name) if isinstance(b, dict) else b
    p = (pj.parent / rel) if rel else None
    return p if p and p.is_file() else None


def _npm_cli():
    nd = tools_dir() / 'node'
    for p in (nd / 'node_modules' / 'npm' / 'bin' / 'npm-cli.js', nd / 'lib' / 'node_modules' / 'npm' / 'bin' / 'npm-cli.js'):
        if p.is_file():
            return p
    return None


def candidates(name):
    """Possible locations of a binary tool, in priority order."""
    t = tools_dir()
    if name == 'pandoc':
        return [t / 'pandoc' / 'bin' / _exe('pandoc'), t / 'pandoc' / _exe('pandoc')]
    if name == 'java':
        return [t / 'jre' / 'bin' / _exe('java'), t / 'jre' / 'Contents' / 'Home' / 'bin' / 'java']
    if name == 'node':
        return [t / 'node' / _exe('node'), t / 'node' / 'bin' / 'node']
    return []


@functools.lru_cache(maxsize=None)
def pandoc_version(path):
    try:
        r = subprocess.run([path, '--version'], capture_output=True, text=True, encoding='utf-8',
                           errors='replace', timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.match(r'pandoc(?:\.exe)?\s+(\d+)\.(\d+)', r.stdout or '')
    return (int(m.group(1)), int(m.group(2))) if m else None


def find(name):
    """Absolute path of a tool or None. Bundled tools (including a downloaded Java runtime) win over PATH."""
    return _find(name, str(home()), os.environ.get('PATH', ''))


def clear_cache():
    """Forget what was found (after tools are installed or removed)."""
    _find.cache_clear()
    pandoc_version.cache_clear()


@functools.lru_cache(maxsize=None)
def _find(name, _home, _path):
    if name == 'epubcheck':
        jar = epubcheck_jar()
        return str(jar) if jar else None
    if name in NODE_SCRIPTS:
        return str(_package_script(*NODE_SCRIPTS[name]) or '') or None
    if name == 'npm':
        p = _npm_cli()
        return str(p) if p else None
    for p in candidates(name):
        if p.exists():
            return str(p)
    path = shutil.which(name)
    if path and name == 'pandoc' and (pandoc_version(path) or (0, 0)) < MIN_PANDOC:
        return None  # too old for the options mdbindery passes
    return path


def command(name):
    """argv prefix to run a tool, or None."""
    if name in NODE_SCRIPTS or name == 'npm':
        node, script = find('node'), find(name)
        return [node, script] if node and script else None
    if name == 'epubcheck':
        return epubcheck_cmd()
    p = find(name)
    return [p] if p else None


def old_pandoc_on_path():
    """Version string of a pandoc on PATH that is too old to use, for doctor."""
    path = shutil.which('pandoc')
    v = pandoc_version(path) if path else None
    return f'{path} ({v[0]}.{v[1]})' if v and v < MIN_PANDOC else None


def epubcheck_jar():
    base = tools_dir() / 'epubcheck'
    if base.exists():
        jars = sorted(base.glob('**/epubcheck.jar'))
        if jars:
            return jars[0]
    return None


def tool_env():
    """Environment for running bundled tools (node on PATH, puppeteer cache)."""
    env = dict(os.environ)
    extra = []
    n = find('node')
    if n:
        extra.append(str(Path(n).parent))
    env['PATH'] = os.pathsep.join(extra + [env.get('PATH', '')])
    env['PUPPETEER_CACHE_DIR'] = str(puppeteer_cache())
    return env


def puppeteer_runtime():
    """Node and environment for the installed Puppeteer shared by preview and PDF."""
    node = find('node')
    modules = npm_modules_dir()
    package = next(iter(sorted(modules.rglob('node_modules/puppeteer/package.json'))), None) if modules.exists() else None
    if not node or not package:
        raise RuntimeError('Node.js and Puppeteer are required: run `mdbindery install-tools` (without --no-node)')
    env = tool_env()
    env['NODE_PATH'] = str(package.parent.parent)
    return node, env


def java_version(java):
    try:
        r = subprocess.run([java, '-version'], capture_output=True, text=True, encoding='utf-8',
                           errors='replace', timeout=30)
    except Exception:
        return None
    out = (r.stderr or '') + (r.stdout or '')
    m = re.search(r'version "(\d+)(?:\.(\d+))?', out)
    if not m:
        return None
    major = int(m.group(1))
    if major == 1 and m.group(2):  # "1.8.0" style
        major = int(m.group(2))
    return major


def epubcheck_cmd():
    """Command prefix to run EPUBCheck, or None."""
    jar = epubcheck_jar()
    java = find('java')
    if jar and java and (java_version(java) or 0) >= 11:
        return [java, '-jar', str(jar)]
    return None


def no_sandbox():
    """Chrome's sandbox fails as root, in most containers, and on CI runners that restrict user namespaces."""
    if os.environ.get('MDBINDERY_NO_SANDBOX') or os.environ.get('CI'):
        return True
    if hasattr(os, 'geteuid') and os.geteuid() == 0:
        return True
    return (tools_dir() / 'no-sandbox').exists()


def puppeteer_config():
    """Puppeteer launch options for mermaid-cli; the sandbox stays on where it works."""
    cfg = tools_dir() / 'puppeteer-config.json'
    args = ['--no-sandbox', '--disable-setuid-sandbox'] if no_sandbox() else []
    text = json.dumps({'args': args}) + '\n'
    cfg.parent.mkdir(parents=True, exist_ok=True)
    if not cfg.exists() or cfg.read_text() != text:
        cfg.write_text(text)
    return cfg


def disable_sandbox():
    """Remember that Chrome's sandbox does not work on this machine (after a sandbox error)."""
    tools_dir().mkdir(parents=True, exist_ok=True)
    (tools_dir() / 'no-sandbox').write_text('Chrome reported that its sandbox cannot run here\n')
    return puppeteer_config()


SANDBOX_ERRORS = re.compile(r'No usable sandbox|without --no-sandbox|setuid sandbox|suid[ _]sandbox|'
                            r'Failed to move to new namespace|crbug\.com/638180', re.I)


def sandbox_error(text):
    """True only for Chrome's own sandbox start-up failures."""
    return bool(SANDBOX_ERRORS.search(text or ''))


class Completed:
    def __init__(self, returncode, stdout, stderr, timed_out):
        self.returncode, self.stdout, self.stderr, self.timed_out = returncode, stdout, stderr, timed_out


def deadline(seconds):
    """A stage's time limit; MDBINDERY_TIMEOUT_SCALE multiplies every limit (slow machines, huge books)."""
    try:
        scale = float(os.environ.get('MDBINDERY_TIMEOUT_SCALE') or 1)
    except ValueError:
        scale = 1.0
    return seconds * max(scale, 0.1)


def _kill_tree(proc):
    try:
        if IS_WIN:
            subprocess.run(['taskkill', '/T', '/F', '/PID', str(proc.pid)], capture_output=True, timeout=30)
        else:
            os.killpg(proc.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        proc.kill()
    except OSError:
        pass


def run_process(cmd, env=None, cwd=None, timeout=None, tail=None):
    """Run a command without a shell; stop its whole process tree on timeout or Ctrl+C.

    Output goes to temporary files, not pipes; tail keeps only the last N bytes of each stream
    (diagnostic output), otherwise all of it is returned (data such as pandoc's plain text).
    """
    kw = {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP} if IS_WIN else {'start_new_session': True}
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        proc = subprocess.Popen([str(c) for c in cmd], env=env, cwd=cwd, stdin=subprocess.DEVNULL,
                                stdout=out, stderr=err, **kw)
        timed_out = False
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill_tree(proc)
            proc.wait()
        except BaseException:
            _kill_tree(proc)
            proc.wait()
            raise

        def read(f):
            size = f.seek(0, 2)
            f.seek(size - tail if tail and size > tail else 0)
            return f.read().decode('utf-8', errors='replace')
        stdout, stderr = read(out), read(err)
    if timed_out:
        stderr += f'\n(stopped after {timeout:.0f} s)'
    return Completed(-9 if timed_out else proc.returncode, stdout, stderr, timed_out)


def _headless_shell(version):
    base = puppeteer_cache() / 'chrome-headless-shell'
    if not base.exists():
        return None
    for d in sorted(base.glob(f'*-{version}')):
        for name in ('chrome-headless-shell.exe', 'chrome-headless-shell'):
            hits = [p for p in d.rglob(name) if p.is_file()]
            if hits:
                return hits[0]
    return None


def ace_env():
    """Environment for Ace: its Puppeteer is pointed at the matching headless-shell build,
    so no full Chrome download is needed."""
    env = tool_env()
    ace_dir = npm_modules_dir() / '@daisy' / 'ace'
    for rev in sorted(ace_dir.rglob('puppeteer-core/lib/cjs/puppeteer/revisions.js')) if ace_dir.exists() else []:
        m = re.search(r"'chrome-headless-shell':\s*'([\d.]+)'", rev.read_text(encoding='utf-8', errors='replace'))
        if m:
            exe = _headless_shell(m.group(1))
            if exe:
                env['PUPPETEER_EXECUTABLE_PATH'] = str(exe)
                break
    return env
