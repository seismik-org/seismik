"""El formulario público de seismik.org no borra nada por sí solo: sólo deja
la solicitud en la bitácora, protegida de spam, para que el equipo la
verifique por el mismo canal que ya documenta la página."""

from __future__ import annotations

import json

import httpx
import pytest
from fakeredis.aioredis import FakeRedis
from fastapi import FastAPI

from api import account_deletion
from api.config import AppSettings


def deletion_app(**settings_overrides: object) -> FastAPI:
    app = FastAPI()
    app.state.redis = FakeRedis(decode_responses=True)
    app.state.settings = AppSettings(**settings_overrides)
    app.include_router(account_deletion.router)
    return app


@pytest.mark.asyncio
async def test_a_request_without_turnstile_configured_is_accepted() -> None:
    app = deletion_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/account/deletion-requests",
            json={"email": "persona@example.org", "scope": "full"},
        )

    assert response.status_code == 201
    body = response.json()
    assert body["request_id"].startswith("delreq_")

    raw = await app.state.redis.xrange("stream:seismik:account-deletion-requests")
    assert len(raw) == 1
    stored = json.loads(raw[0][1]["payload"])
    assert stored["email"] == "persona@example.org"
    assert stored["scope"] == "full"
    assert stored["request_id"] == body["request_id"]


@pytest.mark.asyncio
async def test_an_invalid_email_is_rejected_before_touching_redis() -> None:
    app = deletion_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/account/deletion-requests",
            json={"email": "no-es-un-correo", "scope": "full"},
        )

    assert response.status_code == 422
    assert await app.state.redis.xlen("stream:seismik:account-deletion-requests") == 0


@pytest.mark.asyncio
async def test_turnstile_configuration_exposes_only_the_public_site_key() -> None:
    app = deletion_app(
        turnstile_site_key="0x-public-site-key",
        turnstile_secret_key="private-turnstile-secret",
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/v1/account/deletion-config")

    assert response.status_code == 200
    assert response.json() == {
        "enabled": True,
        "site_key": "0x-public-site-key",
        "action": "delete_account_request",
    }
    assert "private-turnstile-secret" not in response.text


@pytest.mark.asyncio
async def test_turnstile_rejects_the_request_without_a_token() -> None:
    app = deletion_app(
        turnstile_site_key="0x-public-site-key",
        turnstile_secret_key="private-turnstile-secret",
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/account/deletion-requests",
            json={"email": "persona@example.org", "scope": "full"},
        )

    assert response.status_code == 403
    assert "verificación" in response.json()["detail"]


@pytest.mark.asyncio
async def test_turnstile_token_is_checked_before_storing_the_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checked: list[str | None] = []

    async def verify_turnstile(_request, token):  # type: ignore[no-untyped-def]
        checked.append(token)

    monkeypatch.setattr(account_deletion, "_verify_turnstile", verify_turnstile)
    app = deletion_app(
        turnstile_site_key="0x-public-site-key",
        turnstile_secret_key="private-turnstile-secret",
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/account/deletion-requests",
            json={
                "email": "persona@example.org",
                "scope": "partial",
                "details": "sólo mi ubicación compartida con la familia",
                "turnstile_token": "valid-turnstile-token",
            },
        )

    assert response.status_code == 201
    assert checked == ["valid-turnstile-token"]


@pytest.mark.asyncio
async def test_a_request_never_reveals_another_persons_account() -> None:
    """El correo lo escribe quien llena el formulario, sin iniciar sesión: la
    respuesta no puede insinuar si esa cuenta existe o no, o alguien podría
    usar el formulario para averiguar correos registrados."""

    app = deletion_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/account/deletion-requests",
            json={"email": "cualquiera@example.org", "scope": "full"},
        )

    assert response.status_code == 201
    assert "cuenta" not in response.json()["message"].lower() or "solicitud" in response.json()["message"].lower()


@pytest.mark.asyncio
async def test_requests_from_the_same_origin_are_throttled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = deletion_app(account_deletion_requests_per_hour=2)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        first = await client.post(
            "/v1/account/deletion-requests",
            json={"email": "a@example.org", "scope": "full"},
        )
        second = await client.post(
            "/v1/account/deletion-requests",
            json={"email": "b@example.org", "scope": "full"},
        )
        third = await client.post(
            "/v1/account/deletion-requests",
            json={"email": "c@example.org", "scope": "full"},
        )

    assert first.status_code == 201
    assert second.status_code == 201
    assert third.status_code == 429
