"""El dispatcher avisa a la familia cuando alguien reporta su estado."""
from __future__ import annotations

import json

import pytest
from fakeredis.aioredis import FakeRedis

from api.config import AppSettings
from api.schemas import DeviceTarget
from dispatcher.consumer import StreamConsumer
from dispatcher.push import PushResult, notification_content


class KnownDevices:
    def __init__(self, *device_ids: str) -> None:
        self.known = set(device_ids)

    async def resolve(self, device_id: str) -> DeviceTarget | None:
        if device_id not in self.known:
            return None
        return DeviceTarget(device_id=device_id, platform="android", token="t" * 64)

    async def unregister(self, _device_id: str) -> bool:
        return True


class RecordingPush:
    def __init__(self) -> None:
        self.calls: list[tuple[dict, list[str], bool]] = []

    async def send(self, event, targets, *, critical):
        ids = [target.device_id for target in targets]
        self.calls.append((event, ids, critical))
        return PushResult(attempted=len(ids), succeeded=len(ids))


def status_event(event_id: str = "family-1", status: str = "safe") -> dict:
    return {
        "type": "family_status",
        "event_id": event_id,
        "thread_id": "family",
        "circle_id": "casa",
        "member_id": "google-ana",
        "display_name": "Ana",
        "status": status,
        "message": None,
        "related_event_id": "official-1",
        "reported_at": "2026-09-12T20:00:00+00:00",
    }


async def family(redis: FakeRedis) -> None:
    await redis.sadd("seismik:family:members:casa", "google-ana", "google-luis", "device-abuela")
    await redis.sadd("seismik:account:devices:google-ana", "phone-ana")
    await redis.sadd("seismik:account:devices:google-luis", "phone-luis", "tablet-luis")


@pytest.mark.asyncio
async def test_every_other_member_device_is_notified_once() -> None:
    redis = FakeRedis(decode_responses=True)
    await family(redis)
    push = RecordingPush()
    consumer = StreamConsumer(
        redis,
        AppSettings(),
        KnownDevices("phone-ana", "phone-luis", "tablet-luis", "device-abuela"),  # type: ignore[arg-type]
        push,  # type: ignore[arg-type]
    )

    await consumer._handle_family_status(status_event())
    await consumer._handle_family_status(status_event())

    assert len(push.calls) == 1, "una reentrega del stream no repite el aviso"
    _event, targets, critical = push.calls[0]
    assert targets == ["device-abuela", "phone-luis", "tablet-luis"]
    assert "phone-ana" not in targets, "quien reporta no se avisa a sí mismo"
    assert critical is False


@pytest.mark.asyncio
async def test_the_family_stream_is_consumed_and_routed() -> None:
    redis = FakeRedis(decode_responses=True)
    await family(redis)
    settings = AppSettings()
    push = RecordingPush()
    consumer = StreamConsumer(redis, settings, KnownDevices("phone-luis"), push)  # type: ignore[arg-type]
    assert settings.family_notification_stream in consumer.streams

    await consumer.ensure_groups()
    message_id = await redis.xadd(
        settings.family_notification_stream, {"payload": json.dumps(status_event("family-2"))}
    )
    await consumer._handle(settings.family_notification_stream, message_id, {"payload": json.dumps(status_event("family-2"))})

    assert push.calls[0][1] == ["phone-luis"]


def test_the_notification_names_the_person_and_hides_internal_ids() -> None:
    title, body, data = notification_content(status_event(), critical=False)
    assert title == "Ana está bien"
    assert "a salvo" in body

    title, body, data = notification_content(status_event(status="need_help"), critical=False)
    assert title == "Ana necesita ayuda"
    assert set(data) == {"type", "event_id", "status", "display_name", "reported_at"}
    assert "google-ana" not in json.dumps(data)
    assert "casa" not in json.dumps(data)

    custom = {**status_event(status="need_help"), "message": "Estoy en el parque"}
    assert notification_content(custom, critical=False)[1] == "Estoy en el parque"
