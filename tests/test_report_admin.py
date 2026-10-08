from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fakeredis.aioredis import FakeRedis
from fastapi import FastAPI

from api.bus import RedisEventBus
from api.config import AppSettings
from api.dependencies import get_app_settings, get_bus, get_redis
from reporting.admin import REVIEW_KEY
from reporting.ingest import router
from reporting.plausibility import assess

ORIGIN = datetime.now(timezone.utc) - timedelta(hours=1)
EVENT = {
    "event_id": "catalog:test:event-001",
    "origin_time": ORIGIN.isoformat(),
    "latitude": 4.6,
    "longitude": -74.1,
    "magnitude": 4.0,
    "depth_km": 10,
}


def report(**changes) -> dict:
    return {
        "earthquake_event_id": EVENT["event_id"],
        "observed_at": (ORIGIN + timedelta(minutes=1)).isoformat(),
        "latitude": 4.65,
        "longitude": -74.05,
        "felt": True,
        "intensity_mmi": 3,
        **changes,
    }


def test_nearby_report_is_plausible() -> None:
    result = assess(report(), EVENT)
    assert result["status"] == "plausible"
    assert result["distance_km"] is not None and result["distance_km"] < 10


def test_far_away_or_exaggerated_reports_are_flagged() -> None:
    far = assess(report(latitude=40.4, longitude=-3.7), EVENT)
    assert far["status"] == "implausible"
    assert "Demasiado lejos" in far["reasons"][0]
    violent = assess(report(latitude=6.2, longitude=-75.6, intensity_mmi=9), EVENT)
    assert violent["status"] == "implausible"
    assert any("Intensidad" in reason for reason in violent["reasons"])


def test_not_felt_far_away_is_still_coherent() -> None:
    assert assess(report(latitude=40.4, longitude=-3.7, felt=False), EVENT)["status"] == "plausible"


def test_missing_event_is_unknown() -> None:
    assert assess(report(earthquake_event_id=None), None)["status"] == "unknown"
    assert assess(report(), None)["reasons"] == ["El sismo ya no está en el catálogo reciente"]


def session(token: str) -> dict[str, str]:
    return {"Cookie": f"seismik_session={token}"}


ADMIN = session("admin-token")


async def setup(admins: str = "admin@example.com"):
    settings = AppSettings(report_admin_emails=admins)
    redis = FakeRedis(decode_responses=True)
    await redis.xadd(settings.official_stream, {"payload": json.dumps({
        "event_id": EVENT["event_id"],
        "preferred_report": {key: value for key, value in EVENT.items() if key != "event_id"},
    })})
    await redis.xadd(settings.felt_reports_stream, {"payload": json.dumps(
        report(report_id="app-1", device_id="device-secret", type="seismik_felt_report")
    )})
    await redis.xadd(settings.felt_reports_stream, {"payload": json.dumps(
        report(report_id="web-1", source="web", device_id="web-unverified",
               latitude=40.4, longitude=-3.7)
    )})
    for token, email in (("admin-token", "Admin@Example.com"), ("user-token", "user@example.com")):
        await redis.set(f"seismik:oauth:session:{token}", json.dumps({"uid": token, "email": email}))
    app = FastAPI()
    app.include_router(router)
    app.state.redis = redis
    app.dependency_overrides[get_app_settings] = lambda: settings
    app.dependency_overrides[get_redis] = lambda: redis
    app.dependency_overrides[get_bus] = lambda: RedisEventBus(redis, 100, 600)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://local")
    return client, redis


@pytest.mark.asyncio
async def test_only_configured_admins_can_list_reports() -> None:
    client, _ = await setup()
    async with client:
        assert (await client.get("/v1/reports/admin/reports")).status_code == 401
        user = await client.get("/v1/reports/admin/reports", headers=session("user-token"))
        assert user.status_code == 403
    client, _ = await setup(admins="")
    async with client:
        nobody = await client.get("/v1/reports/admin/reports", headers=session("admin-token"))
        assert nobody.status_code == 403


@pytest.mark.asyncio
async def test_admin_sees_app_and_web_reports_with_plausibility() -> None:
    client, _ = await setup()
    async with client:
        response = await client.get("/v1/reports/admin/reports", headers=ADMIN)
    assert response.status_code == 200
    reports = {item["report"]["report_id"]: item for item in response.json()["reports"]}
    assert reports["app-1"]["source"] == "app"
    assert reports["app-1"]["plausibility"]["status"] == "plausible"
    assert "device_id" not in reports["app-1"]["report"]
    assert reports["web-1"]["source"] == "web"
    assert reports["web-1"]["plausibility"]["status"] == "implausible"
    assert reports["web-1"]["event"]["magnitude"] == 4.0


@pytest.mark.asyncio
async def test_review_is_stored_without_touching_the_report() -> None:
    client, redis = await setup()
    async with client:
        listed = (await client.get("/v1/reports/admin/reports", headers=ADMIN)).json()["reports"][0]
        url = f"/v1/reports/admin/reports/felt/{listed['stream_id']}/review"
        dismissed = await client.post(url, json={"status": "dismissed"}, headers=ADMIN)
        assert dismissed.status_code == 200
        assert dismissed.json()["review"]["by"] == "admin@example.com"
        again = (await client.get("/v1/reports/admin/reports", headers=ADMIN)).json()["reports"]
        assert next(i for i in again if i["id"] == listed["id"])["review"]["status"] == "dismissed"
        pending = await client.post(url, json={"status": "pending"}, headers=ADMIN)
        assert pending.json()["review"] is None
        missing = await client.post(
            "/v1/reports/admin/reports/felt/1-0/review", json={"status": "valid"}, headers=ADMIN
        )
        assert missing.status_code == 404
        invalid = await client.post(url, json={"status": "deleted"}, headers=ADMIN)
        assert invalid.status_code == 422
    assert await redis.xlen(AppSettings().felt_reports_stream) == 2
    assert await redis.hlen(REVIEW_KEY) == 0


@pytest.mark.asyncio
async def test_web_ingest_stores_plausibility() -> None:
    settings = AppSettings()
    redis = FakeRedis(decode_responses=True)
    await redis.xadd(settings.official_stream, {"payload": json.dumps({
        "event_id": EVENT["event_id"],
        "preferred_report": {**{k: v for k, v in EVENT.items() if k != "event_id"},
                             "official_event_id": "official-001"},
    })})
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_app_settings] = lambda: settings
    app.dependency_overrides[get_redis] = lambda: redis
    app.dependency_overrides[get_bus] = lambda: RedisEventBus(redis, 100, 600)
    body = report(report_id="browser-plausibility", country_code="CO",
                  latitude=40.4, longitude=-3.7)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://local"
    ) as client:
        assert (await client.post("/v1/reports/web/felt", json=body)).status_code == 202
    stored = json.loads((await redis.xrange(settings.felt_reports_stream))[0][1]["payload"])
    assert stored["plausibility"]["status"] == "implausible"
