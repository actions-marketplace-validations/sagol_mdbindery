"""Phone-size screenshots of EPUB pages with the headless Chrome installed by `mdbindery install-tools`."""
import json
import shutil
import tempfile
import zipfile
from pathlib import Path

from . import tools

# EPUB content is treated as untrusted: scripts are off, and the page may load only files of the extracted EPUB
JS = r"""
const puppeteer = require('puppeteer');
const url = require('url');
const jobs = JSON.parse(require('fs').readFileSync(process.argv[2], 'utf8'));
const root = url.pathToFileURL(jobs.root).href + '/';
(async () => {
  const browser = await puppeteer.launch({headless: 'shell', args: jobs.args});
  const page = await browser.newPage();
  await page.setJavaScriptEnabled(false);
  await page.setRequestInterception(true);
  page.on('request', r => (r.url().startsWith(root) || r.url().startsWith('data:')) ? r.continue() : r.abort());
  await page.setViewport({width: jobs.width, height: jobs.height, deviceScaleFactor: 2});
  for (const j of jobs.pages) {
    await page.goto(require('url').pathToFileURL(j.path).href + (j.frag ? '#' + j.frag : ''), {waitUntil: 'load'});
    if (j.frag) {
      const found = await page.evaluate(f => { const e = document.getElementById(f); if (e) e.scrollIntoView(); return !!e; }, j.frag);
      if (!found) console.log('WARN no element with id "' + j.frag + '" in ' + j.name + '; captured the top of the page');
    }
    await page.screenshot({path: j.out, fullPage: jobs.full});
    console.log(j.out);
  }
  await browser.close();
})().catch(e => { console.error(String(e && e.message || e)); process.exit(1); });
"""


MAX_MEMBERS = 50000
MAX_UNPACKED = 2 * 1024 ** 3   # bytes


def preview(epub, out, pages=None, width=412, height=915, full=False, warn=print):
    """Screenshot pages (paths inside the EPUB, optionally with #fragment). Returns written files."""
    epub = Path(epub)
    if not epub.is_file():
        raise ValueError(f'EPUB not found: {epub}')
    if not zipfile.is_zipfile(epub):
        raise ValueError(f'not an EPUB file: {epub}')
    node = tools.find('node')
    modules = tools.npm_modules_dir()
    pup = next(iter(sorted(modules.rglob('node_modules/puppeteer/package.json'))), None) if modules.exists() else None
    if not node or not pup:
        raise RuntimeError('preview needs Node.js and Puppeteer: run `mdbindery install-tools` (without --no-node)')
    tmp = Path(tempfile.mkdtemp(prefix='mdbindery-preview-'))
    try:
        with zipfile.ZipFile(epub) as z:
            names = z.namelist()
            if len(names) > MAX_MEMBERS or sum(i.file_size for i in z.infolist()) > MAX_UNPACKED:
                raise ValueError(f'EPUB too large to preview (over {MAX_MEMBERS} files or '
                                 f'{MAX_UNPACKED // 1024 ** 3} GB unpacked)')
            for n in names:  # an EPUB is a zip: never write outside the temp folder
                if not (tmp / n).resolve().is_relative_to(tmp.resolve()):
                    raise ValueError(f'unsafe path in the EPUB: {n}')
            z.extractall(tmp)
        root = tmp / 'EPUB' if (tmp / 'EPUB').is_dir() else tmp
        xhtml = sorted(n.split('EPUB/', 1)[-1] for n in names if n.endswith('.xhtml'))
        if not pages:
            wanted = ('cover.xhtml', 'title_page.xhtml', 'nav.xhtml', 'ch001.xhtml', 'ch002.xhtml')
            pages = [n.split('EPUB/', 1)[-1] for n in names if n.endswith(wanted)]
        out = Path(out)
        jobs = {'width': width, 'height': height, 'full': full, 'pages': [], 'root': str(tmp.resolve()),
                'args': ['--no-sandbox'] if tools.no_sandbox() else []}
        missing = []
        for p in pages:
            path, _, frag = p.partition('#')
            if path.startswith('EPUB/'):
                path = path[5:]
            f = root / path
            if not f.is_file() or not f.resolve().is_relative_to(tmp.resolve()):
                missing.append(path)
                continue
            name = (path.replace('/', '_') + ('_' + frag if frag else '') + ('_full' if full else '')
                    ).replace('.xhtml', '') + '.png'
            jobs['pages'].append({'path': str(f), 'frag': frag, 'out': str(out / name), 'name': path})
        if missing:
            raise ValueError(f"not in the EPUB: {', '.join(missing)}\npages: {', '.join(xhtml)}")
        out.mkdir(parents=True, exist_ok=True)
        (tmp / 'shot.js').write_text(JS, encoding='utf-8')
        env = tools.tool_env()
        env['NODE_PATH'] = str(pup.parent.parent)
        def shoot():
            (tmp / 'jobs.json').write_text(json.dumps(jobs), encoding='utf-8')
            return tools.run_process([node, str(tmp / 'shot.js'), str(tmp / 'jobs.json')], env=env,
                                     timeout=tools.deadline(600), tail=65536)
        r = shoot()
        if r.returncode and tools.sandbox_error(r.stderr) and '--no-sandbox' not in jobs['args']:
            # this run only; nothing is remembered for later runs
            warn('warning: Chrome\'s sandbox cannot start here; taking these screenshots without it')
            jobs['args'].append('--no-sandbox')
            r = shoot()
        if r.returncode:
            raise RuntimeError((r.stderr.strip().splitlines() or ['headless Chrome failed'])[-1][:500])
        return [l for l in r.stdout.splitlines() if l.strip()]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
