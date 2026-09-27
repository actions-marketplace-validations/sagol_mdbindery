"""mdbindery command line.

Exit codes: 0 success; 1 the book has problems (check errors, failed build gates); 2 bad input
(config, paths, URLs, missing tools); 3 an unexpected internal error.
"""
import argparse
import sys
import traceback
from pathlib import Path

from . import __version__

EPILOG = """examples:
  mdbindery check https://github.com/OWNER/REPO        report what to fix (no files changed)
  mdbindery check . --build                            also run a trial build with all gates
  mdbindery init                                       write mdbindery.yaml for this folder
  mdbindery build                                      build dist/<slug>.epub and run the gates
  mdbindery preview dist/book.epub shots               phone-size screenshots

docs: https://github.com/sagol/mdbindery/tree/main/docs"""


_stdout_open = True


def _out(msg=''):
    """Print to stdout; a closed pipe (mdbindery build | head) must not stop the work."""
    global _stdout_open
    if not _stdout_open:
        return
    try:
        print(msg, flush=True)
    except BrokenPipeError:
        _stdout_open = False
        import os
        try:
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        except OSError:
            pass


def _err(msg):
    print(msg, file=sys.stderr, flush=True)


def cmd_build(a):
    from . import config as config_mod
    from .build import BuildError, build
    try:
        cfg = config_mod.load(a.path, a.config)
    except config_mod.ConfigError as e:
        _err(f'config error: {e}')
        return 2
    lines = []

    def log(msg):
        lines.append(msg)
        if not a.quiet:
            _out(msg)
    reports = (Path(a.out) if a.out else cfg.base / cfg['output_dir']).resolve() / 'reports'

    def save_log():  # also after a failed build, next to its build.json
        if reports.is_dir():
            (reports / 'build.log').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    try:
        s = build(cfg, out_dir=a.out, run_ace=not a.no_ace, keep_work=a.keep_work, log=log)
    except BuildError as e:
        lines.append(f'build error: {e}')
        save_log()
        _err(f'build error: {e}')
        return 2
    save_log()
    if a.quiet:
        _out(lines[-1] if lines else '')
    return 0 if s['ok'] else 1


def cmd_check(a):
    from .check import check, to_json, to_markdown
    try:
        rep = check(a.target, a.config, a.ref, do_build=a.build, render=not a.no_render,
                    log=(lambda *_: None) if a.quiet else _err)
    except (OSError, RuntimeError, ValueError) as e:
        _err(f'check error: {e}')
        return 2
    md = to_markdown(rep)
    try:
        for dest, text in ((a.report, md), (a.json, to_json(rep) if a.json else '')):
            if dest:
                Path(dest).parent.mkdir(parents=True, exist_ok=True)
                Path(dest).write_text(text, encoding='utf-8')
    except OSError as e:
        _err(f'check error: cannot write the report: {e}')
        return 2
    if not a.quiet or not (a.report or a.json):
        _out(md)
    return 0 if rep.ok else 1


def cmd_init(a):
    from . import config as config_mod
    target = Path(a.path).resolve()
    if not target.is_dir():
        _err(f'init error: folder not found: {a.path}')
        return 2
    dest = target / 'mdbindery.yaml'
    if dest.exists() and not a.force:
        _err(f'{dest} already exists (use --force to rewrite it; a backup is kept)')
        return 1
    try:
        cfg = config_mod.load(target, None)
    except config_mod.ConfigError as e:
        if not a.force:
            _err(f'config error: {e}')
            return 2
        _err(f'warning: the existing config is not usable ({e}); writing a fresh one')
        cfg = config_mod.load(target, None, ignore_config=True)
    if not cfg['files']:
        _err(f'init error: no Markdown files in {target} (or in chapters/): nothing to put in the book')
        return 1
    text = config_mod.starter_yaml(cfg)
    if dest.exists():
        backup = dest.with_name(dest.name + '.bak')
        backup.write_bytes(dest.read_bytes())
        _out(f'kept a copy of the old file: {backup}')
    dest.write_text(text, encoding='utf-8')
    _out(f'wrote {dest}' + (f' (reading order from {cfg.order_source})' if cfg.order_source else ''))
    _out(f'review the title, authors, and file order, then run: mdbindery check {a.path}')
    return 0


def cmd_install_tools(a):
    from .installer import install_all
    try:
        status = install_all(no_node=a.no_node, jre=a.java, force=a.force)
    except Exception as e:  # noqa: BLE001 - print any installer failure plainly
        _err(f'install failed: {e}')
        return 2
    _print_status(status)
    missing = [k for k in ('pandoc', 'epubcheck') if not status.get(k)]
    if missing:
        _err(f"\nrequired tools are missing: {', '.join(missing)}")
    return 1 if missing else 0


def _print_status(status):
    _out('--- tools')
    for k in ('pandoc', 'epubcheck', 'java', 'node', 'mermaid', 'ace', 'python'):
        _out(f'{k:10} {status.get(k) or "missing"}')
    for k, note in (status.get('notes') or {}).items():
        _out(f'  {k}: {note}')


def cmd_doctor(a):
    import os
    from . import tools
    from .installer import self_test
    _out(f'mdbindery {__version__}\ntool home: {tools.home()}' +
         ('' if os.environ.get('MDBINDERY_HOME') else ' (default; set MDBINDERY_HOME to use another)'))
    status = self_test()
    _print_status(status)
    if not status.get('pandoc') or not status.get('epubcheck'):
        _out('\nrequired tools are missing: run `mdbindery install-tools`')
        if not os.environ.get('MDBINDERY_HOME') and not tools.tools_dir().exists():
            _out('if you installed the tools into another folder, set MDBINDERY_HOME to it first')
        return 1
    if not status.get('mermaid'):
        _out('\nmermaid-cli is not installed (tools installed with --no-node): charts become placeholders.')
    elif 'cannot' in str(status.get('mermaid')):
        _out('\nMermaid charts will become placeholders (see docs/installation.md, "Headless Chrome").')
    if not status.get('ace'):
        _out('Ace is not installed: builds skip the accessibility check, and `preview` does not work '
             '(run `mdbindery install-tools`).')
    return 0


def cmd_preview(a):
    from .preview import preview
    if a.width < 200 or a.height < 200 or a.width > 4000 or a.height > 8000:
        _err('preview error: --width and --height must be between 200 and 4000/8000 CSS pixels')
        return 2
    try:
        files = preview(a.epub, a.out, a.pages, a.width, a.height, a.full, warn=_err)
    except (RuntimeError, OSError, ValueError) as e:
        _err(f'preview error: {e}')
        return 2
    for f in files:
        _out(f)
    return 0


def parser():
    p = argparse.ArgumentParser(
        prog='mdbindery', formatter_class=argparse.RawDescriptionHelpFormatter, epilog=EPILOG,
        description='Turn a folder or GitHub repository of Markdown chapters into a validated EPUB 3.')
    p.add_argument('--version', action='version', version=f'mdbindery {__version__}')
    sub = p.add_subparsers(dest='cmd', metavar='COMMAND')

    b = sub.add_parser('build', help='build the EPUB and run the validation gates',
                       description='Build <output_dir>/<slug>.epub, then run the gates: links, images, charts, '
                                   'EPUBCheck, Ace, and the word count. Exit 0 when every gate passes, '
                                   '1 when a gate fails, 2 on a config or input error.')
    b.add_argument('path', nargs='?', default=None,
                   help='book folder or config file (default: the --config file\'s folder, else the current folder)')
    b.add_argument('-c', '--config', help='config file (default: <book>/mdbindery.yaml, or inferred)')
    b.add_argument('-o', '--out', help='output folder (default: output_dir from the config, "dist")')
    b.add_argument('--no-ace', action='store_true', help='skip the Ace accessibility check (faster)')
    b.add_argument('--keep-work', action='store_true', help='keep the intermediate files and print their folder')
    b.add_argument('-q', '--quiet', action='store_true', help='print only the final BUILD OK / BUILD FAILED line')
    b.set_defaults(func=cmd_build)

    c = sub.add_parser('check', help='dry run: report what to fix before building (folder or repository URL)',
                       description='Check a book folder or a public repository and print a Markdown report of '
                                   'what to fix. Nothing in the book is changed. Exit 0 when there are no '
                                   'errors, 1 when there are, 2 when the target cannot be read.')
    c.add_argument('target', nargs='?', default='.',
                   help='book folder, GitHub URL (https://github.com/OWNER/REPO[/tree/BRANCH/FOLDER]), '
                        'or git URL (default: .)')
    c.add_argument('-c', '--config', help='config file to use instead of the one in the book folder')
    c.add_argument('--ref', help='branch or tag to check (repository URLs)')
    c.add_argument('--build', action='store_true',
                   help='also run a trial build with EPUBCheck, Ace, and the word count (in a temporary folder)')
    c.add_argument('--no-render', action='store_true', help='do not test-render Mermaid charts (faster)')
    c.add_argument('--report', metavar='FILE', help='write the Markdown report to FILE')
    c.add_argument('--json', metavar='FILE', help='write the JSON report to FILE')
    c.add_argument('-q', '--quiet', action='store_true',
                   help='no progress messages; with --report or --json, print nothing')
    c.set_defaults(func=cmd_check)

    i = sub.add_parser('init', help='write a starter mdbindery.yaml inferred from the book folder',
                       description='Write mdbindery.yaml with the inferred title, language, license, cover, '
                                   'reading order, and (from the git remote) source_url.')
    i.add_argument('path', nargs='?', default='.', help='book folder (default: .)')
    i.add_argument('--force', action='store_true',
                   help='rewrite an existing mdbindery.yaml (metadata, identifier, and options are kept; '
                        'the old file is saved as mdbindery.yaml.bak)')
    i.set_defaults(func=cmd_init)

    t = sub.add_parser('install-tools', help='download pandoc, EPUBCheck, Java (if needed), Node.js, mermaid-cli, Ace',
                       description='Download pinned, checksum-verified tools into the tool home '
                                   '($MDBINDERY_HOME). Safe to run again: installed versions are skipped.')
    t.add_argument('--no-node', action='store_true',
                   help='skip Node.js, mermaid-cli, and Ace (charts become placeholders, no accessibility check, '
                        'no preview)')
    t.add_argument('--java', choices=['auto', 'always', 'never'], default='auto',
                   help='install a Java runtime: auto = only when no Java 11+ is found (default)')
    t.add_argument('--force', action='store_true', help='reinstall even if present')
    t.set_defaults(func=cmd_install_tools)

    d = sub.add_parser('doctor', help='show which tools are installed and working')
    d.set_defaults(func=cmd_doctor)

    v = sub.add_parser('preview', help='phone-size screenshots of EPUB pages',
                       description='Screenshot pages of a built EPUB with headless Chrome. Without PAGE '
                                   'arguments: cover, title page, contents, and the first two chapters.')
    v.add_argument('epub', help='the .epub file')
    v.add_argument('out', help='folder for the PNG files (created if needed)')
    v.add_argument('pages', nargs='*', metavar='PAGE', help='files inside the EPUB, e.g. text/ch002.xhtml or '
                                                             'text/ch002.xhtml#some-id')
    v.add_argument('--width', type=int, default=412, help='viewport width in CSS pixels (default: 412, a phone)')
    v.add_argument('--height', type=int, default=915, help='viewport height in CSS pixels (default: 915)')
    v.add_argument('--full', action='store_true', help='capture the whole page, not one screen')
    v.set_defaults(func=cmd_preview)
    return p


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):  # Windows consoles may not encode every character
        try:
            stream.reconfigure(errors='replace')
        except (AttributeError, ValueError):
            pass
    p = parser()
    a = p.parse_args(argv)
    if not getattr(a, 'func', None):
        p.print_help()
        return 0
    try:
        return a.func(a)
    except KeyboardInterrupt:
        _err('interrupted')
        return 130
    except Exception as e:  # noqa: BLE001 - never show a bare traceback for a user-facing command
        _err(f'internal error: {type(e).__name__}: {e}')
        _err('please report it with the text below: https://github.com/sagol/mdbindery/issues')
        _err(''.join(traceback.format_exception(type(e), e, e.__traceback__)[-3:]).rstrip())
        return 3


if __name__ == '__main__':
    sys.exit(main())
