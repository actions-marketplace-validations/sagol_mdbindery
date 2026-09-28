"""PDF output from the prepared Pandoc document, using the existing Chromium tools."""
import hashlib
import html
import json
import os
import re
import shutil
import unicodedata
from collections import Counter
from pathlib import Path

from . import config, tools
from .build import BuildError, DATA, meta_value, run


JS = r"""
const fs = require('fs');
const url = require('url');
const puppeteer = require('puppeteer');
const jobs = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
(async () => {
  const browser = await puppeteer.launch({headless: 'shell', args: jobs.args});
  try {
    const page = await browser.newPage();
    const allowed = new Set(jobs.files.map(p => fs.realpathSync(p)));
    const failures = new Set();
    await page.setJavaScriptEnabled(false);
    await page.setRequestInterception(true);
    page.on('request', request => {
      let ok = false;
      try {
        const u = new URL(request.url());
        ok = u.protocol === 'data:' || (u.protocol === 'file:' &&
          allowed.has(fs.realpathSync(url.fileURLToPath(u))));
      } catch (_) {}
      if (ok) request.continue();
      else { failures.add('blocked resource'); request.abort(); }
    });
    page.on('requestfailed', () => failures.add('failed resource'));
    await page.emulateMediaType('print');
    await page.goto(url.pathToFileURL(jobs.html).href, {waitUntil: 'load', timeout: 60000});
    await page.evaluate(() => document.fonts.ready);
    const documentState = await page.evaluate(() => {
      const source = document.body.cloneNode(true);
      source.querySelectorAll('annotation, script, style').forEach(n => n.remove());
      return {
      text: source.textContent,
      brokenImages: Array.from(document.images).filter(i => !i.complete || !i.naturalWidth).length,
      brokenFonts: Array.from(document.fonts).filter(f => f.status === 'error').length,
      brokenLinks: Array.from(document.querySelectorAll('a[href^="#"]')).filter(a => {
        try { return a.hash && !document.getElementById(decodeURIComponent(a.hash.slice(1))); }
        catch (_) { return true; }
      }).length
    }; });
    if (failures.size || documentState.brokenImages || documentState.brokenFonts || documentState.brokenLinks)
      throw new Error('PDF resources or internal links failed: ' + JSON.stringify({
        resources: Array.from(failures), images: documentState.brokenImages,
        fonts: documentState.brokenFonts, links: documentState.brokenLinks}));
    await page.pdf({path: jobs.output, format: jobs.page_size, printBackground: true,
      margin: {top: jobs.margin, bottom: jobs.margin, left: jobs.margin, right: jobs.margin},
      displayHeaderFooter: jobs.page_numbers, headerTemplate: '<span></span>',
      footerTemplate: '<div style="font-size:9px;text-align:center;width:100%"><span class="pageNumber"></span></div>',
      timeout: 120000});
    fs.writeFileSync(jobs.text, documentState.text, 'utf8');
    console.log(JSON.stringify({browser: await browser.version(),
      puppeteer: require('puppeteer/package.json').version}));
  } finally { await browser.close(); }
})().catch(e => { console.error(String(e && e.message || e)); process.exit(1); });
"""


def requirements():
    """Fail before preparation if optional PDF dependencies are absent."""
    try:
        import pypdf  # noqa: F401
    except ImportError:
        raise BuildError('PDF needs pypdf: install mdbindery[pdf] (from source: pip install ".[pdf]")')
    try:
        return tools.puppeteer_runtime()
    except RuntimeError as e:
        raise BuildError(f'PDF export: {e}') from e


def _tokens(text):
    text = unicodedata.normalize('NFKC', text).replace('\u00ad', '')
    return Counter(re.findall(r"[^\W_][\w'’-]*", text))


def validate_pdf(path, expected, opts):
    """Read the actual PDF and compare text with the rendered HTML, independent of page order."""
    from pypdf import PdfReader
    try:
        with Path(path).open('rb') as stream:
            reader = PdfReader(stream, strict=True)
            count = len(reader.pages)
            if not count or reader.is_encrypted:
                raise ValueError('empty or encrypted PDF')
            text = '\n'.join(p.extract_text() or '' for p in reader.pages)
    except Exception as e:
        raise BuildError(f'PDF cannot be read: {e}') from e
    source, output = _tokens(expected), _tokens(text)
    missing = sum((source - output).values())
    total = sum(source.values())
    limit = max(opts['wordcount_min_words'], total * opts['wordcount_tolerance'])
    ok = bool(source) and any(any(c.isalpha() for c in token) for token in output) and missing <= limit
    return {'result': 'pass' if ok else 'fail', 'pages': count, 'html_words': total,
            'pdf_words': sum(output.values()), 'missing_words': missing, 'tolerance_words': limit}


def render(cfg, analysis, work, css, cover, destination, date, log, *, runtime):
    """Stage only declared assets, print one HTML document, validate, then atomically publish PDF."""
    node, env = runtime
    settings = cfg.opts['pdf']
    document = json.loads(Path(analysis['linked']).read_text(encoding='utf-8'))
    meta = {k: cfg.meta[k] for k in ('title', 'subtitle', 'lang', 'description')}
    meta.update(author=cfg.meta['authors'], date=date)
    document['meta'] = {k: meta_value(v) for k, v in meta.items()}
    assets = work / 'pdf-assets'
    assets.mkdir(exist_ok=True)
    staged = {}

    def asset(source):
        source = Path(source).resolve()
        # Recheck untrusted paths immediately before copying. Generated assets live in work.
        if not cfg.trusted and not (config.contained(source, cfg.repo_root) or config.contained(source, work)):
            raise BuildError('PDF asset points outside the repository')
        if not source.is_file():
            raise BuildError(f'PDF asset not found: {source}')
        if source not in staged:
            name = hashlib.sha256(str(source).encode('utf-8')).hexdigest()[:20] + source.suffix.lower()
            target = assets / name
            shutil.copyfile(source, target)
            staged[source] = target
        return staged[source]

    def walk(value):
        if isinstance(value, dict):
            if value.get('t') == 'Image':
                value['c'][2][0] = asset(value['c'][2][0]).as_uri()
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(document)
    cover_path = asset(cover)
    # Font files are copied only when explicitly listed; CSS never triggers arbitrary file reads.
    fonts = {}
    for name in cfg.opts['embed_fonts']:
        original = Path(name)
        source = original if original.is_absolute() else cfg.base / original
        target = asset(source)
        for key in (name, original.as_posix(), source.resolve().as_uri(), str(source.resolve())):
            fonts[key] = target.as_uri()
    css_text = css.read_text(encoding='utf-8')
    css_text = re.sub(r'url\(\s*([\'"]?)(.*?)\1\s*\)',
                      lambda m: 'url("' + fonts[m[2]] + '")' if m[2] in fonts else m[0], css_text)
    pdf_css = work / 'pdf-book.css'
    pdf_css.write_text(css_text, encoding='utf-8')
    print_css = work / 'print.css'
    shutil.copyfile(DATA / 'print.css', print_css)
    # Bound image height by printable page dimensions, including full-page figures.
    page_height = 297 if settings['page_size'] == 'A4' else 279.4
    with print_css.open('a', encoding='utf-8') as stream:
        stream.write(f'\n:root {{ --page-height: {page_height - 2 * settings["margin_mm"]}mm; }}\n')
    front = work / 'pdf-cover.html'
    front.write_text('<section class="pdf-cover"><img src="' + html.escape(cover_path.as_uri(), quote=True)
                     + '" alt="' + html.escape(cfg.meta['title'], quote=True) + '"></section>', encoding='utf-8')
    book = work / 'pdf-book.json'
    book.write_text(json.dumps(document, ensure_ascii=False), encoding='utf-8')
    html_file = work / 'book.html'
    command = [tools.find('pandoc'), '-f', 'json', '-t', 'html5', '--standalone', '--mathml', book,
               '-o', html_file, '--css', pdf_css.as_uri(), '--css', print_css.as_uri(),
               '--include-before-body', front, '--toc-depth', str(cfg.opts['toc_depth']),
               '--syntax-highlighting=' + (cfg.opts['highlight_style'] or 'none')]
    if cfg.opts['toc']:
        command.append('--toc')
    result = run(command, timeout=1800)
    for line in result.stderr.splitlines():
        log(f'  pandoc: {line}')
    script = work / 'pdf.js'
    script.write_text(JS, encoding='utf-8')
    text_file = work / 'pdf-text.txt'
    temporary = destination.with_name(f'{destination.name}.{os.getpid()}.part')
    # Explicit opt-out only. A failed sandbox or remembered Mermaid fallback never downgrades PDF silently.
    args = ['--no-sandbox'] if os.environ.get('MDBINDERY_NO_SANDBOX') else []
    if args:
        log('  warning: PDF browser sandbox disabled by MDBINDERY_NO_SANDBOX')
    jobs = {'html': str(html_file), 'output': str(temporary), 'text': str(text_file),
            'files': [str(p) for p in [html_file, pdf_css, print_css, *staged.values()]],
            'args': args, 'page_size': settings['page_size'], 'page_numbers': settings['page_numbers'],
            'margin': f'{settings["margin_mm"]}mm'}
    jobs_file = work / 'pdf-jobs.json'
    jobs_file.write_text(json.dumps(jobs), encoding='utf-8')
    try:
        result = run([node, script, jobs_file], env=env, timeout=600, tail=65536)
        browser = json.loads(result.stdout.strip())
        check = validate_pdf(temporary, text_file.read_text(encoding='utf-8'), cfg.opts)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    log(f'  PDF: {check["pages"]} pages; {check["missing_words"]} missing words from rendered HTML')
    return check, browser
