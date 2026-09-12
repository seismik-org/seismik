"""La API sólo atiende a quien llega por el Worker o trae el secreto de origen.

Cubre las tres piezas que deben ponerse de acuerdo: la guardia de la API, el
Worker que añade la cabecera y el reenviador de Pub/Sub, que llama a la API por
su URL directa de Cloud Run y por eso también tiene que enviarla.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import httpx
import pytest

from api.app import create_app
from api.config import AppSettings
from api.edge_origin import EDGE_ORIGIN_HEADER

SECRET = "edge-origin-secret-for-tests"
WORKER_COPIES = (Path("edge-worker/worker.js"), Path("deploy/cloudflare-edge-router.js"))


async def _get(settings: AppSettings, path: str, headers: dict[str, str] | None = None) -> httpx.Response:
    transport = httpx.ASGITransport(app=create_app(settings))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path, headers=headers or {})


# Una ruta inexistente responde 404 sólo si la petición atravesó la guardia, y
# no necesita Redis: distingue «rechazada en la puerta» de «llegó a la API».
PAST_THE_GUARD = "/health/does-not-exist"


@pytest.mark.asyncio
async def test_without_a_secret_the_guard_does_nothing() -> None:
    """Permite desplegar el código antes de repartir el secreto."""

    response = await _get(AppSettings(), PAST_THE_GUARD)

    assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("headers", [{}, {EDGE_ORIGIN_HEADER: "wrong"}, {EDGE_ORIGIN_HEADER: ""}])
async def test_requests_without_the_secret_are_rejected(headers: dict[str, str]) -> None:
    response = await _get(AppSettings(edge_origin_secret=SECRET), PAST_THE_GUARD, headers)

    assert response.status_code == 403
    assert response.json() == {"detail": "Origin not allowed"}


@pytest.mark.asyncio
async def test_requests_with_the_secret_reach_the_api() -> None:
    response = await _get(
        AppSettings(edge_origin_secret=SECRET),
        PAST_THE_GUARD,
        {"X-Seismik-Origin-Auth": SECRET},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_liveness_probe_does_not_need_the_secret() -> None:
    response = await _get(AppSettings(edge_origin_secret=SECRET), "/health/live")

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_readiness_is_not_exempt() -> None:
    """`/health/ready` toca Redis: no debe quedar abierto a cualquiera."""

    response = await _get(AppSettings(edge_origin_secret=SECRET), "/health/ready")

    assert response.status_code == 403


# --- Worker ------------------------------------------------------------------


def _worker(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def test_both_worker_copies_are_identical() -> None:
    """`wrangler.toml` de la raíz y `edge-worker/` apuntan a archivos distintos."""

    first, second = (_worker(path) for path in WORKER_COPIES)

    assert first == second, "edge-worker/worker.js y deploy/cloudflare-edge-router.js divergieron"


@pytest.mark.parametrize("path", WORKER_COPIES)
def test_worker_strips_client_header_and_sends_secret_only_to_the_api(path: Path) -> None:
    source = _worker(path)

    header = re.search(r'const ORIGIN_AUTH_HEADER = "([^"]+)";', source)
    assert header and header.group(1).lower() == EDGE_ORIGIN_HEADER

    delete_at = source.index("upstreamRequest.headers.delete(ORIGIN_AUTH_HEADER)")
    set_match = re.search(
        r"if \(target\.origin === API && env\?\.EDGE_ORIGIN_SECRET\) "
        r"upstreamRequest\.headers\.set\(ORIGIN_AUTH_HEADER, env\.EDGE_ORIGIN_SECRET\)",
        source,
    )
    assert set_match, "el secreto sólo debe añadirse cuando el destino es la API"
    assert delete_at < set_match.start(), "hay que borrar la cabecera del cliente antes"
    assert source.count("ORIGIN_AUTH_HEADER, env.EDGE_ORIGIN_SECRET") == 1
    assert "fetch(upstreamRequest)" in source


# --- Reenviador de Pub/Sub ----------------------------------------------------


class FakeMessage:
    def __init__(self, event_type: str = "earthquake_candidate") -> None:
        self.data = json.dumps({"event_type": event_type, "payload": {"event_id": "x"}}).encode()
        self.acked = False
        self.nacked = False

    def ack(self) -> None:
        self.acked = True

    def nack(self) -> None:
        self.nacked = True


class FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


@pytest.fixture
def forwarder():
    pytest.importorskip("google.cloud.pubsub_v1")
    from dispatcher import pubsub_forwarder

    return pubsub_forwarder


def test_forwarder_uses_the_same_header_name(forwarder) -> None:
    assert forwarder.EDGE_ORIGIN_HEADER.lower() == EDGE_ORIGIN_HEADER


def test_forwarder_sends_the_origin_secret_only_when_configured(forwarder) -> None:
    with_secret = forwarder.forward_headers("1", "sig", SECRET)
    without = forwarder.forward_headers("1", "sig", "")

    assert with_secret[forwarder.EDGE_ORIGIN_HEADER] == SECRET
    assert forwarder.EDGE_ORIGIN_HEADER not in without


@pytest.mark.parametrize("status", [401, 403, 408, 429, 500, 503])
def test_forwarder_retries_auth_and_transient_failures(forwarder, monkeypatch, status: int) -> None:
    """Un secreto desalineado se corrige en minutos; un sismo descartado no vuelve."""

    monkeypatch.setattr(forwarder.requests, "post", lambda *a, **k: FakeResponse(status))
    message = FakeMessage()

    forwarder._deliver(message, base_url="https://api.test", secret="hmac", edge_secret=SECRET)

    assert message.nacked and not message.acked


@pytest.mark.parametrize("status", [400, 404, 413, 422])
def test_forwarder_drops_events_the_api_calls_invalid(forwarder, monkeypatch, status: int) -> None:
    monkeypatch.setattr(forwarder.requests, "post", lambda *a, **k: FakeResponse(status))
    message = FakeMessage()

    forwarder._deliver(message, base_url="https://api.test", secret="hmac", edge_secret=SECRET)

    assert message.acked and not message.nacked


def test_forwarder_attaches_the_secret_to_the_real_request(forwarder, monkeypatch) -> None:
    captured: dict = {}

    def fake_post(url, **kwargs):
        captured.update(kwargs, url=url)
        return FakeResponse(202)

    monkeypatch.setattr(forwarder.requests, "post", fake_post)
    message = FakeMessage()

    forwarder._deliver(message, base_url="https://api.test/", secret="hmac", edge_secret=SECRET)

    assert message.acked
    assert captured["url"] == "https://api.test/v1/events/candidate"
    assert captured["headers"][forwarder.EDGE_ORIGIN_HEADER] == SECRET
