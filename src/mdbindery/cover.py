"""Typographic cover (JPEG) for books without artwork."""
import subprocess
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# Linux, macOS, Windows; all of these cover Latin, Cyrillic, and Greek
SERIF_FONTS = ['/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf',
               '/usr/share/fonts/dejavu/DejaVuSerif-Bold.ttf',
               '/System/Library/Fonts/Supplemental/Georgia Bold.ttf',
               '/Library/Fonts/Georgia Bold.ttf',
               'C:/Windows/Fonts/georgiab.ttf', 'C:/Windows/Fonts/timesbd.ttf']
SANS_FONTS = ['/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
              '/usr/share/fonts/dejavu/DejaVuSans.ttf',
              '/System/Library/Fonts/Supplemental/Arial.ttf',
              '/Library/Fonts/Arial Unicode.ttf',
              'C:/Windows/Fonts/arial.ttf', 'C:/Windows/Fonts/segoeui.ttf']


def _fc_match(spec):
    try:
        out = subprocess.run(['fc-match', '-f', '%{file}', spec], capture_output=True, text=True, timeout=10)
        p = out.stdout.strip()
        return p if p and Path(p).exists() else None
    except (OSError, subprocess.SubprocessError):
        return None


def find_font(kind, lang=''):
    """kind: 'serif' (bold, for the title) or 'sans'; lang (e.g. 'ru') picks a font that covers it."""
    spec = 'serif:bold' if kind == 'serif' else 'sans'
    if lang:
        spec += ':lang=' + lang.split('-')[0].lower()
    p = _fc_match(spec)
    if p:
        return p
    for f in (SERIF_FONTS + SANS_FONTS) if kind == 'serif' else (SANS_FONTS + SERIF_FONTS):
        if Path(f).exists():
            return f
    return None


def _font(path, size):
    if path:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    try:
        return ImageFont.load_default(size)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def _fit(draw, text, font_path, max_width, start, minimum, max_lines=4):
    size = start
    while size >= minimum:
        font = _font(font_path, size)
        avg = max(1.0, draw.textlength('abcdefghijklmnopqrstuvwxyz', font=font) / 26)
        lines = textwrap.wrap(text, width=max(8, int(max_width / avg)))
        if len(lines) <= max_lines and all(draw.textlength(l, font=font) <= max_width for l in lines):
            return font, lines
        size -= 4
    font = _font(font_path, minimum)
    return font, textwrap.wrap(text, width=18)


def make_cover(out, title, subtitle='', author='', width=1600, height=2560,
               bg='#1d2330', fg='#f2efe6', accent='#c8643b', serif=None, sans=None, lang=''):
    W, H = width, height
    img = Image.new('RGB', (W, H), bg)
    d = ImageDraw.Draw(img)
    serif = serif or find_font('serif', lang)
    sans = sans or find_font('sans', lang)
    margin = int(W * 0.1)
    font, lines = _fit(d, title, serif, W - 2 * margin, int(W * 0.11), int(W * 0.05))
    y = int(H * 0.16)
    for line in lines:
        d.text((margin, y), line, font=font, fill=fg)
        y += int(getattr(font, 'size', 40) * 1.18)
    if subtitle:
        sfont, slines = _fit(d, subtitle, sans, W - 2 * margin, int(W * 0.045), int(W * 0.028), max_lines=5)
        y += int(H * 0.03)
        for line in slines:
            d.text((margin, y), line, font=sfont, fill=fg)
            y += int(getattr(sfont, 'size', 20) * 1.3)
    band = max(int(H * 0.62), y + int(H * 0.04))
    d.rectangle([0, band, W, band + int(H * 0.012)], fill=accent)
    if author:
        afont, alines = _fit(d, author, sans, W - 2 * margin, int(W * 0.045), int(W * 0.028), max_lines=3)
        y = int(H * 0.86) - (len(alines) - 1) * int(getattr(afont, 'size', 20) * 1.25)
        for line in alines:
            d.text((margin, y), line, font=afont, fill=fg)
            y += int(getattr(afont, 'size', 20) * 1.25)
    img.save(out, 'JPEG', quality=92, optimize=True)
    return out
