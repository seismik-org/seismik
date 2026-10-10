from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from fakeredis.aioredis import FakeRedis

from api.config import AppSettings
from api.family_automatic import share_alert_locations
from api.schemas import DeviceTarget


def settings() -> AppSettings:
    return AppSettings(environment="production", push_enabled=True, push_mode="production",
                       integrity_verification_enabled=True,
                       webhook_hmac_secret="unit-test-hmac", crowd_master_secret="unit-test-crowd",
                       integration_webhook_master_secret="unit-test-integrations",
                       consumer_api_key="unit-test-consumer")


async def setup(redis: FakeRedis, *, consent: bool = True, age: int = 5) -> list[DeviceTarget]:
    await redis.set("seismik:device:account:phone", "person")
    await redis.set("seismik:family:account:person", "circle")
    await redis.sadd("seismik:family:members:circle", "person")
    if consent:
        await redis.set("seismik:family:auto-location:person", "1")
    await redis.hset("seismik:device:phone", mapping={
        "latitude": "4.65321", "longitude": "-74.08321",
        "updated_at": (datetime.now(timezone.utc) - timedelta(minutes=age)).isoformat(),
    })
    return [DeviceTarget(device_id="phone", platform="android", token="test-token")]


@pytest.mark.asyncio
async def test_automatic_location_is_approximate_expiring_deduplicated_and_not_safe() -> None:
    redis = FakeRedis(decode_responses=True)
    targets = await setup(redis)
    await redis.set("seismik:family:status:circle:person", "previous-status")
    event = {"event_id": "real-earthquake", "candidate_event_id": "candidate-1"}
    await share_alert_locations(redis, settings(), event, targets)
    await share_alert_locations(redis, settings(), event, targets)
    location = json.loads(await redis.get("seismik:family:location:circle:person"))
    assert location["latitude"] == 4.65
    assert location["longitude"] == -74.08
    assert location["related_event_id"] == "candidate-1"
    assert location["source"] == "automatic_alert"
    assert 0 < await redis.ttl("seismik:family:location:circle:person") <= 3600
    assert await redis.get("seismik:family:status:circle:person") == "previous-status"
    notices = await redis.xrange(settings().family_notification_stream)
    assert len(notices) == 1
    notification = json.loads(notices[0][1]["payload"])
    assert notification["status"] == "location_only"
    assert "latitude" not in notification


@pytest.mark.asyncio
@pytest.mark.parametrize("consent,age", [(False, 5), (True, 61), (True, -5)])
async def test_no_sharing_without_consent_or_recent_registration(consent: bool, age: int) -> None:
    redis = FakeRedis(decode_responses=True)
    targets = await setup(redis, consent=consent, age=age)
    await share_alert_locations(redis, settings(), {"event_id": "real-earthquake"}, targets)
    assert not await redis.exists("seismik:family:location:circle:person")


@pytest.mark.asyncio
@pytest.mark.parametrize("event", [{"event_id": "local-test"}, {"event_id": "quake", "simulation": True}, {}])
async def test_tests_and_missing_event_ids_never_share(event: dict[str, object]) -> None:
    redis = FakeRedis(decode_responses=True)
    targets = await setup(redis)
    await share_alert_locations(redis, settings(), event, targets)
    assert not await redis.exists("seismik:family:location:circle:person")


@pytest.mark.asyncio
async def test_unlinked_phone_and_revoked_preference_do_not_share() -> None:
    redis = FakeRedis(decode_responses=True)
    targets = await setup(redis)
    await redis.delete("seismik:device:account:phone")
    await share_alert_locations(redis, settings(), {"event_id": "quake"}, targets)
    assert not await redis.exists("seismik:family:location:circle:person")
