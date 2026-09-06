"""Simulacros sísmicos: del evento simulado al push filtrado por dispositivo.

Recorre la ruta completa candidato → API firmada → Redis Streams → dispatcher,
sin atajos ni endpoints especiales para pruebas.
"""
from __future__ import annotations

import json
import time

import httpx
import pytest
from fakeredis.aioredis import FakeRedis
from fastapi import FastAPI

from api.bus import RedisEventBus
from api.config import AppSettings
from api.dependencies import get_app_settings, get_bus
from api.devices_store import DeviceRepository
from api.schemas import DeviceRegistration, DeviceTarget
from api.security import create_signature
from api.webhooks import router
from dispatcher.consumer import StreamConsumer
from dispatcher.policy import AlertPolicy
from dispatcher.push import PushResult
from eew.simulation import (
    PROFILES,
    drill_sequence,
    is_drill,
    simulated_candidate,
    simulated_official_update,
)

SECRET = "simulation-shared-secret"


class RecordingPush:
    def __init__(self) -> None:
        self.calls: list[tuple[dict, list[DeviceTarget], bool]] = []

    async def send(self, event, targets, *, critical):
        target_list = list(targets)
        self.calls.append((event, target_list, critical))
        return PushResult(attempted=len(target_list), succeeded=len(target_list))


def ingest_app(redis: FakeRedis, settings: AppSettings) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    bus = RedisEventBus(redis, settings.stream_maxlen, settings.webhook_idempotency_seconds)
    app.dependency_overrides[get_bus] = lambda: bus
    app.dependency_overrides[get_app_settings] = lambda: settings
    return app


async def post_event(client: httpx.AsyncClient, path: str, event: dict) -> httpx.Response:
    body = json.dumps(event, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    timestamp = str(int(time.time()))
    signature = create_signature(SECRET, timestamp, body)
    return await client.post(
        path,
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Seismik-Timestamp": timestamp,
            "X-Seismik-Signature": signature,
        },
    )


async def drain(redis: FakeRedis, settings: AppSettings, push: RecordingPush) -> StreamConsumer:
    """Consume una vez cada stream, como haría el dispatcher en producción."""

    consumer = StreamConsumer(
        redis, settings, DeviceRepository(redis), push, AlertPolicy(redis, settings)
    )
    await consumer.ensure_groups()
    messages = await redis.xreadgroup(
        settings.dispatcher_group,
        settings.consumer_name,
        {stream: ">" for stream in consumer.streams},
        count=50,
        block=10,
    )
    for stream, entries in messages or []:
        for message_id, fields in entries:
            await consumer._handle(stream, message_id, fields)
    return consumer


def simulation_settings(**overrides: object) -> AppSettings:
    return AppSettings(
        webhook_hmac_secret=SECRET,
        device_api_key="device-bootstrap-key",
        **overrides,
    )


async def register_device(
    redis: FakeRedis,
    device_id: str,
    *,
    latitude: float,
    longitude: float,
    alert_radius_km: float = 250.0,
    minimum_magnitude: float = 4.0,
    early: bool = True,
) -> None:
    await DeviceRepository(redis).register(
        DeviceRegistration(
            device_id=device_id,
            platform="android",
            fcm_token=device_id.ljust(64, "f")[:64],
            zone_id="andes",
            latitude=latitude,
            longitude=longitude,
            alert_radius_km=alert_radius_km,
            minimum_notification_magnitude=minimum_magnitude,
            receive_early_alerts=early,
            play_integrity_token="integrity-token-android",
        )
    )


def test_every_simulated_identifier_is_recognisable_as_a_drill() -> None:
    candidate, official = drill_sequence("bogota")
    assert is_drill(candidate["event_id"])
    assert is_drill(official["event_id"])
    assert is_drill(official["preferred_report"]["official_event_id"])
    assert not is_drill("candidate-real-1")


def test_simulated_candidate_satisfies_the_public_contract() -> None:
    from api.schemas import EarthquakeCandidate

    event = simulated_candidate(PROFILES["pacifico"], station_count=4)
    parsed = EarthquakeCandidate.model_validate(event)
    assert parsed.station_count == 4
    assert len({station.station_id for station in parsed.stations}) == 4
    assert parsed.estimated_latitude == pytest.approx(PROFILES["pacifico"].latitude)


def test_simulated_official_update_satisfies_the_public_contract() -> None:
    from api.schemas import OfficialReportUpdate

    event = simulated_official_update(PROFILES["atacama"], "drill-candidate-1", magnitude=6.9)
    parsed = OfficialReportUpdate.model_validate(event)
    assert parsed.preferred_report.magnitude == 6.9
    assert parsed.candidate_event_id == "drill-candidate-1"


def test_unlocated_drill_omits_both_coordinates() -> None:
    from api.schemas import EarthquakeCandidate

    event = simulated_candidate(PROFILES["bogota"], located=False)
    parsed = EarthquakeCandidate.model_validate(event)
    assert parsed.estimated_latitude is None
    assert parsed.estimated_longitude is None


def test_an_unknown_profile_is_reported_clearly() -> None:
    with pytest.raises(KeyError, match="Perfil desconocido"):
        drill_sequence("marte")


@pytest.mark.asyncio
async def test_drill_reaches_only_the_devices_that_asked_for_it() -> None:
    redis = FakeRedis(decode_responses=True)
    settings = simulation_settings()
    await register_device(redis, "device-near-01", latitude=4.70, longitude=-74.00)
    await register_device(
        redis, "device-far-002", latitude=6.25, longitude=-75.57, alert_radius_km=50
    )
    await register_device(redis, "device-muted-03", latitude=4.66, longitude=-74.04, early=False)

    candidate, official = drill_sequence("bogota")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=ingest_app(redis, settings)),
        base_url="http://test",
    ) as client:
        accepted = await post_event(client, "/v1/events/candidate", candidate)
        assert accepted.status_code == 202
        assert accepted.json()["duplicate"] is False

    push = RecordingPush()
    await drain(redis, settings, push)
    assert len(push.calls) == 1
    event, targets, critical = push.calls[0]
    assert critical is True
    assert event["event_id"] == candidate["event_id"]
    assert [target.device_id for target in targets] == ["device-near-01"]

    ledger = await redis.xrevrange(settings.alert_ledger_stream, count=5)
    assert ledger[0][1]["event_id"] == candidate["event_id"]
    assert ledger[0][1]["critical"] == "true"
    assert official["candidate_event_id"] == candidate["event_id"]


@pytest.mark.asyncio
async def test_a_repeated_drill_is_absorbed_by_the_bus_idempotency() -> None:
    redis = FakeRedis(decode_responses=True)
    settings = simulation_settings()
    await register_device(redis, "device-near-01", latitude=4.66, longitude=-74.04)
    candidate, _official = drill_sequence("bogota")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=ingest_app(redis, settings)),
        base_url="http://test",
    ) as client:
        first = await post_event(client, "/v1/events/candidate", candidate)
        second = await post_event(client, "/v1/events/candidate", candidate)

    assert first.json()["duplicate"] is False
    assert second.json()["duplicate"] is True

    push = RecordingPush()
    await drain(redis, settings, push)
    assert len(push.calls) == 1


@pytest.mark.asyncio
async def test_a_second_drill_in_the_same_zone_is_held_by_the_cooldown() -> None:
    redis = FakeRedis(decode_responses=True)
    settings = simulation_settings(alert_cooldown_seconds=120)
    await register_device(redis, "device-near-01", latitude=4.66, longitude=-74.04)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=ingest_app(redis, settings)),
        base_url="http://test",
    ) as client:
        for _ in range(2):
            candidate, _ = drill_sequence("bogota")
            assert (await post_event(client, "/v1/events/candidate", candidate)).status_code == 202

    push = RecordingPush()
    await drain(redis, settings, push)
    assert len(push.calls) == 1


@pytest.mark.asyncio
async def test_the_official_update_of_a_drill_respects_the_magnitude_threshold() -> None:
    redis = FakeRedis(decode_responses=True)
    settings = simulation_settings()
    await register_device(
        redis, "device-sensitive-1", latitude=4.66, longitude=-74.04, minimum_magnitude=3.0
    )
    await register_device(
        redis, "device-strict-0002", latitude=4.67, longitude=-74.03, minimum_magnitude=7.5
    )
    candidate, official = drill_sequence("bogota", magnitude=5.2)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=ingest_app(redis, settings)),
        base_url="http://test",
    ) as client:
        await post_event(client, "/v1/events/candidate", candidate)
        assert (
            await post_event(client, "/v1/events/official-update", official)
        ).status_code == 202

    push = RecordingPush()
    await drain(redis, settings, push)
    official_calls = [call for call in push.calls if call[2] is False]
    assert len(official_calls) == 1
    assert [target.device_id for target in official_calls[0][1]] == ["device-sensitive-1"]


@pytest.mark.asyncio
async def test_a_tampered_drill_never_reaches_the_bus() -> None:
    redis = FakeRedis(decode_responses=True)
    settings = simulation_settings()
    candidate, _ = drill_sequence("bogota")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=ingest_app(redis, settings)),
        base_url="http://test",
    ) as client:
        body = json.dumps(candidate, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        timestamp = str(int(time.time()))
        signature = create_signature(SECRET, timestamp, body)
        tampered = json.dumps(
            {**candidate, "zone_id": "otra-zona"}, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        response = await client.post(
            "/v1/events/candidate",
            content=tampered,
            headers={
                "Content-Type": "application/json",
                "X-Seismik-Timestamp": timestamp,
                "X-Seismik-Signature": signature,
            },
        )

    assert response.status_code == 401
    assert await redis.xlen(settings.candidate_stream) == 0
