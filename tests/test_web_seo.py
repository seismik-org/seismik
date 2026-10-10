"""SEO de seismik.org: identidad de la marca, mapa del sitio, canónicos y la página de preguntas frecuentes."""
from __future__ import annotations

import html
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

WEB = Path("web")
SITE = "https://seismik.org"
NAMESPACE = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
PUBLIC_PAGES = {
    "/": "index.html",
    "/preguntas-frecuentes/": "preguntas-frecuentes/index.html",
    "/contact/": "contact/index.html",
    "/terms-of-privacy/": "terms-of-privacy/index.html",
    "/terms-of-service/": "terms-of-service/index.html",
    "/acceptable-use/": "acceptable-use/index.html",
    "/delete-account/": "delete-account/index.html",
}


def read(name: str) -> str:
    return (WEB / name).read_text(encoding="utf-8")


def json_ld(page: str) -> list[dict]:
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', read(page), re.S)
    graphs = [json.loads(block) for block in blocks]
    return [node for graph in graphs for node in graph.get("@graph", [graph])]


def text_of(fragment: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", "", fragment)).split())


def test_the_sitemap_lists_every_public_page_and_only_pages_that_exist() -> None:
    root = ET.fromstring(read("sitemap.xml"))
    listed = [item.findtext("s:loc", namespaces=NAMESPACE) for item in root.findall("s:url", NAMESPACE)]

    assert listed == [f"{SITE}{path}" for path in PUBLIC_PAGES]
    for path, page in PUBLIC_PAGES.items():
        assert (WEB / page).is_file(), f"{path} está en el sitemap pero no existe"
    for item in root.findall("s:url", NAMESPACE):
        modified = item.findtext("s:lastmod", namespaces=NAMESPACE)
        assert modified is None or re.fullmatch(r"\d{4}-\d{2}-\d{2}", modified)


def test_robots_allows_the_site_and_points_to_the_sitemap() -> None:
    robots = read("robots.txt")

    assert re.search(r"(?m)^User-agent: \*$", robots) and re.search(r"(?m)^Allow: /$", robots)
    assert f"Sitemap: {SITE}/sitemap.xml" in robots
    assert not re.search(r"(?mi)^Disallow:\s*/\s*$", robots), "un Disallow: / sacaría el sitio de los buscadores"


@pytest.mark.parametrize(("path", "page"), PUBLIC_PAGES.items())
def test_every_public_page_has_one_canonical_address_and_is_indexable(path: str, page: str) -> None:
    document = read(page)

    assert re.findall(r'<link rel="canonical" href="([^"]+)">', document) == [f"{SITE}{path}"]
    assert not re.search(r'<meta name="robots"[^>]*noindex', document), f"{page} no debe llevar noindex"
    assert re.search(r"<title>[^<]{10,}</title>", document) and 'name="description"' in document


def test_the_home_page_states_what_seismik_is_for_search_engines() -> None:
    nodes = {node["@type"]: node for node in json_ld("index.html")}
    organization, website = nodes["Organization"], nodes["WebSite"]

    assert organization["name"] == "Seismik" and organization["url"] == f"{SITE}/"
    assert organization["logo"]["url"].startswith(f"{SITE}/assets/") and (WEB / organization["logo"]["url"].removeprefix(SITE).lstrip("/")).is_file()
    assert organization["sameAs"] == ["https://github.com/seismik-org"]
    assert organization["contactPoint"]["email"] == "support@seismik.org"
    assert website["name"] == "Seismik" and website["publisher"] == {"@id": organization["@id"]}
    home = read("index.html")
    assert 'property="og:site_name" content="Seismik"' in home and 'name="twitter:card"' in home
    assert "SoftwareApplication" not in home, "la app aún no es pública en las tiendas: no se declara como si lo fuera"


def test_the_faq_structured_data_matches_the_visible_questions_and_answers() -> None:
    document = read("preguntas-frecuentes/index.html")
    [faq] = [node for node in json_ld("preguntas-frecuentes/index.html") if node["@type"] == "FAQPage"]
    visible = {
        text_of(question): text_of(answer)
        for question, answer in re.findall(r"<h2>(.*?)</h2>\s*<p>(.*?)</p>", document, re.S)
    }

    structured = {item["name"]: item["acceptedAnswer"]["text"] for item in faq["mainEntity"]}
    assert len(structured) == 11
    assert structured == visible, "Google ignora (o penaliza) un FAQ cuyo texto visible no coincide con los datos estructurados"


def test_the_faq_keeps_the_same_promises_as_the_terms_of_service() -> None:
    answers = " ".join(item["acceptedAnswer"]["text"] for item in json_ld("preguntas-frecuentes/index.html")[0]["mainEntity"]).lower()

    assert "no garantiza que una alerta llegue a tiempo" in answers
    assert "no es una autoridad sismológica" in answers and "servicio de emergencias" in answers
    assert "temporalmente desactivado" in answers  # el SGC, igual que en la página principal
    assert "no tiene relación con seismic" in answers  # desambiguación de la marca
    for claim in ("garantiza la llegada", "100 % confiable", "reemplaza a las autoridades"):
        assert claim not in answers


def test_the_faq_is_linked_from_the_home_page() -> None:
    assert read("index.html").count('href="/preguntas-frecuentes/"') >= 2
