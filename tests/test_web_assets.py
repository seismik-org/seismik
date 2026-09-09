"""La web pública: iconos y los requisitos que revisa Google en OAuth.

Google verifica la marca mirando la página principal. Perder el enlace a la
privacidad o a los términos invalida la verificación, y eso sólo se descubre
cuando la revisión vuelve rechazada días después.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

WEB = Path("web")
PAGES = sorted(WEB.rglob("*.html"))
HOME = WEB / "index.html"

# El logotipo completo mide más de 800 KB: enlazarlo como favicon obliga a
# descargarlo entero para pintar 16 píxeles.
MAX_ICON_KB = {
    "favicon.ico": 40,
    "assets/favicon-16.png": 8,
    "assets/favicon-32.png": 16,
    "assets/apple-touch-icon.png": 64,
    "assets/icon-192.png": 96,
    "assets/icon-512.png": 320,
}


def test_the_icon_set_exists() -> None:
    missing = [name for name in MAX_ICON_KB if not (WEB / name).is_file()]

    assert not missing, f"Faltan iconos: {missing}. Ejecuta tools/generate_web_icons.py"


@pytest.mark.parametrize("name", sorted(MAX_ICON_KB))
def test_each_icon_is_small_enough_to_be_an_icon(name: str) -> None:
    path = WEB / name
    if not path.is_file():
        pytest.skip("El icono se genera con tools/generate_web_icons.py")
    size_kb = path.stat().st_size / 1024

    assert size_kb <= MAX_ICON_KB[name], (
        f"{name} pesa {size_kb:.0f} KB; el límite razonable es {MAX_ICON_KB[name]} KB"
    )


@pytest.mark.parametrize("page", PAGES, ids=lambda path: str(path.relative_to(WEB)))
def test_every_page_declares_the_favicon(page: Path) -> None:
    html = page.read_text(encoding="utf-8")

    assert 'href="/favicon.ico"' in html
    assert 'href="/assets/favicon-32.png"' in html
    assert 'rel="apple-touch-icon"' in html


@pytest.mark.parametrize("page", PAGES, ids=lambda path: str(path.relative_to(WEB)))
def test_no_page_uses_the_full_logo_as_an_icon(page: Path) -> None:
    """El logotipo sigue sirviendo para la marca, no para el icono."""

    html = page.read_text(encoding="utf-8")
    icon_links = [
        line
        for line in html.replace("><", ">\n<").splitlines()
        if 'rel="icon"' in line or 'rel="apple-touch-icon"' in line
    ]

    assert not any("seismik_logo.png" in line for line in icon_links), (
        "Un PNG de 1254x1254 no es un favicon"
    )


def test_the_manifest_is_valid_and_points_at_real_files() -> None:
    manifest = json.loads((WEB / "site.webmanifest").read_text(encoding="utf-8"))

    assert manifest["name"]
    assert manifest["icons"], "El manifiesto debe declarar al menos un icono"
    for icon in manifest["icons"]:
        target = WEB / icon["src"].lstrip("/")
        assert target.is_file(), f"El manifiesto apunta a {icon['src']}, que no existe"


def test_the_homepage_links_privacy_and_terms() -> None:
    """Google exige ambos enlaces visibles para verificar la marca."""

    html = HOME.read_text(encoding="utf-8")

    assert "/terms-of-privacy" in html
    assert "/terms-of-service" in html


def test_the_homepage_describes_the_product() -> None:
    """Una página vacía o de dominio aparcado hace fallar la verificación."""

    html = HOME.read_text(encoding="utf-8")

    assert '<meta name="description"' in html
    assert "Seismik" in html


def test_privacy_and_terms_pages_are_published() -> None:
    for route in ("terms-of-privacy", "terms-of-service"):
        assert (WEB / route / "index.html").is_file(), (
            f"/{route} debe existir: Google comprueba que el enlace resuelve"
        )
