from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fakeredis.aioredis import FakeRedis
from fastapi import FastAPI
from starlette.requests import Request

from api.admin import router as admin_router
from api.admin_security import COOKIE, MFA_PREFIX, SESSION_PREFIX, account, digest
from api.admin_security import router as security_router
from api.bus import RedisEventBus
from api.config import AppSettings
from api.dependencies import get_app_settings, get_bus, get_redis
from api.edge_origin import EdgeOriginGuard
from api.oauth import _finish_login
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
    return {"Cookie": f"{COOKIE}={token}", "Origin": "https://admin.seismik.org",
            "X-Seismik-Admin": "1", "X-Seismik-Admin-Approval": "test-approval"}


ADMIN = session("admin-token")


async def approve(redis, action):
    await redis.set("seismik:admin:approval:" + digest("test-approval"),
                    json.dumps({"session":digest("admin-token"), "action":action}), ex=120)



async def setup(admins: str = "admin@example.com", production: bool = False):
    settings = AppSettings(admin_emails=admins)
    if production:
        settings = settings.model_copy(update={"environment": "production"})
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
        await redis.set(SESSION_PREFIX + digest(token), json.dumps(
            {"uid": token, "email": email, "authenticated_at": str(int(time.time())), "last_seen": time.time(), "mfa_version": "test-version"}
        ))
    await redis.set(MFA_PREFIX + account({"uid":"admin-token"}), json.dumps({"version":"test-version"}))
    await redis.set("seismik:admin:approval:" + digest("test-approval"), json.dumps({"session":digest("admin-token"),"action":"control:alerts:false"}), ex=120)
    await redis.xadd(settings.developer_audit_stream, {"payload": json.dumps(
        {"action": "key_created", "email": "dev@example.com", "api_key": "sk_live_secret",
         "client_ip": "1.2.3.4", "nested": {"session_token": "abc"}}
    )})
    await redis.hset("seismik:device:device-1", mapping={"platform": "ios"})
    await redis.hset("seismik:developer-profile:dev-1", mapping={"plan": "free"})
    app = FastAPI()
    if production:
        app.add_middleware(EdgeOriginGuard, secret="test-edge-secret")
    app.include_router(router)
    app.include_router(admin_router)
    app.include_router(security_router)
    app.state.settings = settings
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
        await approve(redis, f"review:felt:{listed['stream_id']}:dismissed")
        dismissed = await client.post(url, json={"status": "dismissed"}, headers=ADMIN)
        assert dismissed.status_code == 200
        assert dismissed.json()["review"]["by"] == "admin@example.com"
        again = (await client.get("/v1/reports/admin/reports", headers=ADMIN)).json()["reports"]
        assert next(i for i in again if i["id"] == listed["id"])["review"]["status"] == "dismissed"
        await approve(redis, f"review:felt:{listed['stream_id']}:pending")
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
    audit = [json.loads(fields["payload"]) for _, fields in
             await redis.xrevrange(AppSettings().developer_audit_stream, count=2)]
    assert [entry["status"] for entry in audit] == ["pending", "dismissed"]
    assert all(entry["action"] == "report_review" and entry["by"] == "admin@example.com"
               for entry in audit)


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

@pytest.mark.asyncio
async def test_overview_counts_streams_and_accounts_for_admins_only() -> None:
    client, _ = await setup()
    async with client:
        assert (await client.get("/v1/admin/overview")).status_code == 401
        user = await client.get("/v1/admin/overview", headers=session("user-token"))
        assert user.status_code == 403
        assert (await client.get("/v1/admin/me", headers=ADMIN)).json() == {
            "email": "admin@example.com"
        }
        data = (await client.get("/v1/admin/overview", headers=ADMIN)).json()
    streams = {item["name"]: item for item in data["streams"]}
    assert streams["felt"]["total"] == 2 and streams["felt"]["last_24h"] == 2
    assert streams["official"]["total"] == 1
    assert streams["damage"]["total"] == 0 and streams["damage"]["last_at"] is None
    assert data["keys"]["devices"] == 1
    assert data["keys"]["developer_accounts"] == 1
    assert data["keys"]["admin_sessions"] == 2
    assert data["keys"]["web_sessions"] == 0
    assert data["keys_complete"] is True


@pytest.mark.asyncio
async def test_records_hide_secrets_and_reject_unknown_streams() -> None:
    client, _ = await setup()
    async with client:
        data = (await client.get("/v1/admin/records/developer_audit", headers=ADMIN)).json()
        unknown = await client.get("/v1/admin/records/oauth-sessions", headers=ADMIN)
        anonymous = await client.get("/v1/admin/records/felt")
    entry = data["records"][0]["data"]
    assert entry["email"] == "dev@example.com" and entry["action"] == "key_created"
    assert entry["api_key"] == entry["client_ip"] == entry["nested"]["session_token"] == "•••"
    assert unknown.status_code == 404
    assert anonymous.status_code == 401


def login_request(cookie: str = "") -> Request:
    app = FastAPI()
    app.state.settings = AppSettings()
    app.state.redis = FakeRedis(decode_responses=True)
    headers = [(b"cookie", cookie.encode())] if cookie else []
    return Request({"type": "http", "app": app, "headers": headers, "method": "GET",
                    "path": "/", "query_string": b""})


@pytest.mark.asyncio
async def test_login_returns_to_admin_only_with_the_fixed_marker() -> None:
    user = {"uid": "u-1", "email": "support@example.com", "name": "Support"}
    plain = await _finish_login(login_request(), user, None)
    assert plain.headers["location"] == "https://devs.seismik.org/"
    # A legacy/shared cookie cannot create an administrative session.
    admin = await _finish_login(login_request("seismik_after_login=admin"), user, None)
    assert admin.headers["location"] == "https://devs.seismik.org/"
    other = await _finish_login(login_request("seismik_after_login=https://evil.example"), user, None)
    assert other.headers["location"] == "https://devs.seismik.org/"


@pytest.mark.asyncio
async def test_admin_rejects_csrf_including_sibling_domains() -> None:
    client, redis = await setup()
    stream_id = (await redis.xrevrange(AppSettings().felt_reports_stream, count=1))[0][0]
    url = f"/v1/reports/admin/reports/felt/{stream_id}/review"
    async with client:
        for origin in (None, "https://evil.example", "https://devs.seismik.org"):
            headers = {"Cookie": f"{COOKIE}=admin-token", "X-Seismik-Admin": "1"}
            if origin:
                headers["Origin"] = origin
            assert (await client.post(url, json={"status": "valid"}, headers=headers)).status_code == 403
        headers = {k: v for k, v in ADMIN.items() if k != "X-Seismik-Admin"}
        assert (await client.post(url, json={"status": "valid"}, headers=headers)).status_code == 403
    assert await redis.hlen(REVIEW_KEY) == 0


@pytest.mark.asyncio
async def test_admin_requires_recent_valid_session_and_limits_queries() -> None:
    client, redis = await setup()
    key = SESSION_PREFIX + digest("admin-token")
    valid = await redis.get(key)
    async with client:
        for raw in ("{broken", json.dumps({"email": "admin@example.com"}),
                    json.dumps({"email": "admin@example.com", "authenticated_at": time.time() - 28801})):
            await redis.set(key, raw)
            assert (await client.get("/v1/admin/me", headers=ADMIN)).status_code == 401
        await redis.set(key, valid)
        for _ in range(120):
            response = await client.get("/v1/admin/me", headers=ADMIN)
            assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert (await client.get("/v1/admin/me", headers=ADMIN)).status_code == 429


@pytest.mark.asyncio
async def test_reports_redact_nested_credentials_too() -> None:
    client, redis = await setup()
    await redis.xadd(AppSettings().felt_reports_stream, {"payload": json.dumps(
        report(report_id="sensitive", authorization="Bearer private", nested={"clientIp": "1.2.3.4"})
    )})
    async with client:
        data = (await client.get("/v1/reports/admin/reports", headers=ADMIN)).json()
    item = next(item for item in data["reports"] if item["report"]["report_id"] == "sensitive")
    assert item["report"]["authorization"] == item["report"]["nested"]["clientIp"] == "•••"


@pytest.mark.asyncio
async def test_production_admin_requires_authenticated_edge_and_panel_host() -> None:
    client, _ = await setup(production=True)
    async with client:
        headers = {**ADMIN, "X-Seismik-Admin-Host": "admin.seismik.org"}
        assert (await client.get("/v1/admin/me", headers=headers)).status_code == 403
        headers["X-Seismik-Origin-Auth"] = "test-edge-secret"
        assert (await client.get("/v1/admin/me", headers=headers)).status_code == 200
        headers["X-Seismik-Admin-Host"] = "devs.seismik.org"
        assert (await client.get("/v1/admin/me", headers=headers)).status_code == 403
        del headers["X-Seismik-Admin-Host"]
        assert (await client.get("/v1/admin/me", headers=headers)).status_code == 403
