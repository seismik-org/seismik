from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fakeredis.aioredis import FakeRedis
from fastapi import FastAPI

from api.bus import RedisEventBus
from api.config import AppSettings
from api.dependencies import get_app_settings, get_bus, get_redis
from api.edge_origin import EdgeOriginGuard
from reporting.ingest import router


def payload() -> dict:
    return {
        "report_id": "browser-report-001",
        "earthquake_event_id": "catalog:test:event-001",
        "observed_at": "2026-10-07T15:00:00Z",
        "latitude": 4.651234,
        "longitude": -74.051234,
        "country_code": "CO",
        "location_accuracy_m": 8,
        "felt": True,
        "intensity_mmi": 4,
    }


def secure_settings(**kwargs):
    return AppSettings(
        integrity_verification_enabled=True,
        webhook_hmac_secret="test-webhook",
        crowd_master_secret="test-crowd",
        integration_webhook_master_secret="test-integration",
        consumer_api_key="test-key",
        **kwargs,
    )


async def setup(settings: AppSettings | None = None):
    settings = settings or AppSettings()
    redis = FakeRedis(decode_responses=True)
    await redis.xadd(settings.official_stream, {"payload": json.dumps({
        "event_id": "catalog:test:event-001",
        "preferred_report": {"official_event_id": "official-001",
            "origin_time": datetime.now(timezone.utc).isoformat(), "magnitude": 3.2,
            "latitude": 4.6, "longitude": -74.1, "place": "Colombia", "agency": "Test"},
    })})
    app = FastAPI()
    app.include_router(router)
    app.add_middleware(EdgeOriginGuard, secret=settings.edge_origin_secret.get_secret_value())
    app.dependency_overrides[get_app_settings] = lambda: settings
    app.dependency_overrides[get_redis] = lambda: redis
    app.dependency_overrides[get_bus] = lambda: RedisEventBus(redis, 100, 600)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://local")
    return client, redis, settings


@pytest.mark.asyncio
async def test_web_rounding_provenance_stream_and_retry():
    client, redis, settings = await setup()
    async with client:
        first = await client.post("/v1/reports/web/felt", json=payload())
        retry = await client.post("/v1/reports/web/felt", json=payload())
    assert first.status_code == retry.status_code == 202
    assert first.json()["accepted"]
    assert retry.json()["duplicate"]
    records = await redis.xrange(settings.felt_reports_stream)
    assert len(records) == 1
    stored = json.loads(records[0][1]["payload"])
    assert stored["source"] == "web"
    assert stored["device_id"] == "web-unverified"
    assert stored["integrity_verified"] is False
    assert stored["latitude"] == 4.65 and stored["longitude"] == -74.05
    assert stored["location_accuracy_m"] is None
    assert "turnstile_token" not in stored
    assert not await redis.keys("seismik:device:*")


@pytest.mark.asyncio
async def test_precise_opt_in_optional_details_and_official_forms():
    client, redis, settings = await setup()
    async with client:
        response = await client.post(
            "/v1/reports/web/felt",
            json=payload()
            | {
                "location_precision": "precise",
                "duration_seconds": 15,
                "movement": "rolling",
                "activity": "working",
                "building_type": "office",
                "building_height": 12,
                "reaction": "sheltered",
                "others_felt": "many",
                "noise": "loud",
                "windows": "rattled",
                "lamps": "swung",
                "furniture": "moved",
                "share_with_official_agencies": True,
            },
        )
    assert response.status_code == 202
    assert all(not route["automatic_submission"] for route in response.json()["agency_routes"])
    stored = json.loads((await redis.xrange(settings.felt_reports_stream))[0][1]["payload"])
    assert stored["latitude"] == 4.651234 and stored["location_accuracy_m"] == 8
    assert stored["duration_seconds"] == 15


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "extra",
    [
        {"source": "mobile"},
        {"device_id": "device-0001"},
        {"integrity_verified": True},
        {"name": "Name"},
        {"email": "user@example.org"},
        {"files": []},
        {"comment": "hello"},
        {"duration_seconds": -1},
        {"building_height": 201},
        {"movement": "invalid"},
    ],
)
async def test_browser_cannot_claim_mobile_identity_or_collect_personal_fields(extra):
    client, redis, settings = await setup()
    async with client:
        response = await client.post("/v1/reports/web/felt", json=payload() | extra)
    assert response.status_code == 422
    assert await redis.xlen(settings.felt_reports_stream) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "environment,site,secret",
    [
        ("production", "", ""),
        ("staging", "", ""),
        ("development", "site", ""),
        ("development", "", "secret"),
    ],
)
async def test_fail_closed_without_both_keys(environment, site, secret):
    client, _, _ = await setup(
        secure_settings(
            environment=environment, turnstile_site_key=site, turnstile_secret_key=secret
        )
    )
    async with client:
        config = await client.get("/v1/reports/web/config")
        response = await client.post("/v1/reports/web/felt", json=payload())
    assert not config.json()["enabled"]
    assert "secret" not in config.text
    assert response.status_code == 503


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action,hostname,success,expected",
    [
        ("felt_report", "ifeltit.seismik.org", True, 202),
        ("create_api_key", "ifeltit.seismik.org", True, 403),
        ("felt_report", "devs.seismik.org", True, 403),
        ("felt_report", "ifeltit.seismik.org", False, 403),
    ],
)
async def test_real_verification_action_hostname_and_token_redaction(
    monkeypatch, action, hostname, success, expected
):
    from reporting import web

    class Verifier:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, data):
            assert data == {"secret": "secret", "response": "sensitive-token"}
            return httpx.Response(
                200,
                request=httpx.Request("POST", url),
                json={"success": success, "action": action, "hostname": hostname},
            )

    client, redis, settings = await setup(
        secure_settings(
            environment="production", turnstile_site_key="site", turnstile_secret_key="secret"
        )
    )
    monkeypatch.setattr(web.httpx, "AsyncClient", Verifier)
    async with client:
        response = await client.post(
            "/v1/reports/web/felt", json=payload() | {"turnstile_token": "sensitive-token"}
        )
    assert response.status_code == expected
    records = await redis.xrange(settings.felt_reports_stream)
    assert "sensitive-token" not in str(records)
    assert "turnstile_token" not in str(records)


@pytest.mark.asyncio
async def test_rate_limit_hashes_trusted_edge_ip_and_ignores_spoofed_header():
    secret = "edge-secret"
    client, redis, _ = await setup(AppSettings(edge_origin_secret=secret, report_rate_limit_per_minute=1))
    async with client:
        blocked = await client.post(
            "/v1/reports/web/felt", json=payload(), headers={"X-Seismik-Client-IP": "1.2.3.4"}
        )
        assert blocked.status_code == 403
        headers = {"X-Seismik-Origin-Auth": secret, "X-Seismik-Client-IP": "1.2.3.4"}
        assert (
            await client.post("/v1/reports/web/felt", json=payload(), headers=headers)
        ).status_code == 202
        assert (
            await client.post("/v1/reports/web/felt", json=payload(), headers=headers)
        ).status_code == 429
    keys = await redis.keys("seismik:reports:web:rate:*")
    assert len(keys) == 1 and hashlib.sha256(b"1.2.3.4").hexdigest() in keys[0]
    assert "1.2.3.4" not in keys[0]
    client, redis, _ = await setup()
    async with client:
        await client.post(
            "/v1/reports/web/felt", json=payload(), headers={"X-Seismik-Client-IP": "1.2.3.4"}
        )
    keys = await redis.keys("seismik:reports:web:rate:*")
    assert hashlib.sha256(b"127.0.0.1").hexdigest() in keys[0]


@pytest.mark.asyncio
async def test_web_id_does_not_suppress_mobile_id():
    client, redis, settings = await setup()
    bus = RedisEventBus(redis, 100, 600)
    async with client:
        response = await client.post("/v1/reports/web/felt", json=payload())
    mobile = payload() | {"event_id": payload()["report_id"], "type": "seismik_felt_report"}
    assert response.status_code == 202
    assert (await bus.publish_once(settings.felt_reports_stream, mobile)).accepted


@pytest.mark.asyncio
async def test_missing_token_and_verifier_outage_never_publish(monkeypatch):
    from reporting import web

    client, redis, settings = await setup(
        secure_settings(
            environment="production", turnstile_site_key="site", turnstile_secret_key="secret"
        )
    )
    async with client:
        missing = await client.post("/v1/reports/web/felt", json=payload())
        assert missing.status_code == 403

        class UnavailableVerifier:
            def __init__(self, **kwargs):
                pass

            async def __aenter__(self):
                raise httpx.ConnectError("unavailable")

            async def __aexit__(self, *args):
                pass

        monkeypatch.setattr(web.httpx, "AsyncClient", UnavailableVerifier)
        outage = await client.post(
            "/v1/reports/web/felt", json=payload() | {"turnstile_token": "sensitive-token"}
        )
        assert outage.status_code == 503
    assert await redis.xlen(settings.felt_reports_stream) == 0


@pytest.mark.asyncio
async def test_selected_event_is_required_known_and_official_identity_is_bound():
    client, redis, settings = await setup()
    async with client:
        for changes in ({"earthquake_event_id": None}, {"earthquake_event_id": "invented"},
                        {"official_event_id": "other-event"}):
            response = await client.post("/v1/reports/web/felt", json=payload() | changes)
            assert response.status_code == 422
        missing = payload()
        del missing["earthquake_event_id"]
        assert (await client.post("/v1/reports/web/felt", json=missing)).status_code == 422
        assert await redis.xlen(settings.felt_reports_stream) == 0
        assert (await client.post("/v1/reports/web/felt", json=payload())).status_code == 202
    stored = json.loads((await redis.xrange(settings.felt_reports_stream))[0][1]["payload"])
    assert stored["earthquake_event_id"] == "catalog:test:event-001"
    assert stored["official_event_id"] == "official-001"


@pytest.mark.asyncio
async def test_catalog_deduplicates_revisions_filters_old_events_and_has_no_magnitude_floor():
    client, redis, settings = await setup()
    old = {"event_id": "old", "preferred_report": {
        "origin_time": (datetime.now(timezone.utc) - timedelta(days=8)).isoformat(),
        "magnitude": 5.0,
    }}
    await redis.xadd(settings.official_stream, {"payload": json.dumps(old)})
    await redis.xadd(settings.official_stream, {"payload": "malformed"})
    revision = {"event_id": "catalog:test:event-001", "preferred_report": {
        "origin_time": datetime.now(timezone.utc).isoformat(), "magnitude": 2.9,
        "place": "Revised", "official_event_id": "official-001",
    }}
    await redis.xadd(settings.official_stream, {"payload": json.dumps(revision)})
    async with client:
        response = await client.get("/v1/reports/web/events")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json()["period_days"] == 7
    assert len(response.json()["events"]) == 1
    assert response.json()["events"][0]["place"] == "Revised"
    assert response.json()["events"][0]["magnitude"] == 2.9


@pytest.mark.asyncio
async def test_catalog_deduplicates_official_ids_but_keeps_old_selection_valid_and_searches():
    client, redis, settings = await setup()
    await redis.xadd(settings.official_stream, {"payload": json.dumps({
        "event_id": "new-revision", "preferred_report": {
            "official_event_id": "official-001", "agency": "Test", "place": "Revised Colombia",
            "origin_time": datetime.now(timezone.utc).isoformat(), "magnitude": 3.4,
        },
    })})
    async with client:
        catalog = await client.get("/v1/reports/web/events?q=colombia")
        assert len(catalog.json()["events"]) == 1
        assert catalog.json()["events"][0]["event_id"] == "new-revision"
        assert (await client.get("/v1/reports/web/events?q=unknown")).json()["events"] == []
        assert (await client.post("/v1/reports/web/felt", json=payload())).status_code == 202
