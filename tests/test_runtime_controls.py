from __future__ import annotations

import json

import pytest
from fakeredis.aioredis import FakeRedis
from test_dispatcher import FakeDevices, FakePush
from test_report_admin import ADMIN, setup
from test_x_publisher import official_event

from api.config import AppSettings
from api.runtime_controls import PAUSE_KEY, announce, paused, state
from dispatcher.consumer import StreamConsumer
from integrations.facebook_publisher import FacebookPublisher
from integrations.x_publisher import XPublisher


@pytest.mark.asyncio
async def test_admin_pause_is_durable_audited_and_requires_csrf() -> None:
    client, redis = await setup()
    await announce(redis, {"alerts": True, "x": True, "facebook": False})
    async with client:
        url = "/v1/admin/controls/alerts"
        public_headers = {key: value for key, value in ADMIN.items() if key != "Cookie"}
        assert (await client.put(url, headers=public_headers, json={"enabled": False})).status_code == 401
        assert (await client.put(url, headers={"Cookie": ADMIN["Cookie"]},
                                 json={"enabled": False})).status_code == 403
        response = await client.put(url, headers=ADMIN, json={"enabled": False})
        assert response.status_code == 200
        assert await paused(redis, "alerts")
        assert await redis.ttl(PAUSE_KEY) == -1
        await announce(redis, {"alerts": True})  # A restart must not clear a pause.
        assert await paused(redis, "alerts")
        audit = await redis.xrevrange(AppSettings().developer_audit_stream, count=1)
        assert audit[0][1]["action"] == "operation.paused"
        assert audit[0][1]["by"] == "admin@example.com"
        assert (await client.put(url, headers=ADMIN, json={"enabled": True})).status_code == 200
        assert not await paused(redis, "alerts")


@pytest.mark.asyncio
async def test_controls_cannot_enable_an_unconfigured_or_disconnected_worker() -> None:
    client, redis = await setup()
    async with client:
        url = "/v1/admin/controls/facebook"
        assert (await client.put(url, headers=ADMIN, json={"enabled": True})).status_code == 409
        await announce(redis, {"facebook": False})
        assert (await client.put(url, headers=ADMIN, json={"enabled": True})).status_code == 409
        assert (await client.put(url, headers=ADMIN, json={"enabled": "false"})).status_code == 422
        assert (await client.put(url, headers=ADMIN, json={"enabled": False, "secret": "x"})).status_code == 422
        assert (await client.put("/v1/admin/controls/unknown", headers=ADMIN,
                                 json={"enabled": False})).status_code == 404
        assert (await client.put(url, headers=ADMIN, json={"enabled": False})).status_code == 200


@pytest.mark.asyncio
async def test_worker_heartbeat_expiry_does_not_claim_function_is_active() -> None:
    redis = FakeRedis(decode_responses=True)
    await announce(redis, {"x": True})
    assert next(item for item in await state(redis) if item["id"] == "x")["enabled"]
    await redis.delete("seismik:operations:worker:x")
    x = next(item for item in await state(redis) if item["id"] == "x")
    assert not x["enabled"] and not x["worker_available"]


@pytest.mark.asyncio
@pytest.mark.parametrize("publisher_type", [XPublisher, FacebookPublisher])
async def test_paused_publisher_never_renders_or_sends(publisher_type, monkeypatch) -> None:
    redis = FakeRedis(decode_responses=True)
    publisher = publisher_type(redis, AppSettings())
    await redis.hset(PAUSE_KEY, publisher.namespace, "1")

    async def forbidden(_event):
        pytest.fail("A paused publisher must not start a delivery")

    monkeypatch.setattr(publisher, "_render_card", forbidden)
    await publisher._publish({"event_id": "test-event"}, "test-key")
    audit = await redis.xrange(f"stream:seismik:{publisher.namespace}-audit")
    assert audit[-1][1]["action"] == "skipped_paused"


@pytest.mark.asyncio
async def test_alert_switch_blocks_push_and_can_resume_without_a_restart() -> None:
    redis = FakeRedis(decode_responses=True)
    push = FakePush()
    consumer = StreamConsumer(redis, AppSettings(), FakeDevices(), push)  # type: ignore[arg-type]
    event = {"event_id": "test-alert"}
    await redis.hset(PAUSE_KEY, "alerts", "1")
    result = await consumer._send_earthquake(event, [], critical=True)
    assert result.attempted == 0 and not push.calls
    await redis.hset(PAUSE_KEY, "alerts", "0")
    await consumer._send_earthquake(event, [], critical=True)
    assert len(push.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("publisher_type", [XPublisher, FacebookPublisher])
async def test_pause_during_image_render_is_checked_again_before_delivery(publisher_type, monkeypatch) -> None:
    redis = FakeRedis(decode_responses=True)
    publisher = publisher_type(redis, AppSettings())

    async def card(_event):
        await redis.hset(PAUSE_KEY, publisher.namespace, "1")
        return b"test-image"

    monkeypatch.setattr(publisher, "_render_card", card)
    await publisher._publish(official_event(), "test-key")
    audit = await redis.xrange(f"stream:seismik:{publisher.namespace}-audit")
    assert audit[-1][1]["action"] == "skipped_paused"


@pytest.mark.asyncio
async def test_real_publication_stream_and_nonfinite_legacy_records_are_readable() -> None:
    client, redis = await setup()
    await redis.xadd("stream:seismik:x-audit", {"action": "published", "post_id": "123"})
    await redis.xadd(AppSettings().candidate_stream, {"payload": json.dumps({"magnitude": float("nan")})})
    async with client:
        response = await client.get("/v1/admin/records/x_publisher", headers=ADMIN)
        assert response.json()["records"][0]["data"]["post_id"] == "123"
        response = await client.get("/v1/admin/records/candidates", headers=ADMIN)
        assert response.status_code == 200
        assert response.json()["records"][0]["data"]["magnitude"] is None
