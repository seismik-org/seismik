from __future__ import annotations

import json
import time
from pathlib import Path

import httpx
import numpy as np
import pytest
from fakeredis.aioredis import FakeRedis
from fastapi import FastAPI
from obspy import Stream, Trace, UTCDateTime

from api.bus import RedisEventBus
from api.config import AppSettings
from api.dependencies import get_bus
from api.devices_store import DeviceRepository
from api.schemas import DeviceRegistration
from api.security import create_signature
from api.webhooks import router
from dispatcher.consumer import StreamConsumer
from dispatcher.push import PushDispatcher
from eew.config import CoincidenceSettings, DetectionSettings, StationSubscription
from eew.replay import MiniSeedReplay


def write_impulse_case(path: Path) -> tuple[StationSubscription, ...]:
    traces = []
    subscriptions = []
    for index, station in enumerate(("ONE", "TWO", "THREE")):
        data = np.random.default_rng(index).normal(0, 0.01, 1_200)
        data[800:830] += 8
        trace = Trace(data=data.astype(np.float32))
        trace.stats.network = "XX"
        trace.stats.station = station
        trace.stats.location = ""
        trace.stats.channel = "HHZ"
        trace.stats.sampling_rate = 100.0
        trace.stats.starttime = UTCDateTime("2026-01-01T00:00:00Z")
        traces.append(trace)
        subscriptions.append(
            StationSubscription(
                "XX",
                station,
                "HHZ",
                country_code="CO",
                zone_id="CO",
                latitude=4.0 + index,
                longitude=-74.0 - index,
            )
        )
    Stream(traces).write(path, format="MSEED")
    return tuple(subscriptions)


@pytest.mark.asyncio
async def test_replay_webhook_stream_consumer_produces_test_payload(tmp_path: Path) -> None:
    case_path = tmp_path / "e2e.mseed"
    subscriptions = write_impulse_case(case_path)
    replay = MiniSeedReplay(
        subscriptions,
        DetectionSettings(
            buffer_seconds=20,
            sta_seconds=0.2,
            lta_seconds=5,
            trigger_on=3,
            trigger_off=1,
            filter_enabled=False,
        ),
        CoincidenceSettings(
            minimum_stations=3,
            window_seconds=3,
            alert_cooldown_seconds=0,
        ),
    ).run([case_path], include_event_payload=True)
    event = replay["candidates"][0]["event"]

    redis = FakeRedis(decode_responses=True)
    settings = AppSettings(
        webhook_hmac_secret="e2e-secret",
        push_enabled=False,
        push_mode="dry_run",
    )
    bus = RedisEventBus(redis, settings.stream_maxlen, settings.webhook_idempotency_seconds)
    app = FastAPI()
    app.state.settings = settings
    app.include_router(router)
    app.dependency_overrides[get_bus] = lambda: bus
    body = json.dumps(event, separators=(",", ":")).encode()
    timestamp = str(time.time())
    headers = {
        "Content-Type": "application/json",
        "X-Seismik-Timestamp": timestamp,
        "X-Seismik-Signature": create_signature("e2e-secret", timestamp, body),
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        accepted = await client.post("/v1/events/candidate", content=body, headers=headers)
        duplicate = await client.post("/v1/events/candidate", content=body, headers=headers)
    assert accepted.status_code == 202
    assert accepted.json()["duplicate"] is False
    assert duplicate.json()["duplicate"] is True

    devices = DeviceRepository(redis)
    await devices.register(
        DeviceRegistration(
            device_id="device-e2e-0001",
            platform="android",
            fcm_token="f" * 64,
            zone_id="CO",
            play_integrity_token="app-check-debug-token",
        )
    )
    consumer = StreamConsumer(redis, settings, devices, PushDispatcher(settings))
    await consumer.ensure_groups()
    messages = await redis.xreadgroup(
        settings.dispatcher_group,
        settings.consumer_name,
        {settings.candidate_stream: ">"},
        count=1,
    )
    stream, entries = messages[0]
    message_id, fields = entries[0]
    await consumer._handle(stream, message_id, fields)

    audit = (await redis.xrevrange(settings.push_audit_stream, count=1))[0][1]
    assert audit["test"] == "true"
    assert audit["event_id"] == event["event_id"]
    assert json.loads(audit["target_device_ids"]) == ["device-e2e-0001"]
    assert "f" * 64 not in audit["payload"]
    pending = await redis.xpending(settings.candidate_stream, settings.dispatcher_group)
    assert pending["pending"] == 0
