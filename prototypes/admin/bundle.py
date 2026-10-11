"""Inline static assets for a browser-openable prototype. No runtime data access."""
from pathlib import Path

root = Path(__file__).resolve().parent
html = (root / 'index.html').read_text()
css = (root / 'styles.css').read_text()
js = '\n'.join((root / name).read_text() for name in ['profiles.js', 'conversation.js', 'app.js'])
assert '</script' not in js.lower() and '</style' not in css.lower()
html = html.replace('<link rel="stylesheet" href="styles.css">', '<style>\n' + css + '\n</style>')
html = html.replace('  <script src="app.js" defer></script>\n', '')
html = html.replace('  <script src="profiles.js" defer></script>\n', '')
html = html.replace('  <script src="conversation.js" defer></script>\n', '')
html = html.replace('</body>', '<script>\n' + js + '\n</script>\n</body>')
(root / 'prototype.html').write_text(html)
print('Built prototypes/admin/prototype.html (HTML + CSS + JS; no dependencies)')
