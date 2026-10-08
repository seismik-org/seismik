"""Empaqueta el respaldo en el Worker: python tools/generate_fallback_assets.py.

Ejecutar tras modificar offline.*, site.js o sw.js; no necesita dependencias.
"""
from pathlib import Path
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / 'web'
NAMES = ('offline.html', 'offline.css', 'footer.css', 'offline.js', 'site.js', 'sw.js')


def render():
    version = hashlib.sha256(b''.join((WEB / name).read_bytes() for name in NAMES if name != 'sw.js')).hexdigest()[:16]
    sw = WEB / 'sw.js'
    source = re.sub(r'const CACHE = CACHE_PREFIX \+ "[^"]+";', f'const CACHE = CACHE_PREFIX + "{version}";', sw.read_text())
    sw.write_text(source)
    assets = {'/' + name: (WEB / name).read_text().replace('__ASSET_VERSION__', version) for name in NAMES}
    return '// Generado por tools/generate_fallback_assets.py. No editar a mano.\nexport const FALLBACK_ASSETS = ' + json.dumps(assets, ensure_ascii=False, indent=2) + ';\n'


if __name__ == '__main__':
    (ROOT / 'deploy/fallback-assets.js').write_text(render())
