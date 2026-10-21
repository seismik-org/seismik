"""Los tres textos legales de seismik.org deben seguir enlazados desde el pie de cada página pública."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

WEB = Path("web")
LEGAL = {
    "privacidad": "/terms-of-privacy/",
    "términos": "/terms-of-service/",
    "eliminar cuenta y datos": "/delete-account/",
}
PAGES = [
    "index.html",
    "grupo/index.html",
    "contact/index.html",
    "modo-emergencia/index.html",
    "preguntas-frecuentes/index.html",
    "acceptable-use/index.html",
    "terms-of-privacy/index.html",
    "terms-of-service/index.html",
    "delete-account/index.html",
    "privacy.html",
    "404.html",
    "api-terms.html",
    "auth.html",
    "developers.html",
    "developers-public.html",
]


def footer(page: str) -> str:
    match = re.search(r"<footer[^>]*>(.*?)</footer>", (WEB / page).read_text(encoding="utf-8"), re.S)
    assert match, f"{page} no tiene pie de página"
    return match.group(1)


@pytest.mark.parametrize("page", PAGES)
def test_footer_links_the_three_legal_documents(page: str) -> None:
    links = {
        re.sub(r"\s+", " ", text).strip().lower(): href
        for href, text in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', footer(page), re.S)
    }
    for label, path in LEGAL.items():
        assert label in links, f"{page}: falta el enlace «{label}» en el pie"
        assert links[label] in (path, f"https://seismik.org{path}"), f"{page}: «{label}» apunta a {links[label]}"


@pytest.mark.parametrize("path", LEGAL.values())
def test_the_legal_documents_exist(path: str) -> None:
    assert (WEB / path.strip("/") / "index.html").is_file()


def test_privacy_policy_is_published_without_drafting_placeholders() -> None:
    text = (WEB / "terms-of-privacy/index.html").read_text(encoding="utf-8")
    body = re.search(r"<main.*?</main>", text, re.S).group(0)  # type: ignore[union-attr]
    assert not re.search(r"\[[^\]]*(CONFIRMAR|DEFINIR|PENDIENTE|RECOMENDADO)[^\]]*\]", body, re.I)
    assert "menores de 13 años" in body and "Vigente desde" in body
    for provider in ("Google", "Apple", "Cloudflare", "Turnstile"):
        assert provider in body
