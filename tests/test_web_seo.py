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
    "/modo-emergencia/": "modo-emergencia/index.html",
    "/preguntas-frecuentes/": "preguntas-frecuentes/index.html",
    "/contact/": "contact/index.html",
    "/terms-of-privacy/": "terms-of-privacy/index.html",
    "/terms-of-service/": "terms-of-service/index.html",
    "/acceptable-use/": "acceptable-use/index.html",
    "/delete-account/": "delete-account/index.html",
    "/grupo/": "grupo/index.html",
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
    assert re.search(r"<title>[^<]{7,}</title>", document) and 'name="description"' in document


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
    assert len(structured) == 13
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
    assert read("index.html").count('href="/preguntas-frecuentes/"') >= 1  # el pie de página; el menú móvil sólo lleva lo esencial


def test_emergency_feature_is_discoverable_and_honest_about_offline_limits() -> None:
    home = read("index.html")
    assert 'id="modo-emergencia"' in home
    assert home.count('href="/modo-emergencia/"') >= 3
    page = read("modo-emergencia/index.html")
    visible = text_of(page.split("<body>")[1]).lower()
    for phrase in ("no se reciben sismos nuevos", "ni se actualiza la ubicación familiar",
                   "historial guardado", "no exige iniciar sesión", "reportes", "pendientes",
                   "no garantiza avisar antes de la sacudida", "no representa a ninguna entidad pública"):
        assert phrase in visible
    assert "https://www.cdc.gov/earthquakes/safety/index.html" in page
    assert "SoftwareApplication" not in page  # no inventar disponibilidad pública o calificaciones
    nodes = json_ld("modo-emergencia/index.html")
    assert {node["@type"] for node in nodes} == {"WebPage", "BreadcrumbList"}
    assert "https://seismik.org/modo-emergencia/" in read("llms.txt")


@pytest.mark.parametrize("page", ["index.html", "modo-emergencia/index.html", "preguntas-frecuentes/index.html"])
def test_discovery_titles_social_tags_and_visible_headings_are_consistent(page: str) -> None:
    document = read(page)
    [title] = re.findall(r"<title>([^<]+)</title>", document)
    assert "Seismik" in title and len(title) <= 40
    assert re.findall(r'<meta property="og:title" content="([^"]+)">', document) == [title]
    assert re.findall(r'<meta name="twitter:title" content="([^"]+)">', document) == [title]
    assert len(re.findall(r"<h1[ >]", document)) == 1
    assert 'name="keywords"' not in document  # Google no utiliza esta etiqueta para posicionar


def test_the_home_menu_is_short_and_mentions_waves() -> None:
    home = read("index.html")
    menu = home.split('<nav class="menu-panel" aria-label="Menú">')[1].split("</nav>")[0]
    links = re.findall(r'<a href="([^"]+)">', menu)

    assert len(links) <= 7, "el menú de las tres rayas lleva sólo lo esencial"
    assert "https://waves.seismik.org/" in links and "https://devs.seismik.org/" in links and "https://ifeltit.seismik.org/" in links
    assert home.count('href="https://waves.seismik.org/"') >= 3, "menú móvil, barra de escritorio y la sección de Waves"
    assert 'id="waves"' in home and "Ir a Waves" in home
    for page in ("contact/index.html", "developers.html"):
        assert 'href="https://waves.seismik.org/"' in read(page), page


AI_CRAWLERS = ("GPTBot", "OAI-SearchBot", "ChatGPT-User", "ClaudeBot", "Claude-SearchBot", "Claude-User", "Claude-Web", "anthropic-ai",
               "PerplexityBot", "Perplexity-User", "Google-Extended", "Applebot-Extended", "CCBot", "Amazonbot", "Meta-ExternalAgent",
               "cohere-ai", "MistralAI-User", "DuckAssistBot")
SEARCH_CRAWLERS = ("Googlebot", "Bingbot", "BingPreview", "DuckDuckBot", "Applebot")


def robots_groups(text: str) -> dict[str, list[str]]:
    """Cada agente con las reglas de su grupo (los agentes consecutivos comparten reglas)."""
    groups: dict[str, list[str]] = {}
    agents: list[str] = []
    rules: list[str] = []
    for raw in text.splitlines() + ["User-agent: "]:
        line = raw.split("#")[0].strip()
        if not line:
            continue
        key, _, value = line.partition(":")
        if key.lower() == "user-agent":
            if rules:
                for agent in agents:
                    groups[agent] = rules
                agents, rules = [], []
            if value.strip():
                agents.append(value.strip())
        elif key.lower() in {"allow", "disallow", "content-signal"}:
            rules.append(f"{key.lower()}: {value.strip()}")
    return groups


@pytest.mark.parametrize("path", ["web/robots.txt", "waves/static/robots.txt"])
def test_robots_explicitly_welcome_search_engines_and_ai_crawlers(path: str) -> None:
    text = Path(path).read_text(encoding="utf-8")
    groups = robots_groups(text)

    for agent in (*SEARCH_CRAWLERS, *AI_CRAWLERS):
        assert agent in groups, f"{agent} no tiene permiso explícito en {path}"
        assert "allow: /" in groups[agent], agent
    for agent, rules in groups.items():
        assert "disallow: /" not in rules, f"{agent} quedaría fuera del sitio"
        assert "disallow:" not in rules, agent
    assert "content-signal: search=yes, ai-input=yes, ai-train=yes" in groups["*"]


def test_robots_only_keep_functional_routes_out_of_the_index() -> None:
    main = robots_groups(Path("web/robots.txt").read_text(encoding="utf-8"))["*"]
    waves = robots_groups(Path("waves/static/robots.txt").read_text(encoding="utf-8"))["*"]

    assert [rule for rule in main if rule.startswith("disallow")] == ["disallow: /v1/", "disallow: /admin/"]
    assert [rule for rule in waves if rule.startswith("disallow")] == ["disallow: /v1/", "disallow: /login", "disallow: /explore"]


def test_each_robots_points_to_its_own_sitemap_and_the_main_one_also_to_waves() -> None:
    main = Path("web/robots.txt").read_text(encoding="utf-8")
    waves = Path("waves/static/robots.txt").read_text(encoding="utf-8")

    assert re.findall(r"(?m)^Sitemap: (\S+)$", main) == ["https://seismik.org/sitemap.xml", "https://waves.seismik.org/sitemap.xml"]
    assert re.findall(r"(?m)^Sitemap: (\S+)$", waves) == ["https://waves.seismik.org/sitemap.xml"]
    root = ET.fromstring(Path("waves/static/sitemap.xml").read_text(encoding="utf-8"))
    assert [item.findtext("s:loc", namespaces=NAMESPACE) for item in root.findall("s:url", NAMESPACE)] == ["https://waves.seismik.org/"]


def test_llms_txt_describes_the_site_and_waves_for_language_models() -> None:
    main = Path("web/llms.txt").read_text(encoding="utf-8")
    waves = Path("waves/static/llms.txt").read_text(encoding="utf-8")

    assert main.startswith("# Seismik") and "https://waves.seismik.org/" in main and "https://devs.seismik.org/" in main
    assert waves.startswith("# Seismik Waves") and "MiniSEED" in waves and "no sustituye a las agencias sismológicas oficiales" in waves
    for text in (main, waves):
        for url in re.findall(r"\((https://[^)]+)\)", text):
            assert "localhost" not in url and url.startswith("https://"), url


def test_the_waves_home_page_is_indexable_and_canonical() -> None:
    page = Path("waves/static/index.html").read_text(encoding="utf-8")

    assert '<link rel="canonical" href="https://waves.seismik.org/">' in page
    assert 'name="robots" content="index,follow' in page and "noindex" not in page
    assert 'property="og:title"' in page and 'property="og:url" content="https://waves.seismik.org/"' in page
    assert 'name="robots" content="noindex"' in Path("waves/static/explore.html").read_text(encoding="utf-8"), "el visor privado no se indexa"
