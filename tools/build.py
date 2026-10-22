#!/usr/bin/env python3
"""Build the offline (PWA) version of the game.

Input : game.html  (the same page that is published as the Claude artifact)
Output: index.html, sw.js, fonts/DotGothic16-subset.woff2, icons/*.png

Run from the repository root:  python3 tools/build.py
Needs: fonttools, brotli, pillow  (pip install fonttools brotli pillow)
"""
import hashlib
import json
import pathlib
import re

from fontTools import subset
from PIL import Image, ImageDraw

ROOT = pathlib.Path(__file__).resolve().parent.parent
GAME = ROOT / 'game.html'
FONT_SRC = ROOT / 'tools' / 'DotGothic16-Regular.ttf'
FONT_OUT = ROOT / 'fonts' / 'DotGothic16-subset.woff2'
ICONS = ROOT / 'icons'

APP_NAME = 'ディクテオンの洞窟'
SHORT_NAME = 'ディクテオン'
BG = '#0b0a14'


def subset_font(text):
    chars = set(text)
    chars.update(chr(c) for c in range(0x20, 0x7F))        # ASCII
    chars.update(chr(c) for c in range(0x3000, 0x3100))    # CJK punctuation, hiragana
    chars.update(chr(c) for c in range(0x30A0, 0x3100))    # katakana
    chars.update(chr(c) for c in range(0xFF01, 0xFF5F))    # full-width forms
    opts = subset.Options()
    opts.flavor = 'woff2'
    opts.layout_features = ['*']
    font = subset.load_font(str(FONT_SRC), opts)
    sub = subset.Subsetter(opts)
    sub.populate(text=''.join(sorted(chars)))
    sub.subset(font)
    FONT_OUT.parent.mkdir(exist_ok=True)
    subset.save_font(font, str(FONT_OUT), opts)


def sprite_rows(src, name):
    m = re.search(name + r": \[(.*?)\]", src, re.S)
    return re.findall(r"'([^']*)'", m.group(1))


def palette(src):
    pal = dict(re.findall(r"(\w):'(#[0-9a-fA-F]{6})'", src[src.index('const PAL = {'):src.index('};', src.index('const PAL = {'))]))
    m = re.search(r"const ATHENA_PAL = \{(.*?)\}", src)
    pal.update(dict(re.findall(r"(\w):'(#[0-9a-fA-F]{6})'", m.group(1))))
    return pal


def make_icons(src):
    rows = sprite_rows(src, 'athena_f')
    pal = palette(src)
    ICONS.mkdir(exist_ok=True)

    def render(size, art_frac, rounded):
        # dark ground with a soft gold glow behind the goddess
        bg = tuple(int(BG[i:i + 2], 16) for i in (1, 3, 5))
        gold, cx, cy, rad = (255, 196, 90), size / 2, size * 0.54, size * 0.46
        px = []
        for y in range(size):
            for x in range(size):
                k = max(0.0, 1 - ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 / rad) ** 1.4 * 0.8
                px.append(tuple(int(b + (g - b) * k) for b, g in zip(bg, gold)) + (255,))
        img = Image.new('RGBA', (size, size))
        img.putdata(px)
        d = ImageDraw.Draw(img)
        h = len(rows)
        cell = int(size * art_frac / h)
        ox = (size - 16 * cell) // 2
        oy = (size - h * cell) // 2 + cell
        for y, row in enumerate(rows):
            for x, ch in enumerate(row):
                if ch != '.' and ch in pal:
                    d.rectangle([ox + x * cell, oy + y * cell, ox + (x + 1) * cell - 1, oy + (y + 1) * cell - 1], fill=pal[ch])
        if rounded:
            mask = Image.new('L', (size, size), 0)
            ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=size // 5, fill=255)
            img.putalpha(mask)
        return img

    render(192, 0.78, True).save(ICONS / 'icon-192.png')
    render(512, 0.78, True).save(ICONS / 'icon-512.png')
    render(512, 0.56, False).save(ICONS / 'icon-maskable-512.png')
    render(180, 0.74, False).convert('RGB').save(ICONS / 'apple-touch-icon.png')


def build():
    src = GAME.read_text(encoding='utf-8')
    subset_font(src)
    make_icons(src)

    body = src
    title = re.search(r'<title>.*?</title>', body).group(0)
    body = body.replace(title, '', 1)
    body = re.sub(r'<meta name="claude:viewport-fit-sides"[^>]*>\n?', '', body)
    body = re.sub(r'<link rel="preconnect"[^>]*>\n?', '', body)
    body = re.sub(r'<link rel="stylesheet" href="https://fonts.googleapis.com[^>]*>\n?', '', body)

    head = f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
{title}
<meta name="theme-color" content="{BG}">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="{SHORT_NAME}">
<link rel="manifest" href="manifest.webmanifest">
<link rel="icon" href="icons/icon-192.png">
<link rel="apple-touch-icon" href="icons/apple-touch-icon.png">
<style>
@font-face {{ font-family: 'DotGothic16'; src: url(fonts/DotGothic16-subset.woff2) format('woff2'); font-display: swap; }}
:root {{ padding-top: env(safe-area-inset-top, 0px); padding-bottom: env(safe-area-inset-bottom, 0px); }}
img {{ max-width: 100%; }}
</style>
</head>
<body>
"""
    tail = """
<script>
// offline support: cache everything once, then play without a connection
if ('serviceWorker' in navigator) navigator.serviceWorker.register('sw.js').catch(() => {});
// ask the browser to keep this game's save data even when storage runs low
if (navigator.storage && navigator.storage.persist) navigator.storage.persist().catch(() => {});
</script>
</body>
</html>
"""
    index = head + body + tail
    (ROOT / 'index.html').write_text(index, encoding='utf-8')

    manifest = {
        'name': APP_NAME, 'short_name': SHORT_NAME, 'lang': 'ja',
        'description': '女神アテナの宝さがしローグライク',
        'start_url': './', 'scope': './', 'display': 'standalone', 'orientation': 'portrait',
        'background_color': BG, 'theme_color': BG,
        'icons': [
            {'src': 'icons/icon-192.png', 'sizes': '192x192', 'type': 'image/png'},
            {'src': 'icons/icon-512.png', 'sizes': '512x512', 'type': 'image/png'},
            {'src': 'icons/icon-maskable-512.png', 'sizes': '512x512', 'type': 'image/png', 'purpose': 'maskable'},
        ],
    }
    (ROOT / 'manifest.webmanifest').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    assets = ['./', 'index.html', 'manifest.webmanifest', 'fonts/DotGothic16-subset.woff2',
              'icons/icon-192.png', 'icons/icon-512.png', 'icons/icon-maskable-512.png', 'icons/apple-touch-icon.png']
    h = hashlib.sha256()
    for a in assets[1:]:
        h.update((ROOT / a).read_bytes())
    version = h.hexdigest()[:10]
    sw = (ROOT / 'tools' / 'sw.template.js').read_text(encoding='utf-8')
    sw = sw.replace('__VERSION__', version).replace('__ASSETS__', json.dumps(assets))
    (ROOT / 'sw.js').write_text(sw, encoding='utf-8')
    print('built version', version, '| font', FONT_OUT.stat().st_size // 1024, 'KB | index', len(index.encode()) // 1024, 'KB')


if __name__ == '__main__':
    build()
