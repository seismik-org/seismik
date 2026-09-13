from __future__ import annotations

import json

import httpx
import pytest
from fakeredis.aioredis import FakeRedis
from fastapi import FastAPI

from api.config import AppSettings
from api.device_sessions import DeviceSessionRepository
from api.family import account_router, router


def app_for(redis: FakeRedis) -> FastAPI:
    app = FastAPI()
    app.state.redis = redis
    app.state.settings = AppSettings()
    app.include_router(router)
    app.include_router(account_router)
    return app


async def account(redis: FakeRedis, uid: str, name: str = "") -> dict[str, str]:
    token = f"account-session-{uid}-" + "x" * 40
    await redis.set(
        f"seismik:oauth:mobile-session:{token}",
        json.dumps({"uid": uid, "email": f"{uid}@example.test", "name": name}),
        ex=3600,
    )
    return {"X-Seismik-Account-Session": token}


async def device(redis: FakeRedis, device_id: str) -> dict[str, str]:
    token = await DeviceSessionRepository(redis, ttl_seconds=3600).issue(device_id)
    return {"X-Seismik-Device-Session": token}


def client_for(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test")


async def family_with_member(client: httpx.AsyncClient, redis: FakeRedis) -> tuple[dict[str, str], dict[str, str]]:
    owner = await account(redis, "google-owner", "Óscar")
    member = await account(redis, "google-ana", "Ana")
    created = await client.post("/v1/family/circle", headers=owner, json={"display_name": "Óscar"})
    assert created.status_code == 201
    invitation = await client.post("/v1/family/circle/invitations", headers=owner, json={"display_name": "Ana"})
    assert invitation.status_code == 201
    joined = await client.post(
        "/v1/family/join",
        headers=member,
        json={"invite_code": invitation.json()["invite_code"], "display_name": "Ana"},
    )
    assert joined.status_code == 200
    return owner, member


@pytest.mark.asyncio
async def test_family_requires_a_signed_in_account() -> None:
    redis = FakeRedis(decode_responses=True)
    phone_only = await device(redis, "device-sin-cuenta")
    async with client_for(app_for(redis)) as client:
        created = await client.post("/v1/family/circle", headers=phone_only, json={"display_name": "Óscar"})
        circle = await client.get("/v1/family/circle", headers=phone_only)
        expired = await client.get("/v1/family/circle", headers={"X-Seismik-Account-Session": "vencida"})

    assert created.status_code == 401
    assert circle.status_code == 401
    assert expired.status_code == 401


@pytest.mark.asyncio
async def test_family_circle_requires_invitation_and_expires_shared_location() -> None:
    redis = FakeRedis(decode_responses=True)
    async with client_for(app_for(redis)) as client:
        owner, member = await family_with_member(client, redis)
        shared = await client.put(
            "/v1/family/location", headers=member, json={"latitude": 4.65321, "longitude": -74.08321, "share_minutes": 15}
        )
        assert shared.status_code == 200
        circle = await client.get("/v1/family/circle", headers=owner)
        ana = next(item for item in circle.json()["members"] if item["display_name"] == "Ana")
        assert ana["location"]["latitude"] == 4.65
        assert ana["location"]["precision"] == "approximate"
        assert ana["is_you"] is False
        assert "google-ana" not in json.dumps(circle.json()), "no se expone el id de la cuenta"
        stopped = await client.delete("/v1/family/location", headers=member)
        assert stopped.status_code == 204
        circle = await client.get("/v1/family/circle", headers=owner)
        ana = next(item for item in circle.json()["members"] if item["display_name"] == "Ana")
        assert ana["location"] is None


@pytest.mark.asyncio
async def test_only_the_circle_owner_can_invite() -> None:
    redis = FakeRedis(decode_responses=True)
    async with client_for(app_for(redis)) as client:
        _owner, member = await family_with_member(client, redis)
        response = await client.post("/v1/family/circle/invitations", headers=member, json={"display_name": "Luis"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_precise_location_requires_explicit_consent() -> None:
    redis = FakeRedis(decode_responses=True)
    owner = await account(redis, "google-owner")
    async with client_for(app_for(redis)) as client:
        await client.post("/v1/family/circle", headers=owner, json={"display_name": "Óscar"})
        response = await client.put(
            "/v1/family/location", headers=owner, json={"latitude": 4.65, "longitude": -74.08, "precision": "precise"}
        )
        status_report = await client.put(
            "/v1/family/status",
            headers=owner,
            json={"status": "safe", "location": {"latitude": 4.65, "longitude": -74.08, "precision": "precise"}},
        )
    assert response.status_code == 422
    assert status_report.status_code == 422


@pytest.mark.asyncio
async def test_status_report_shares_location_and_notifies_the_family_once() -> None:
    redis = FakeRedis(decode_responses=True)
    settings = AppSettings()
    async with client_for(app_for(redis)) as client:
        owner, member = await family_with_member(client, redis)
        report = {
            "status": "safe",
            "event_id": "official-sgc-2026",
            "location": {"latitude": 4.65321, "longitude": -74.08321},
        }
        first = await client.put("/v1/family/status", headers=member, json=report)
        repeated = await client.put("/v1/family/status", headers=member, json=report)
        circle = await client.get("/v1/family/circle", headers=owner)
        help_needed = await client.put(
            "/v1/family/status", headers=member, json={"status": "need_help", "message": "Estoy en el parque"}
        )

    assert first.status_code == 200
    assert first.json()["notified"] is True
    assert first.json()["sharing_location"] is True
    assert repeated.json()["notified"] is False, "tocar dos veces no avisa dos veces"
    assert help_needed.json()["notified"] is True, "pedir ayuda avisa de inmediato"

    ana = next(item for item in circle.json()["members"] if item["display_name"] == "Ana")
    assert ana["status"]["status"] == "safe"
    assert ana["status"]["event_id"] == "official-sgc-2026"
    assert ana["location"]["latitude"] == 4.65

    entries = await redis.xrange(settings.family_notification_stream)
    assert len(entries) == 2
    notification = json.loads(entries[0][1]["payload"])
    assert notification["type"] == "family_status"
    assert notification["display_name"] == "Ana"
    assert notification["member_id"] == "google-ana"
    assert "@example.test" not in entries[0][1]["payload"], "el correo nunca viaja en el aviso"
    assert json.loads(entries[1][1]["payload"])["status"] == "need_help"


@pytest.mark.asyncio
async def test_status_without_location_does_not_share_it() -> None:
    redis = FakeRedis(decode_responses=True)
    async with client_for(app_for(redis)) as client:
        owner, member = await family_with_member(client, redis)
        response = await client.put("/v1/family/status", headers=member, json={"status": "safe"})
        circle = await client.get("/v1/family/circle", headers=owner)

    assert response.json()["sharing_location"] is False
    ana = next(item for item in circle.json()["members"] if item["display_name"] == "Ana")
    assert ana["status"]["status"] == "safe"
    assert ana["location"] is None


@pytest.mark.asyncio
async def test_signing_in_moves_the_phone_circle_to_the_account() -> None:
    redis = FakeRedis(decode_responses=True)
    # Círculo creado por la versión anterior, ligado a teléfonos.
    await redis.hset(
        "seismik:family:circle:legacy-circle",
        mapping={"circle_id": "legacy-circle", "circle_name": "Casa", "owner_device_id": "device-owner"},
    )
    await redis.sadd("seismik:family:members:legacy-circle", "device-owner", "device-abuela")
    await redis.hset("seismik:family:member:legacy-circle:device-owner", mapping={"display_name": "Óscar"})
    await redis.hset("seismik:family:member:legacy-circle:device-abuela", mapping={"display_name": "Abuela"})
    await redis.set("seismik:family:device:device-owner", "legacy-circle")
    await redis.set("seismik:family:device:device-abuela", "legacy-circle")
    await redis.set(
        "seismik:family:location:legacy-circle:device-owner",
        json.dumps({"latitude": 4.6, "longitude": -74.1, "precision": "approximate"}),
        ex=900,
    )
    owner_account = await account(redis, "google-owner", "Óscar")
    headers = {**owner_account, **await device(redis, "device-owner")}

    async with client_for(app_for(redis)) as client:
        linked = await client.post("/v1/account/device", headers=headers)
        circle = await client.get("/v1/family/circle", headers=owner_account)
        invitation = await client.post(
            "/v1/family/circle/invitations", headers=owner_account, json={"display_name": "Luis"}
        )

    assert linked.json() == {"linked": True, "migrated_circle": True}
    body = circle.json()
    assert body["circle_name"] == "Casa"
    assert body["is_owner"] is True
    you = next(item for item in body["members"] if item["is_you"])
    assert you["display_name"] == "Óscar"
    assert you["location"]["latitude"] == 4.6
    assert {item["display_name"] for item in body["members"]} == {"Óscar", "Abuela"}
    assert invitation.status_code == 201, "la propiedad del círculo pasó a la cuenta"
    assert await redis.smembers("seismik:account:devices:google-owner") == {"device-owner"}
    assert await redis.get("seismik:family:device:device-owner") is None


@pytest.mark.asyncio
async def test_an_account_in_a_circle_does_not_absorb_another_family() -> None:
    redis = FakeRedis(decode_responses=True)
    await redis.hset("seismik:family:circle:old", mapping={"circle_id": "old", "circle_name": "Antiguo"})
    await redis.sadd("seismik:family:members:old", "device-shared")
    await redis.set("seismik:family:device:device-shared", "old")
    person = await account(redis, "google-owner")

    async with client_for(app_for(redis)) as client:
        await client.post("/v1/family/circle", headers=person, json={"display_name": "Óscar"})
        linked = await client.post(
            "/v1/account/device", headers={**person, **await device(redis, "device-shared")}
        )
        circle = await client.get("/v1/family/circle", headers=person)

    assert linked.json()["migrated_circle"] is False
    assert circle.json()["circle_name"] == "Mi círculo"
    assert await redis.smembers("seismik:family:members:old") == set()


@pytest.mark.asyncio
async def test_signing_out_stops_family_notifications_on_that_phone() -> None:
    redis = FakeRedis(decode_responses=True)
    person = await account(redis, "google-owner")
    headers = {**person, **await device(redis, "device-owner")}
    async with client_for(app_for(redis)) as client:
        await client.post("/v1/account/device", headers=headers)
        removed = await client.delete("/v1/account/device", headers=headers)

    assert removed.status_code == 204
    assert await redis.smembers("seismik:account:devices:google-owner") == set()


def test_verified_ios_installation_can_create_session_before_apns_token() -> None:
    """La sesión segura no depende de que APNs ya haya respondido."""
    from api.schemas import DeviceRegistration

    registration = DeviceRegistration(
        device_id="ios-family-session",
        platform="ios",
        country_code="CO",
        zone_id="global",
        app_attest_token="verified-app-check-token",
    )
    assert registration.token == ""
