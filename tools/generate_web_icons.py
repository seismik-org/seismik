#!/usr/bin/env python3
"""Genera los iconos del sitio a partir del logotipo de Seismik.

El logotipo mide 1254x1254 y pesa 807 KB. Enlazarlo como favicon obliga a cada
visita a descargarlo entero para pintar 16 píxeles, y deja sin cubrir la
petición que los navegadores y los rastreadores hacen igualmente a
`/favicon.ico`. Aquí se derivan los tamaños reales una sola vez.

El logotipo es un rombo con mucho margen transparente. A 16 píxeles ese margen
se come casi la mitad del icono, así que primero se recorta al contenido y se
vuelve a cuadrar centrado: la marca ocupa entonces todo el lienzo sin
deformarse.

Uso:
    python tools/generate_web_icons.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB = PROJECT_ROOT / "web"
SOURCE = WEB / "assets/seismik_logo.png"

# Azul marino del propio logotipo. Apple compone su icono sobre un cuadrado
# opaco: con transparencia, iOS lo pinta sobre negro y la marca pierde el borde.
BRAND_NAVY = (11, 18, 38, 255)

ICO_SIZES = (16, 32, 48)
PNG_ICONS = {
    "assets/favicon-16.png": 16,
    "assets/favicon-32.png": 32,
    "assets/icon-192.png": 192,
    "assets/icon-512.png": 512,
}
APPLE_TOUCH_SIZE = 180
# Apple recorta las esquinas del icono; sin este margen, el rombo queda cortado.
APPLE_INSET = 0.10


def squared_mark(source: Path) -> Image.Image:
    """Logotipo recortado a su contenido y centrado en un lienzo cuadrado."""

    image = Image.open(source).convert("RGBA")
    box = image.getbbox()
    if box is None:
        raise SystemExit(f"{source} no tiene contenido visible")
    mark = image.crop(box)
    side = max(mark.size)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(
        mark,
        ((side - mark.width) // 2, (side - mark.height) // 2),
        mark,
    )
    return canvas


def scaled(mark: Image.Image, size: int) -> Image.Image:
    return mark.resize((size, size), Image.LANCZOS)


def apple_touch_icon(mark: Image.Image, size: int) -> Image.Image:
    canvas = Image.new("RGBA", (size, size), BRAND_NAVY)
    inner = round(size * (1 - 2 * APPLE_INSET))
    resized = scaled(mark, inner)
    offset = (size - inner) // 2
    canvas.paste(resized, (offset, offset), resized)
    return canvas.convert("RGB")


def manifest() -> dict[str, object]:
    return {
        "name": "Seismik",
        "short_name": "Seismik",
        "description": "Detección sísmica y avisos tempranos en fase experimental.",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "background_color": "#0B1226",
        "theme_color": "#0B1226",
        "icons": [
            {"src": "/assets/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/assets/icon-512.png", "sizes": "512x512", "type": "image/png"},
        ],
    }


def generate(web: Path = WEB) -> list[Path]:
    mark = squared_mark(web / "assets/seismik_logo.png")
    written: list[Path] = []

    for relative, size in PNG_ICONS.items():
        target = web / relative
        scaled(mark, size).save(target, format="PNG", optimize=True)
        written.append(target)

    apple = web / "assets/apple-touch-icon.png"
    apple_touch_icon(mark, APPLE_TOUCH_SIZE).save(apple, format="PNG", optimize=True)
    written.append(apple)

    # Un único .ico con varias resoluciones: es lo que pide el navegador cuando
    # no encuentra ninguna etiqueta, y también lo que usa el historial.
    ico = web / "favicon.ico"
    scaled(mark, max(ICO_SIZES)).save(
        ico, format="ICO", sizes=[(size, size) for size in ICO_SIZES]
    )
    written.append(ico)

    web_manifest = web / "site.webmanifest"
    web_manifest.write_text(
        json.dumps(manifest(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    written.append(web_manifest)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--web", type=Path, default=WEB)
    args = parser.parse_args()

    if not (args.web / "assets/seismik_logo.png").is_file():
        print("No se encontró el logotipo de origen", file=sys.stderr)
        return 1

    for path in generate(args.web):
        size_kb = path.stat().st_size / 1024
        print(f"{path.relative_to(args.web)}  {size_kb:.1f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
