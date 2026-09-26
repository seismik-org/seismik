"""Propiedades de seguridad de la web que no deben perderse en un refactor.

Son comprobaciones de código y de configuración, no de la web en vivo: se
ejecutan en CI, sin red, y fallan antes de que un cambio llegue al servidor.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from api.app import create_app
from api.config import AppSettings

WEB = Path("web")
PORTAL_SCRIPTS = ("developers.js", "developers-fixed.js")

# Un `${...}` dentro de un atributo entre comillas: el punto donde un valor sin
# escapar se sale del atributo y se convierte en marcado.
ATTRIBUTE_INTERPOLATION = re.compile(r'\b[a-z-]+="\$\{([^}]*)\}"')


def _script(name: str) -> str:
    return (WEB / name).read_text(encoding="utf-8")


@pytest.mark.parametrize("name", PORTAL_SCRIPTS)
def test_escape_html_also_escapes_quotes(name: str) -> None:
    """`textContent` no escapa comillas, y estos valores van en atributos."""

    source = _script(name)

    assert "&quot;" in source and "&#39;" in source, (
        f"{name}: escapeHtml debe escapar comillas, no sólo `<` y `>`"
    )
    assert "div.textContent = value" not in source, (
        f"{name}: escapar con textContent deja pasar `\"` y `'`"
    )


@pytest.mark.parametrize("name", PORTAL_SCRIPTS)
def test_every_attribute_interpolation_is_escaped(name: str) -> None:
    """Ningún valor entra en un atributo sin pasar por `escapeHtml`."""

    unescaped = [
        expression.strip()
        for expression in ATTRIBUTE_INTERPOLATION.findall(_script(name))
        if "escapeHtml(" not in expression
    ]

    assert not unescaped, (
        f"{name}: valores interpolados en atributos sin escapar: {unescaped}"
    )


@pytest.mark.parametrize("name", PORTAL_SCRIPTS)
def test_the_portal_never_injects_raw_user_text_as_markup(name: str) -> None:
    """Cada `innerHTML` debe recibir marcado construido con `escapeHtml`."""

    for line in _script(name).splitlines():
        if ".innerHTML =" not in line:
            continue
        assert "Markup" in line, (
            f"{name}: `{line.strip()}` asigna innerHTML sin una función de "
            "marcado que escape sus valores"
        )


def test_the_html_carries_no_inline_script() -> None:
    """La CSP del portal no permite `unsafe-inline`: un script inline no corre.

    Comprobarlo aquí evita el fallo silencioso —la página carga y el botón
    simplemente no responde— en vez de descubrirlo en producción.
    """

    for page in sorted(WEB.rglob("*.html")):
        html = page.read_text(encoding="utf-8")
        for match in re.finditer(r"<script\b([^>]*)>", html):
            assert "src=" in match.group(1), (
                f"{page}: hay un <script> inline y la CSP lo bloqueará"
            )
        assert not re.search(r"\son(click|error|load|submit)=", html), (
            f"{page}: hay un manejador inline y la CSP lo bloqueará"
        )


def test_the_api_hides_its_schema_outside_development() -> None:
    """El esquema publica el cuerpo exacto de la ingesta de sismos."""

    base = dict(
        redis_url="redis://localhost:6379/0",
        webhook_hmac_secret="test-hmac-secret",
        crowd_master_secret="test-crowd-secret",
        integration_webhook_master_secret="test-integration-secret",
        consumer_api_key="test-consumer-key",
    )

    served = create_app(AppSettings(environment="staging", **base))
    assert served.docs_url is None
    assert served.openapi_url is None
    assert served.redoc_url is None

    local = create_app(AppSettings(environment="development", **base))
    assert local.docs_url == "/docs"
    assert local.openapi_url == "/openapi.json"


def test_the_api_vhost_declares_a_restrictive_csp() -> None:
    """Una respuesta JSON no debe poder cargar recursos ni ser incrustada."""

    caddyfile = Path("deploy/Caddyfile").read_text(encoding="utf-8")
    api_block = caddyfile.split("api.seismik.org {", 1)[1].split("\n}", 1)[0]

    assert "default-src 'none'" in api_block
    assert "frame-ancestors 'none'" in api_block


def test_the_portal_markup_keeps_every_element_its_script_uses() -> None:
    """`developers.js` busca cada elemento por `id`.

    Un rediseño que renombra o pierde uno deja el portal cargando pero con un
    botón muerto o un panel que nunca aparece, sin ningún error visible.
    """

    script = _script("developers.js")
    html = (WEB / "developers.html").read_text(encoding="utf-8")
    used = set(re.findall(r'elements\["([a-z0-9-]+)"\]', script))
    used |= set(re.findall(r"elements\.([A-Za-z0-9_]+)", script))
    present = set(re.findall(r'\bid="([^"]+)"', html))

    assert used, "developers.js dejó de usar `elements`: revisa esta prueba"
    assert not used - present, f"developers.html perdió elementos: {sorted(used - present)}"


def test_no_page_relies_on_inline_styles() -> None:
    """La CSP de seismik.org y devs.seismik.org es `style-src 'self'`.

    Un `style=""` o un bloque `<style>` no se aplica en producción, aunque en
    local se vea bien.
    """

    for page in sorted(WEB.rglob("*.html")):
        html = page.read_text(encoding="utf-8")
        assert "<style" not in html, f"{page}: bloque <style> bloqueado por la CSP"
        assert not re.search(r"\sstyle=", html), f"{page}: atributo style bloqueado por la CSP"


def test_static_css_and_javascript_are_versioned_before_the_web_image_is_built() -> None:
    """Impide mezclar un HTML nuevo con archivos estáticos de una caché vieja.

    Dockerfile.web sustituye el marcador en cada imagen. El navegador y el CDN
    reciben así una URL nueva para cada hoja/script sin introducir un hash que
    deba mantenerse manualmente en todas las páginas.
    """

    static_ref = re.compile(r'(?:href|src)="/[^"?#]+\.(?:css|js)(?:\?[^\"]*)?"')
    for page in sorted(WEB.rglob("*.html")):
        for reference in static_ref.findall(page.read_text(encoding="utf-8")):
            assert "?v=__ASSET_VERSION__" in reference, (
                f"{page}: recurso estático sin versión: {reference}"
            )

    dockerfile = Path("Dockerfile.web").read_text(encoding="utf-8")
    assert "__ASSET_VERSION__" in dockerfile
    assert "header Cache-Control \"no-cache\"" in Path("deploy/Caddyfile.web").read_text(
        encoding="utf-8"
    )


def test_unknown_web_paths_render_the_seismik_404_page() -> None:
    caddyfile = Path("deploy/Caddyfile.web").read_text(encoding="utf-8")
    page = (WEB / "404.html").read_text(encoding="utf-8")

    assert "handle_errors" in caddyfile
    assert "rewrite @notFound /404.html" in caddyfile
    assert "Error 404" in page
    assert "Ir al inicio" in page


def test_status_page_is_dynamic_and_does_not_disclose_internal_information() -> None:
    page = (WEB / "status.html").read_text(encoding="utf-8")
    script = (WEB / "status.js").read_text(encoding="utf-8")
    worker = Path("deploy/cloudflare-edge-router.js").read_text(encoding="utf-8")

    assert 'src="/status.js?v=__ASSET_VERSION__"' in page
    assert 'fetch("/api/status"' in script
    assert 'source.hostname === "status.seismik.org"' in worker
    assert "${API}/health/ready" in worker
    assert "EDGE_ORIGIN_SECRET" in worker


def test_developer_portal_uses_turnstile_only_for_credential_issuance() -> None:
    script = _script("developers.js")
    page = (WEB / "developers.html").read_text(encoding="utf-8")
    worker = Path("deploy/cloudflare-edge-router.js").read_text(encoding="utf-8")

    assert 'window.location.assign(`${AUTH}/id`)' in script
    assert "challenges.cloudflare.com/turnstile/v0/api.js?render=explicit" in script
    assert 'id="turnstile-container"' in page
    assert "https://challenges.cloudflare.com" in worker
