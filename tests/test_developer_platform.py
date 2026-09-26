from __future__ import annotations

import httpx
import pytest
from fakeredis.aioredis import FakeRedis
from fastapi import Depends, FastAPI

from api import developer_keys
from api.config import AppSettings
from api.dependencies import ApiPrincipal, require_events_read, require_stations_read


async def verified_identity(request, authorization):  # type: ignore[no-untyped-def]
    if authorization != "Bearer valid-token":
        raise AssertionError("test sent an unexpected identity token")
    return {"uid": "developer-1", "email": "dev@example.org", "email_verified": True}


def developer_app(monkeypatch: pytest.MonkeyPatch, **settings_overrides: object) -> FastAPI:
    monkeypatch.setattr(developer_keys, "_identity", verified_identity)
    app = FastAPI()
    app.state.redis = FakeRedis(decode_responses=True)
    settings_values: dict[str, object] = {
        "consumer_api_key": "internal-key",
        "developer_terms_version": "2026-08-30",
        **settings_overrides,
    }
    app.state.settings = AppSettings(**settings_values)
    app.include_router(developer_keys.router)

    @app.get("/events")
    async def events(_principal: ApiPrincipal = Depends(require_events_read)) -> dict[str, bool]:
        return {"ok": True}

    @app.get("/stations")
    async def stations(
        _principal: ApiPrincipal = Depends(require_stations_read),
    ) -> dict[str, bool]:
        return {"ok": True}

    return app


@pytest.mark.asyncio
async def test_data_routes_are_closed_when_static_key_is_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = developer_app(monkeypatch, consumer_api_key="")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        no_key = await client.get("/events")
        device_key = await client.get(
            "/events", headers={"X-Seismik-Device-Key": "development-device-key"}
        )
    assert no_key.status_code == 401
    assert device_key.status_code == 401


@pytest.mark.asyncio
async def test_key_lifecycle_stores_only_digest(monkeypatch: pytest.MonkeyPatch) -> None:
    app = developer_app(monkeypatch)
    headers = {"Authorization": "Bearer valid-token"}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        created = await client.post(
            "/v1/developer/keys",
            headers=headers,
            json={
                "name": "Laboratorio de prueba",
                "scopes": ["events:read"],
                "accepted_terms_version": "2026-08-30",
            },
        )
        assert created.status_code == 201
        secret = created.json()["key"]
        key_id = created.json()["key_id"]
        assert secret.startswith("sk_test_")

        listed = await client.get("/v1/developer/keys", headers=headers)
        assert listed.json()["active_count"] == 1
        assert listed.json()["keys"][0]["key_id"] == key_id
        assert "key" not in listed.json()["keys"][0]

        redis_keys = [
            item.decode() if isinstance(item, bytes) else item
            for item in await app.state.redis.keys("*")
        ]
        for redis_key in redis_keys:
            assert secret not in redis_key
            key_type = await app.state.redis.type(redis_key)
            if key_type == "string":
                value = await app.state.redis.get(redis_key)
                assert secret not in (value or "")
            elif key_type == "hash":
                values = await app.state.redis.hgetall(redis_key)
                assert all(secret not in value for value in values.values())

        allowed = await client.get("/events", headers={"X-Seismik-API-Key": secret})
        denied_scope = await client.get("/stations", headers={"X-Seismik-API-Key": secret})
        assert allowed.status_code == 200
        assert denied_scope.status_code == 403

        revoked = await client.delete(f"/v1/developer/keys/{key_id}", headers=headers)
        denied_revoked = await client.get("/events", headers={"X-Seismik-API-Key": secret})
        listed_after_revoke = await client.get("/v1/developer/keys", headers=headers)
        assert revoked.status_code == 204
        assert denied_revoked.status_code == 401
        assert listed_after_revoke.json() == {
            "keys": [],
            "active_count": 0,
            "active_limit": 3,
        }


@pytest.mark.asyncio
async def test_current_terms_and_active_key_limit_are_enforced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = developer_app(monkeypatch, developer_max_active_keys=1)
    headers = {"Authorization": "Bearer valid-token"}
    payload = {
        "name": "Investigación",
        "scopes": ["events:read"],
        "accepted_terms_version": "old",
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        stale = await client.post("/v1/developer/keys", headers=headers, json=payload)
        assert stale.status_code == 409
        payload["accepted_terms_version"] = "2026-08-30"
        first = await client.post("/v1/developer/keys", headers=headers, json=payload)
        second = await client.post("/v1/developer/keys", headers=headers, json=payload)
        assert first.status_code == 201
        assert second.status_code == 409


@pytest.mark.asyncio
async def test_free_plan_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    app = developer_app(monkeypatch, developer_free_requests_per_minute=2)
    headers = {"Authorization": "Bearer valid-token"}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        created = await client.post(
            "/v1/developer/keys",
            headers=headers,
            json={
                "name": "Rate limit",
                "scopes": ["events:read"],
                "accepted_terms_version": "2026-08-30",
            },
        )
        api_headers = {"X-Seismik-API-Key": created.json()["key"]}
        responses = [await client.get("/events", headers=api_headers) for _ in range(3)]
    assert [response.status_code for response in responses] == [200, 200, 429]
    assert responses[-1].headers["Retry-After"] == "60"


@pytest.mark.asyncio
async def test_usage_is_metered_without_enabling_payments(monkeypatch: pytest.MonkeyPatch) -> None:
    app = developer_app(monkeypatch)
    headers = {"Authorization": "Bearer valid-token"}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        created = await client.post(
            "/v1/developer/keys",
            headers=headers,
            json={
                "name": "Medición beta",
                "scopes": ["events:read"],
                "accepted_terms_version": "2026-08-30",
            },
        )
        api_headers = {"X-Seismik-API-Key": created.json()["key"]}
        assert (await client.get("/events", headers=api_headers)).status_code == 200
        summary = await client.get("/v1/developer/billing/summary", headers=headers)

    assert summary.status_code == 200
    assert summary.json()["requests"] == 1
    assert summary.json()["events_read"] == 1
    assert summary.json()["credit_balance_microunits"] == 0
    assert summary.json()["payments_enabled"] is False


@pytest.mark.asyncio
async def test_portal_publishes_prepaid_credit_catalog_without_enabling_checkout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = developer_app(monkeypatch)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/v1/developer/config")

    assert response.status_code == 200
    billing = response.json()["billing"]
    assert billing["currency"] == "USD"
    assert billing["model"] == "prepaid_credits"
    assert billing["checkout_enabled"] is False
    assert billing["promotional_credits_enabled"] is False
    assert billing["credit_packs"] == [
        {"id": "credits-5", "name": "Inicio", "usd_microunits": 5_000_000},
        {"id": "credits-25", "name": "Equipo", "usd_microunits": 25_000_000},
        {"id": "credits-100", "name": "Institución", "usd_microunits": 100_000_000},
    ]
    assert billing["request_prices"] == [
        {"id": "events-read", "name": "Eventos sísmicos", "scope": "events:read", "usd_microunits_per_request": 500},
        {"id": "stations-read", "name": "Red de estaciones", "scope": "stations:read", "usd_microunits_per_request": 1_000},
    ]


@pytest.mark.asyncio
async def test_turnstile_configuration_exposes_only_the_public_site_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = developer_app(
        monkeypatch,
        turnstile_site_key="0x-public-site-key",
        turnstile_secret_key="private-turnstile-secret",
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/v1/developer/config")

    assert response.status_code == 200
    assert response.json()["human_verification"] == {
        "enabled": True,
        "site_key": "0x-public-site-key",
        "action": "create_api_key",
    }
    assert "private-turnstile-secret" not in response.text


@pytest.mark.asyncio
async def test_turnstile_rejects_key_issuance_without_a_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = developer_app(
        monkeypatch,
        turnstile_site_key="0x-public-site-key",
        turnstile_secret_key="private-turnstile-secret",
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/developer/keys",
            headers={"Authorization": "Bearer valid-token"},
            json={
                "name": "Clave protegida",
                "scopes": ["events:read"],
                "accepted_terms_version": "2026-08-30",
            },
        )

    assert response.status_code == 403
    assert "verificación" in response.json()["detail"]


@pytest.mark.asyncio
async def test_turnstile_token_is_checked_before_issuing_a_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checked: list[str | None] = []

    async def verify_turnstile(_request, token):  # type: ignore[no-untyped-def]
        checked.append(token)

    monkeypatch.setattr(developer_keys, "_verify_turnstile", verify_turnstile)
    app = developer_app(
        monkeypatch,
        turnstile_site_key="0x-public-site-key",
        turnstile_secret_key="private-turnstile-secret",
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/developer/keys",
            headers={"Authorization": "Bearer valid-token"},
            json={
                "name": "Clave protegida",
                "scopes": ["events:read"],
                "accepted_terms_version": "2026-08-30",
                "turnstile_token": "valid-turnstile-token",
            },
        )

    assert response.status_code == 201
    assert checked == ["valid-turnstile-token"]


@pytest.mark.asyncio
async def test_rotation_revokes_previous_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    app = developer_app(monkeypatch)
    headers = {"Authorization": "Bearer valid-token"}
    payload = {
        "name": "Integración",
        "scopes": ["events:read"],
        "accepted_terms_version": "2026-08-30",
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        first = await client.post("/v1/developer/keys", headers=headers, json=payload)
        rotated = await client.post(
            f"/v1/developer/keys/{first.json()['key_id']}/rotate",
            headers=headers,
            json=payload,
        )
        old_access = await client.get(
            "/events", headers={"X-Seismik-API-Key": first.json()["key"]}
        )
        new_access = await client.get(
            "/events", headers={"X-Seismik-API-Key": rotated.json()["key"]}
        )
    assert rotated.status_code == 200
    assert old_access.status_code == 401
    assert new_access.status_code == 200


@pytest.mark.asyncio
async def test_key_creation_is_rate_limited_per_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El máximo de claves activas no frena el bucle de crear y revocar.

    Revocar libera un hueco al instante, así que sin este límite una cuenta
    puede emitir claves sin fin e inflar la bitácora de auditoría.
    """

    app = developer_app(
        monkeypatch, developer_max_active_keys=1, developer_key_creations_per_hour=3
    )
    headers = {"Authorization": "Bearer valid-token"}
    payload = {
        "name": "Investigación",
        "scopes": ["events:read"],
        "accepted_terms_version": "2026-08-30",
    }

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        statuses: list[int] = []
        for _ in range(4):
            created = await client.post("/v1/developer/keys", json=payload, headers=headers)
            statuses.append(created.status_code)
            if created.status_code == 201:
                key_id = created.json()["key_id"]
                await client.delete(f"/v1/developer/keys/{key_id}", headers=headers)

        assert statuses[:3] == [201, 201, 201]
        assert statuses[3] == 429
        assert (
            await client.post("/v1/developer/keys", json=payload, headers=headers)
        ).headers["Retry-After"] == "3600"


@pytest.mark.asyncio
async def test_rotating_a_key_also_counts_against_the_creation_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rotar emite una clave nueva: si no contara, el bucle seguiría abierto."""

    app = developer_app(monkeypatch, developer_key_creations_per_hour=2)
    headers = {"Authorization": "Bearer valid-token"}
    payload = {
        "name": "Investigación",
        "scopes": ["events:read"],
        "accepted_terms_version": "2026-08-30",
    }

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        created = await client.post("/v1/developer/keys", json=payload, headers=headers)
        assert created.status_code == 201
        key_id = created.json()["key_id"]

        first_rotation = await client.post(
            f"/v1/developer/keys/{key_id}/rotate", json=payload, headers=headers
        )
        assert first_rotation.status_code == 200

        replacement = first_rotation.json()["key_id"]
        blocked = await client.post(
            f"/v1/developer/keys/{replacement}/rotate", json=payload, headers=headers
        )
        assert blocked.status_code == 429
