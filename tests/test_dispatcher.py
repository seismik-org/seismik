from __future__ import annotations

import json

import pytest
from fakeredis.aioredis import FakeRedis

from api.config import AppSettings
from api.schemas import DeviceTarget
from dispatcher.consumer import StreamConsumer
from dispatcher.push import (
    PushDispatcher,
    PushResult,
    apns_notification_id,
    collapse_key,
    notification_content,
)


class FakeDevices:
    def __init__(self) -> None:
        self.calls = []

    async def recipients(self, **kwargs):
        self.calls.append(kwargs)
        return [DeviceTarget(device_id="device-0001", platform="android", token="x" * 64)]

    async def unregister(self, _device_id: str) -> bool:
        return True


class FakePush:
    def __init__(self) -> None:
        self.calls = []

    async def send(self, event, targets, *, critical):
        self.calls.append((event, list(targets), critical))
        return PushResult(attempted=1, succeeded=1)


@pytest.mark.asyncio
async def test_candidate_routes_by_zone_and_official_reuses_mapping() -> None:
    redis = FakeRedis(decode_responses=True)
    settings = AppSettings(alert_cooldown_seconds=60)
    devices = FakeDevices()
    push = FakePush()
    consumer = StreamConsumer(redis, settings, devices, push)  # type: ignore[arg-type]
    candidate = {
        "event_id": "candidate-123", "type": "earthquake_candidate",
        "zone_id": "andes", "detected_at": "2026-01-01T00:00:00Z",
        "estimated_latitude": 4.65, "estimated_longitude": -74.05,
    }
    await consumer._handle_candidate(candidate)
    assert push.calls[0][2] is True
    mapping = json.loads(await redis.get("seismik:event-zone:candidate-123"))
    assert mapping["zone_id"] == "andes"

    official = {
        "event_id": "official-1", "candidate_event_id": "candidate-123",
        "type": "official_report_update",
        "preferred_report": {
            "agency": "SGC", "official_event_id": "SGC1", "origin_time": "2026-01-01T00:00:00Z",
            "latitude": 4.7, "longitude": -74.0, "magnitude": 4.2,
            "depth_km": 10, "official_url": "https://sgc.gov.co/event/1",
        },
    }
    await consumer._handle_official(official)
    assert push.calls[1][2] is False
    assert devices.calls[1]["zone_id"] == "andes"
    await consumer._handle_official(official)
    assert len(push.calls) == 2


def test_notification_payloads_distinguish_critical_and_official() -> None:
    title, body, data = notification_content(
        {"event_id": "c1", "type": "earthquake_candidate", "zone_id": "andes", "detected_at": "now"},
        critical=True,
    )
    assert title == "\u00a1ALERTA S\u00cdSMICA!"
    assert "C\u00fabrete" in body
    assert data["critical"] is True

    title, body, data = notification_content({
        "event_id": "o1", "candidate_event_id": "c1", "type": "official_report_update",
        "preferred_report": {
            "magnitude": 4.3, "depth_km": 12, "place": "Santander", "agency": "SGC",
            "latitude": 6.8, "longitude": -73.1, "official_url": "https://example.test",
        },
    }, critical=False)
    assert title == "Reporte s\u00edsmico oficial"
    assert "M 4.3" in body
    assert data["candidate_event_id"] == "c1"


def test_apns_headers_use_valid_bounded_identifiers() -> None:
    assert len(apns_notification_id("not-a-uuid")) == 36
    assert len(collapse_key("x" * 200).encode()) == 64


@pytest.mark.asyncio
async def test_dry_run_is_audited_without_claiming_push_success() -> None:
    redis = FakeRedis(decode_responses=True)
    settings = AppSettings(push_enabled=False, push_mode="dry_run")
    devices = FakeDevices()
    consumer = StreamConsumer(
        redis, settings, devices, PushDispatcher(settings)  # type: ignore[arg-type]
    )
    event = {
        "event_id": "candidate-audit",
        "type": "earthquake_candidate",
        "zone_id": "andes",
        "detected_at": "2026-01-01T00:00:00Z",
    }
    await consumer._handle_candidate(event)
    entries = await redis.xrevrange(settings.push_audit_stream, count=1)
    fields = entries[0][1]
    assert fields["test"] == "true"
    assert fields["critical"] == "true"
    assert fields["attempted"] == "1"
    assert json.loads(fields["target_device_ids"]) == ["device-0001"]
    assert "x" * 64 not in fields["payload"]


@pytest.mark.asyncio
async def test_poison_message_moves_to_dead_letter_after_bounded_retries() -> None:
    redis = FakeRedis(decode_responses=True)
    settings = AppSettings(max_delivery_attempts=2)
    consumer = StreamConsumer(
        redis, settings, FakeDevices(), FakePush()  # type: ignore[arg-type]
    )
    await consumer.ensure_groups()
    message_id = await redis.xadd(settings.candidate_stream, {"payload": "not-json"})
    messages = await redis.xreadgroup(
        settings.dispatcher_group,
        settings.consumer_name,
        {settings.candidate_stream: ">"},
        count=1,
    )
    fields = messages[0][1][0][1]
    await consumer._handle(settings.candidate_stream, message_id, fields)
    assert await redis.xlen(settings.dead_letter_stream) == 0
    await consumer._handle(settings.candidate_stream, message_id, fields)
    dead_letter = (await redis.xrevrange(settings.dead_letter_stream, count=1))[0][1]
    assert dead_letter["source_id"] == message_id
    assert dead_letter["attempts"] == "2"
    pending = await redis.xpending(settings.candidate_stream, settings.dispatcher_group)
    assert pending["pending"] == 0
