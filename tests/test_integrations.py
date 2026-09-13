from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from types import SimpleNamespace

import httpx
import pytest
from fakeredis.aioredis import FakeRedis
from fastapi import FastAPI

from api import developer_keys, integrations
from api.config import AppSettings
from dispatcher import integrations as integration_worker
from dispatcher.integrations import IntegrationConsumer, keep_running


async def verified_identity(request, authorization):  # type: ignore[no-untyped-def]
    return {"uid": "org-1", "email": "lab@example.org", "email_verified": True}


def integration_app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    monkeypatch.setattr(developer_keys, "_identity", verified_identity)
    async def public_endpoint(_url: str) -> bool:
        return True
    monkeypatch.setattr(integrations, "_is_safe_public_https", public_endpoint)
    app = FastAPI()
    app.state.redis = FakeRedis(decode_responses=True)
    app.state.settings = AppSettings(consumer_api_key="internal-key")
    app.include_router(integrations.router)
    return app


@pytest.mark.asyncio
async def test_webhook_secret_is_one_time_and_disable_is_owned(monkeypatch: pytest.MonkeyPatch) -> None:
    app = integration_app(monkeypatch)
    headers = {"Authorization": "Bearer identity"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test") as client:
        created = await client.post("/v1/developer/webhooks", headers=headers, json={
            "name": "Laboratorio universitario",
            "endpoint": "https://hooks.example.org/seismik",
            "event_types": ["official_report_update"],
        })
        listed = await client.get("/v1/developer/webhooks", headers=headers)
        disabled = await client.delete(
            f"/v1/developer/webhooks/{created.json()['webhook_id']}", headers=headers
        )
    assert created.status_code == 201
    assert created.json()["signing_secret"].startswith("swh_")
    assert "signing_secret" not in listed.json()["webhooks"][0]
    assert disabled.status_code == 204
    assert await app.state.redis.smembers("seismik:webhooks:active") == set()


@pytest.mark.asyncio
async def test_webhook_rejects_non_simulation_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    app = integration_app(monkeypatch)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test") as client:
        response = await client.post("/v1/developer/webhooks", headers={"Authorization": "Bearer identity"}, json={
            "name": "Control de gas",
            "endpoint": "https://hooks.example.org/seismik",
            "mode": "production",
        })
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_delivery_is_signed_and_explicitly_not_for_physical_control() -> None:
    redis = FakeRedis(decode_responses=True)
    settings = AppSettings(consumer_api_key="internal-key")
    secret = "swh_" + hmac.new(
        b"change-me-integration-secret", b"wh_1", hashlib.sha256
    ).hexdigest()
    await redis.sadd("seismik:webhooks:active", "wh_1")
    await redis.hset("seismik:webhook:wh_1", mapping={
        "webhook_id": "wh_1", "status": "active", "endpoint": "https://hook.example.org/receiver",
        "event_types": "official_report_update",
    })
    captured: dict[str, object] = {}
    async def receiver(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content
        captured["headers"] = dict(request.headers)
        return httpx.Response(204, request=request)
    client = httpx.AsyncClient(transport=httpx.MockTransport(receiver))
    consumer = IntegrationConsumer(redis, settings, client)
    event = {"event_id": "event-1", "type": "official_report_update", "status": "official_report_available"}
    await consumer._deliver_all(event, "1-0")
    body = captured["body"]
    headers = captured["headers"]
    assert isinstance(body, bytes)
    assert isinstance(headers, dict)
    payload = json.loads(body)
    assert payload["safety_mode"] == "simulation_only"
    assert "physical equipment" in payload["action_prohibited"]
    timestamp = str(headers["x-seismik-timestamp"])
    expected = hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    assert headers["x-seismik-signature"] == f"sha256={expected}"
    assert headers["x-seismik-safety-mode"] == "simulation_only"
    await client.aclose()


# --- Publicador de X en el mismo proceso ---------------------------------------


@pytest.mark.asyncio
async def test_a_failing_background_task_is_restarted_instead_of_propagating() -> None:
    calls = 0

    async def flaky() -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("X no responde")

    await asyncio.wait_for(keep_running("prueba", flaky, retry_seconds=0), timeout=1)

    assert calls == 2


@pytest.mark.asyncio
async def test_the_x_publisher_shares_the_process_and_cannot_stop_webhooks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Corre junto a los webhooks para aprovechar su CPU siempre asignada."""

    publisher_runs = 0
    publisher_cancelled = asyncio.Event()

    async def crashing_publisher(_self: object) -> None:
        nonlocal publisher_runs
        publisher_runs += 1
        if publisher_runs < 3:
            raise RuntimeError("X no responde")
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            publisher_cancelled.set()
            raise

    async def webhooks(_self: object) -> None:
        # La entrega de webhooks sigue viva mientras el publicador falla.
        while publisher_runs < 3:
            await asyncio.sleep(0.01)

    redis = FakeRedis(decode_responses=True)
    monkeypatch.setattr(integration_worker, "get_settings", AppSettings)
    monkeypatch.setattr(integration_worker.Redis, "from_url", lambda *_args, **_kwargs: redis)
    monkeypatch.setattr(
        integration_worker, "start_health_server", lambda: SimpleNamespace(shutdown=lambda: None)
    )
    monkeypatch.setattr(integration_worker, "X_PUBLISHER_RETRY_SECONDS", 0)
    monkeypatch.setattr(integration_worker.XPublisher, "run", crashing_publisher)
    monkeypatch.setattr(integration_worker.IntegrationConsumer, "run", webhooks)

    await asyncio.wait_for(integration_worker.run_integrations(), timeout=2)

    assert publisher_runs == 3
    assert publisher_cancelled.is_set(), "al cerrar el proceso la tarea no queda colgada"
