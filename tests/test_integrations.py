from __future__ import annotations

import hashlib
import hmac
import json

import httpx
import pytest
from fakeredis.aioredis import FakeRedis
from fastapi import FastAPI

from api import developer_keys, integrations
from api.config import AppSettings
from dispatcher.integrations import IntegrationConsumer


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
