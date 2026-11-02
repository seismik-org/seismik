import importlib.util
import re
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

WAVES = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("waves_app", WAVES / "app.py")
waves = importlib.util.module_from_spec(spec)
spec.loader.exec_module(waves)
client = TestClient(waves.app)

REAL_CLIENT = httpx.AsyncClient
TOKEN = "t" * 48
COOKIES = {"seismik_session": TOKEN}


class Api:
    """Sustituye a la API de Seismik: registra lo que se le pregunta y responde lo que cada prueba necesite."""

    def __init__(self, monkeypatch, *, status=200, body=None, error=None):
        self.calls = []
        self.status, self.error = status, error
        self.body = {"uid": "u-1", "email": "Support@Seismik.org", "name": "Soporte"} if body is None else body
        outer = self

        def handler(request: httpx.Request) -> httpx.Response:
            outer.calls.append((request.method, str(request.url), request.headers.get("cookie")))
            if outer.error:
                raise outer.error
            return httpx.Response(outer.status, json=outer.body) if request.method == "GET" else httpx.Response(204)

        monkeypatch.setattr(waves.httpx, "AsyncClient", lambda **kw: REAL_CLIENT(transport=httpx.MockTransport(handler), **kw))


@pytest.fixture(autouse=True)
def reset(monkeypatch):
    waves.app.dependency_overrides.clear()
    waves._sessions.clear()
    monkeypatch.delenv("WAVES_PILOT_EMAILS", raising=False)
    monkeypatch.delenv("WAVES_DOWNLOADS", raising=False)
    yield
    waves.app.dependency_overrides.clear()
    waves._sessions.clear()


# --- público ------------------------------------------------------------------------------------------------


def test_public_summary_and_portal():
    data = client.get("/v1/waves/summary").json()
    assert data["files"] == 607
    assert data["waveforms"] == 561
    assert data["live"] is False and data["downloads_enabled"] is False
    response = client.get("/")
    assert response.status_code == 200 and "Waves" in response.text
    assert response.headers["cache-control"] == "private, no-store"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_summary_describes_the_archive_in_aggregate_without_naming_recordings():
    data = client.get("/v1/waves/summary").json()
    groups = {item["id"]: item for item in data["groups"]}

    assert [item["id"] for item in data["groups"]] == ["audit", "evaluation", "historical", "cases", "fixtures"]
    assert sum(item["recordings"] for item in data["groups"]) == data["waveforms"] == 561
    assert sum(item["bytes"] for item in data["groups"]) == data["recording_bytes"]
    assert groups["evaluation"]["recordings"] == 432 and groups["fixtures"]["recordings"] == 4
    assert data["formats"] == ["MiniSEED"] and data["snapshot_date"] == "2026-10-18"
    assert data["resource_files"] == 5 and groups["audit"]["recordings"] == 1
    text = client.get("/v1/waves/summary").text
    assert ".mseed" not in text and "calibration/" not in text, "el resumen público no nombra ninguna grabación"


# --- la sesión se comprueba en el servidor ----------------------------------------------------------------


def test_private_routes_require_a_seismik_session():
    assert client.get("/v1/waves/session").status_code == 401
    assert client.get("/v1/waves/catalog").status_code == 401
    assert client.get("/v1/waves/records/unknown").status_code == 401
    for cookie in ("x", "a b", "t" * 500, "a;b" * 12):
        assert client.get("/v1/waves/catalog", cookies={"seismik_session": cookie}).status_code == 401, cookie


def test_the_browser_cannot_vouch_for_itself(monkeypatch):
    api = Api(monkeypatch, status=401, body={"detail": "Sesión requerida"})
    monkeypatch.setenv("WAVES_PILOT_EMAILS", "support@seismik.org")
    forged = {"Authorization": "Bearer anything", "X-Seismik-Email": "support@seismik.org", "X-Email": "support@seismik.org"}

    assert client.get("/v1/waves/catalog", headers=forged).status_code == 401
    assert client.get("/v1/waves/catalog", headers=forged, cookies=COOKIES).status_code == 401
    assert [call[0] for call in api.calls] == ["GET"], "sólo la cookie de sesión llega a preguntarse a la API"


def test_session_is_resolved_by_the_seismik_api_and_the_cookie_is_forwarded(monkeypatch):
    api = Api(monkeypatch)
    monkeypatch.setenv("WAVES_PILOT_EMAILS", "support@seismik.org")

    data = client.get("/v1/waves/session", cookies=COOKIES).json()

    assert data == {"approved": True, "email": "support@seismik.org", "downloads_enabled": False, "mode": "historical_pilot"}
    assert api.calls == [("GET", "https://api.seismik.org/v1/oauth/session", f"seismik_session={TOKEN}")]


def test_other_accounts_are_identified_but_not_approved(monkeypatch):
    Api(monkeypatch, body={"uid": "u-2", "email": "otra@example.org", "name": "Otra"})
    monkeypatch.setenv("WAVES_PILOT_EMAILS", "support@seismik.org")

    assert client.get("/v1/waves/session", cookies=COOKIES).json()["approved"] is False
    denied = client.get("/v1/waves/catalog", cookies=COOKIES)
    assert denied.status_code == 403 and "otra@example.org" not in denied.text
    assert client.get("/v1/waves/records/cualquiera", cookies=COOKIES).status_code == 403


def test_without_an_allowlist_nobody_is_approved(monkeypatch):
    Api(monkeypatch)

    assert client.get("/v1/waves/session", cookies=COOKIES).json()["approved"] is False
    assert client.get("/v1/waves/catalog", cookies=COOKIES).status_code == 403


@pytest.mark.parametrize("kwargs", [
    {"status": 500, "body": {}}, {"status": 200, "body": {"nope": 1}}, {"status": 200, "body": {"uid": "u", "email": "sin-arroba"}},
    {"error": httpx.ConnectTimeout("x")},
])
def test_if_the_api_cannot_confirm_the_session_access_is_denied(monkeypatch, kwargs):
    Api(monkeypatch, **kwargs)
    monkeypatch.setenv("WAVES_PILOT_EMAILS", "support@seismik.org;sin-arroba")

    response = client.get("/v1/waves/catalog", cookies=COOKIES)

    assert response.status_code in (401, 503) and "items" not in response.text


def test_an_expired_session_asks_to_sign_in_again(monkeypatch):
    Api(monkeypatch, status=401, body={"detail": "Sesión expirada"})

    assert client.get("/v1/waves/session", cookies=COOKIES).status_code == 401


def test_confirmed_sessions_are_cached_briefly(monkeypatch):
    api = Api(monkeypatch)
    monkeypatch.setenv("WAVES_PILOT_EMAILS", "support@seismik.org")
    for _ in range(3):
        assert client.get("/v1/waves/session", cookies=COOKIES).status_code == 200
    assert len(api.calls) == 1

    waves._sessions.clear()
    client.get("/v1/waves/session", cookies=COOKIES)
    assert len(api.calls) == 2


def test_failures_are_not_cached(monkeypatch):
    api = Api(monkeypatch, status=401, body={})
    for _ in range(2):
        assert client.get("/v1/waves/session", cookies=COOKIES).status_code == 401
    assert len(api.calls) == 2


# --- catálogo ----------------------------------------------------------------------------------------------


def test_approved_catalog_filters_pagination_and_record(monkeypatch):
    Api(monkeypatch)
    monkeypatch.setenv("WAVES_PILOT_EMAILS", "support@seismik.org")
    data = client.get("/v1/waves/catalog?category=replay&limit=2", cookies=COOKIES).json()
    assert len(data["items"]) == 2
    assert all(r["category"] == "replay" for r in data["items"])
    assert data["items"][0]["validation_status"] == "research_not_validated"
    assert client.get("/v1/waves/records/" + data["items"][0]["id"], cookies=COOKIES).status_code == 200
    assert client.get("/v1/waves/records/unknown", cookies=COOKIES).status_code == 404
    assert client.get("/v1/waves/catalog?limit=500", cookies=COOKIES).status_code == 422
    assert client.get("/v1/waves/catalog?offset=-1", cookies=COOKIES).status_code == 422
    assert client.get("/v1/waves/catalog?q=no-such-record", cookies=COOKIES).json()["total"] == 0
    page2 = client.get("/v1/waves/catalog?limit=25&offset=25", cookies=COOKIES).json()
    assert page2["offset"] == 25 and page2["total"] == 561 and len(page2["items"]) == 25


# --- visor de ondas y catálogo legible -----------------------------------------------------------------------


def approved(monkeypatch):
    Api(monkeypatch)
    monkeypatch.setenv("WAVES_PILOT_EMAILS", "support@seismik.org")


def catalog(path="", **params):
    return client.get("/v1/waves/catalog" + path, params=params, cookies=COOKIES).json()


def test_catalog_rows_say_which_earthquake_each_recording_is(monkeypatch):
    approved(monkeypatch)
    data = catalog(limit=100, kind="evento")
    first = data["items"][0]

    assert first["view"]["kind"] == "evento" and first["group"] in {"evaluation", "historical", "cases", "fixtures"}
    assert {"title", "origin_time", "magnitude", "stations", "duration_s", "reference"} <= set(first["view"])
    dates = [item["view"]["origin_time"] for item in data["items"]]
    assert dates == sorted(dates, reverse=True), "por defecto, los más recientes primero"
    assert data["total"] == 495


def test_catalog_filters_by_kind_group_magnitude_text_and_sort(monkeypatch):
    approved(monkeypatch)
    assert catalog(kind="ruido")["total"] == 61
    assert catalog(group="fixtures")["total"] == 4
    assert {i["group"] for i in catalog(group="historical", limit=100)["items"]} == {"historical"}
    big = catalog(minimum_magnitude=6, kind="evento", limit=100)
    assert big["total"] >= 2 and all(i["view"]["magnitude"] >= 6 for i in big["items"])
    by_magnitude = [i["view"]["magnitude"] for i in catalog(kind="evento", sort="magnitude", limit=50)["items"]]
    assert by_magnitude == sorted(by_magnitude, reverse=True)
    assert catalog(q="jordán", kind="evento")["total"] > 0, "el texto busca también en el lugar"
    names = [i["name"] for i in catalog(sort="name", limit=50)["items"]]
    assert names == sorted(names)
    for bad in ({"group": "otro"}, {"kind": "x"}, {"sort": "azar"}, {"minimum_magnitude": 11}):
        assert client.get("/v1/waves/catalog", params=bad, cookies=COOKIES).status_code == 422, bad


def test_preview_returns_a_reduced_waveform_envelope_for_approved_users_only(monkeypatch):
    approved(monkeypatch)
    item = catalog(kind="evento", limit=1)["items"][0]

    response = client.get(f"/v1/waves/records/{item['id']}/preview", cookies=COOKIES)
    data = response.json()

    assert response.status_code == 200 and data["downloads_enabled"] is False
    assert data["record"]["id"] == item["id"] and data["context"]["title"] == item["view"]["title"]
    assert data["buckets"] == 600 and 3 <= len(data["traces"]) <= 24
    for trace in data["traces"]:
        assert len(trace["mins"]) == len(trace["maxs"]) == 600
        assert all(low <= high for low, high in zip(trace["mins"], trace["maxs"]))
        assert trace["samples"] > 20_000 and trace["rate"] == 100.0, "se reduce de decenas de miles de muestras a 600 intervalos"
        assert trace["peak_counts"] >= max(abs(min(trace["mins"])), abs(max(trace["maxs"]))) - 1
    assert len(response.content) < 400_000


def test_preview_is_closed_without_an_approved_session_and_for_bad_ids(monkeypatch):
    record = next(iter(waves.view()))
    assert client.get(f"/v1/waves/records/{record}/preview").status_code == 401
    Api(monkeypatch, body={"uid": "u", "email": "otra@example.org", "name": "x"})
    monkeypatch.setenv("WAVES_PILOT_EMAILS", "support@seismik.org")
    assert client.get(f"/v1/waves/records/{record}/preview", cookies=COOKIES).status_code == 403
    waves._sessions.clear()
    approved(monkeypatch)
    for bad in ("0" * 24, "../../app", "ZZZ", "a" * 200):
        assert client.get(f"/v1/waves/records/{bad}/preview", cookies=COOKIES).status_code == 404, bad


def test_every_recording_has_a_preview_and_a_context():
    records = waves.index()["records"]
    previews = WAVES / "previews"
    assert {r["id"] for r in records} == set(waves.view())
    assert all((previews / f"{r['id']}.json.gz").is_file() for r in records)
    assert not list(previews.glob("*.mseed")), "los originales nunca viajan con el servicio"


def test_the_explorer_page_is_static_and_same_origin():
    html = (WAVES / "static/explore.html").read_text(encoding="utf-8")
    assert " style=" not in html and "<script>" not in html
    external = re.findall(r'(?:src|href)="(https?://[^"]+)"', html)
    assert external and all(re.match(r"https://(?:[a-z]+\.)?seismik\.org/", url) for url in external), external
    assert not re.findall(r'<(?:script|link|img|iframe)[^>]+(?:src|href)="https?://', html), "ningún recurso externo se carga"
    script = (WAVES / "static/explore.js").read_text(encoding="utf-8")
    assert "innerHTML" not in script and "localStorage" not in script


def test_the_header_button_never_asks_a_signed_in_person_to_sign_in():
    script = (WAVES / "static/waves.js").read_text(encoding="utf-8")
    html = (WAVES / "static/index.html").read_text(encoding="utf-8")
    assert 'id="header-action"' in html and 'id="header-logout"' in html and 'id="hero-action"' in html
    assert '"Explorar archivo"' in script and '"Mi sesión"' in script and '"Acceder"' in script


# --- descargas del MiniSEED original -----------------------------------------------------------------------------


import hashlib  # noqa: E402

PAYLOAD = b"MINISEED-COMPLETO" * 5000
FAKE = {"id": "a" * 24, "name": "calibration/ml-evaluation-2026-10-03/waveforms/ev-1.mseed", "bytes": len(PAYLOAD),
        "sha256": hashlib.sha256(PAYLOAD).hexdigest(), "category": "calibration", "format": "MiniSEED"}


def downloads(monkeypatch, *, enabled=True, data=PAYLOAD, error=None):
    approved(monkeypatch)
    waves._downloads.clear()
    monkeypatch.setattr(waves, "index", lambda: {"records": [FAKE], "files": 1, "bytes": 1})
    if enabled:
        monkeypatch.setenv("WAVES_DOWNLOADS", "on")
    seen = []

    def fetch(name):
        seen.append(name)
        if error:
            raise error
        return data

    monkeypatch.setattr(waves, "archive_bytes", fetch)
    return seen


def test_downloads_are_off_until_they_are_switched_on(monkeypatch):
    seen = downloads(monkeypatch, enabled=False)

    assert client.get("/v1/waves/summary").json()["downloads_enabled"] is False
    assert client.get("/v1/waves/session", cookies=COOKIES).json()["downloads_enabled"] is False
    assert client.get(f"/v1/waves/records/{FAKE['id']}/download", cookies=COOKIES).status_code == 404
    assert seen == [], "con las descargas apagadas ni siquiera se toca el almacenamiento"


def test_an_approved_person_downloads_the_complete_original_file(monkeypatch):
    seen = downloads(monkeypatch)

    response = client.get(f"/v1/waves/records/{FAKE['id']}/download", cookies=COOKIES)

    assert response.status_code == 200 and response.content == PAYLOAD, "el archivo sale completo y sin tocar"
    assert response.headers["content-type"] == "application/vnd.fdsn.mseed"
    assert response.headers["content-disposition"] == 'attachment; filename="ev-1.mseed"'
    assert response.headers["x-waves-sha256"] == FAKE["sha256"] and response.headers["cache-control"] == "private, no-store"
    assert seen == [FAKE["name"]]
    assert client.get("/v1/waves/session", cookies=COOKIES).json()["downloads_enabled"] is True


def test_downloads_need_an_approved_session(monkeypatch):
    downloads(monkeypatch)
    url = f"/v1/waves/records/{FAKE['id']}/download"
    assert client.get(url).status_code == 401
    waves._sessions.clear()
    Api(monkeypatch, body={"uid": "u", "email": "otra@example.org", "name": "x"})
    assert client.get(url, cookies=COOKIES).status_code == 403
    waves._sessions.clear()
    approved(monkeypatch)
    for bad in ("0" * 24, "../../app", "ZZZ"):
        assert client.get(f"/v1/waves/records/{bad}/download", cookies=COOKIES).status_code == 404, bad


def test_a_file_that_does_not_match_the_catalog_is_never_delivered(monkeypatch):
    downloads(monkeypatch, data=PAYLOAD[:-1] + b"X")

    response = client.get(f"/v1/waves/records/{FAKE['id']}/download", cookies=COOKIES)

    assert response.status_code == 502 and b"MINISEED" not in response.content


def test_storage_failures_are_reported_without_internal_details(monkeypatch):
    downloads(monkeypatch, error=RuntimeError("gs://seismik-15bbb-scientific-archive/secreto 403"))

    response = client.get(f"/v1/waves/records/{FAKE['id']}/download", cookies=COOKIES)

    assert response.status_code == 503 and "gs://" not in response.text and "secreto" not in response.text


def test_downloads_are_rate_limited_per_person(monkeypatch):
    downloads(monkeypatch)
    url = f"/v1/waves/records/{FAKE['id']}/download"

    codes = [client.get(url, cookies=COOKIES).status_code for _ in range(waves.DOWNLOADS_PER_MINUTE + 3)]

    assert codes[:waves.DOWNLOADS_PER_MINUTE] == [200] * waves.DOWNLOADS_PER_MINUTE
    assert codes[waves.DOWNLOADS_PER_MINUTE:] == [429] * 3


def test_the_runtime_asks_for_the_archive_object_inside_the_import_prefix(monkeypatch):
    calls = []

    class Blob:
        size = 10

        def download_as_bytes(self, timeout):
            return b"x" * 10

    class Bucket:
        def get_blob(self, name, timeout):
            calls.append(name)
            return Blob()

    class Client:
        def bucket(self, name):
            calls.append(name)
            return Bucket()

    monkeypatch.setattr(waves, "archive_client", lambda: Client())

    assert waves.archive_bytes("calibration/x.mseed") == b"x" * 10
    assert calls == ["seismik-15bbb-scientific-archive", "imports/local-2026-10-10/data/calibration/x.mseed"]


# --- cierre de sesión ---------------------------------------------------------------------------------------


def test_logout_needs_the_waves_origin_and_ends_the_seismik_session(monkeypatch):
    api = Api(monkeypatch)
    monkeypatch.setenv("WAVES_PILOT_EMAILS", "support@seismik.org")
    client.get("/v1/waves/session", cookies=COOKIES)
    api.calls.clear()

    assert client.post("/v1/waves/logout", cookies=COOKIES).status_code == 403
    assert client.post("/v1/waves/logout", cookies=COOKIES, headers={"Origin": "https://evil.example"}).status_code == 403
    assert api.calls == []
    done = client.post("/v1/waves/logout", cookies=COOKIES, headers={"Origin": "https://waves.seismik.org"})

    assert done.status_code == 204
    assert api.calls == [("POST", "https://api.seismik.org/v1/oauth/logout", f"seismik_session={TOKEN}")]
    assert not waves._sessions, "la copia local de la sesión se descarta"


def test_logout_reports_when_the_session_could_not_be_closed(monkeypatch):
    Api(monkeypatch, error=httpx.ConnectError("x"))

    response = client.post("/v1/waves/logout", cookies=COOKIES, headers={"Origin": "https://waves.seismik.org"})

    assert response.status_code == 503


# --- sin Firebase y sin apariencia --------------------------------------------------------------------------


def test_no_firebase_login_remains_in_the_portal_or_the_backend():
    sources = {p.name: p.read_text(encoding="utf-8") for p in [WAVES / "app.py", WAVES / "requirements.txt", WAVES / "Dockerfile",
                                                                *(WAVES / "static").glob("*.[hjc]*")]}
    for name, text in sources.items():
        assert not re.search(r"firebase_admin|firebase-admin|firebasejs|firebase-app|firebaseapp|gstatic|apis\.google\.com|signInWith", text, re.I), name
    assert not (WAVES / "firebase-public.json").exists()
    assert client.get("/v1/waves/config").status_code == 404


def test_the_portal_sends_people_to_auth_seismik_org_and_has_no_appearance_selector():
    html = (WAVES / "static/index.html").read_text(encoding="utf-8")
    assert 'href="/login"' in html and "auth.seismik.org" in html
    assert 'type="password"' not in html and "id=\"google\"" not in html
    assert "theme-control" not in html and 'id="theme"' not in html


def test_the_portal_explains_what_waves_is():
    html = (WAVES / "static/index.html").read_text(encoding="utf-8")
    for needle in ("QUÉ ES WAVES", "MiniSEED", "SHA-256", "QUÉ HAY DENTRO", "ALCANCE DEL PILOTO", "PREGUNTAS FRECUENTES", "id=\"groups\""):
        assert needle in html, needle
    assert " style=" not in html, "la CSP no permite estilos en línea"


# --- cabeceras y rutas -----------------------------------------------------------------------------------------


def test_custom_404_and_no_file_exposure():
    for path in ['/no-such-route', '/catalog.json', '/firebase-public.json', '/app.py', '/assets/../app.py']:
        response = client.get(path)
        assert response.status_code == 404
    assert client.get('/v1/waves/no-such-route').json()["detail"] == 'Ruta no encontrada.'


def edge_csp() -> str:
    source = (WAVES / "edge/worker.js").read_text(encoding="utf-8")
    block = source[source.index("const CSP ="):source.index(";\n\nfunction hardened")]
    return "".join(re.findall(r'"([^"]*)"', block))  # las cadenas de la política no llevan comillas dobles ni escapes


def test_the_worker_and_the_backend_publish_the_same_csp():
    assert edge_csp() == waves.CSP
    assert client.get("/").headers["content-security-policy"] == waves.CSP


def test_csp_is_closed_to_third_parties_and_inline_code():
    csp = waves.CSP
    assert "script-src 'self';" in csp and "connect-src 'self';" in csp and "frame-src 'none';" in csp
    for forbidden in ("unsafe-inline", "unsafe-eval", "*", "google", "gstatic", "firebase"):
        assert forbidden not in csp, forbidden


def test_the_static_folder_published_by_the_worker_has_no_private_data():
    names = {p.name for p in (WAVES / "static").iterdir()}
    assert not names & {"catalog.json", "firebase-public.json", "app.py"}
    assert {n for n in names if n.endswith(".json")} == {"historical-earthquakes.json"}
    assert all(not n.endswith((".mseed", ".py", ".env")) for n in names)
