from __future__ import annotations

import httpx
import pytest
from fakeredis.aioredis import FakeRedis
from fastapi import FastAPI

from api.config import AppSettings
from api.device_sessions import DeviceSessionRepository
from api.family import router


def app_for(redis: FakeRedis) -> FastAPI:
    app = FastAPI()
    app.state.redis = redis
    app.state.settings = AppSettings()
    app.include_router(router)
    return app


async def headers(redis: FakeRedis, device_id: str) -> dict[str, str]:
    token = await DeviceSessionRepository(redis, ttl_seconds=3600).issue(device_id)
    return {"X-Seismik-Device-Session": token}


@pytest.mark.asyncio
async def test_family_circle_requires_invitation_and_expires_shared_location() -> None:
    redis = FakeRedis(decode_responses=True)
    app = app_for(redis)
    transport = httpx.ASGITransport(app=app)
    owner_headers = await headers(redis, "device-owner")
    member_headers = await headers(redis, "device-member")
    async with httpx.AsyncClient(transport=transport, base_url="https://test") as client:
        created = await client.post("/v1/family/circle", headers=owner_headers, json={"display_name": "Óscar"})
        assert created.status_code == 201
        invitation = await client.post("/v1/family/circle/invitations", headers=owner_headers, json={"display_name": "Ana"})
        assert invitation.status_code == 201
        joined = await client.post("/v1/family/join", headers=member_headers, json={"invite_code": invitation.json()["invite_code"], "display_name": "Ana"})
        assert joined.status_code == 200
        shared = await client.put("/v1/family/location", headers=member_headers, json={"latitude": 4.65321, "longitude": -74.08321, "share_minutes": 15})
        assert shared.status_code == 200
        circle = await client.get("/v1/family/circle", headers=owner_headers)
        ana = next(item for item in circle.json()["members"] if item["display_name"] == "Ana")
        assert ana["location"]["latitude"] == 4.65
        assert ana["location"]["precision"] == "approximate"
        stopped = await client.delete("/v1/family/location", headers=member_headers)
        assert stopped.status_code == 204
        circle = await client.get("/v1/family/circle", headers=owner_headers)
        ana = next(item for item in circle.json()["members"] if item["display_name"] == "Ana")
        assert ana["location"] is None


@pytest.mark.asyncio
async def test_precise_location_requires_explicit_consent() -> None:
    redis = FakeRedis(decode_responses=True)
    app = app_for(redis)
    transport = httpx.ASGITransport(app=app)
    owner_headers = await headers(redis, "device-owner")
    async with httpx.AsyncClient(transport=transport, base_url="https://test") as client:
        await client.post("/v1/family/circle", headers=owner_headers, json={"display_name": "Óscar"})
        response = await client.put("/v1/family/location", headers=owner_headers, json={"latitude": 4.65, "longitude": -74.08, "precision": "precise"})
    assert response.status_code == 422
