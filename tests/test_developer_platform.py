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
