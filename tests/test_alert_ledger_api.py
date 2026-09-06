"""La bitácora de alertas permite que una app sin conexión recupere lo perdido."""
from __future__ import annotations

import httpx
import pytest
from fakeredis.aioredis import FakeRedis
from fastapi import FastAPI

from api.alerts import router
from api.config import AppSettings
from api.device_sessions import DeviceSessionRepository
from api.devices_store import DeviceRepository
from api.schemas import DeviceRegistration, DeviceTarget
from dispatcher.consumer import StreamConsumer
from dispatcher.policy import AlertPolicy
from dispatcher.push import PushResult


class RecordingPush:
    def __init__(self) -> None:
        self.calls: list[tuple[dict, list[DeviceTarget], bool]] = []

    async def send(self, event, targets, *, critical):
        target_list = list(targets)
        self.calls.append((event, target_list, critical))
        return PushResult(attempted=len(target_list), succeeded=len(target_list))


def build_app(redis: FakeRedis, settings: AppSettings) -> FastAPI:
    app = FastAPI()
    app.state.redis = redis
    app.state.settings = settings
    app.state.devices = DeviceRepository(redis)
    app.include_router(router)
    return app


async def session_headers(redis: FakeRedis, settings: AppSettings, device_id: str) -> dict[str, str]:
    token = await DeviceSessionRepository(
        redis, ttl_seconds=settings.device_session_ttl_seconds
    ).issue(device_id)
    return {"X-Seismik-Device-Session": token}


async def register(
    redis: FakeRedis,
    device_id: str = "device-0001",
    *,
    latitude: float = 4.65,
    longitude: float = -74.05,
    alert_radius_km: float = 250.0,
    minimum_magnitude: float = 4.0,
) -> None:
    await DeviceRepository(redis).register(
        DeviceRegistration(
            device_id=device_id,
            platform="android",
            fcm_token="f" * 64,
            zone_id="andes",
            latitude=latitude,
            longitude=longitude,
            alert_radius_km=alert_radius_km,
            minimum_notification_magnitude=minimum_magnitude,
            play_integrity_token="integrity-token-android",
        )
    )


def candidate(event_id: str = "candidate-1") -> dict:
    return {
        "event_id": event_id,
        "type": "earthquake_candidate",
        "zone_id": "andes",
        "estimated_latitude": 4.65,
        "estimated_longitude": -74.05,
    }


def official(event_id: str = "official-1", magnitude: float = 5.4) -> dict:
    return {
        "event_id": event_id,
        "candidate_event_id": "candidate-1",
        "type": "official_report_update",
        "preferred_report": {
            "agency": "SGC",
            "official_event_id": "SGC-1",
            "origin_time": "2026-01-01T00:00:00Z",
            "latitude": 4.7,
            "longitude": -74.0,
            "magnitude": magnitude,
            "depth_km": 12,
            "place": "Cundinamarca",
            "official_url": "https://sgc.gov.co/event/1",
        },
    }


async def emit(redis: FakeRedis, settings: AppSettings, events: list[dict]) -> RecordingPush:
    push = RecordingPush()
    consumer = StreamConsumer(
        redis, settings, DeviceRepository(redis), push, AlertPolicy(redis, settings)
    )
    for event in events:
        if event["type"] == "official_report_update":
            await consumer._handle_official(event)
        else:
            await consumer._handle_candidate(event)
    return push


@pytest.mark.asyncio
async def test_offline_device_recovers_the_alerts_it_missed() -> None:
    redis = FakeRedis(decode_responses=True)
    settings = AppSettings()
    await register(redis)
    await emit(redis, settings, [candidate(), official()])

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=build_app(redis, settings)),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/v1/alerts/recent",
            params={"device_id": "device-0001"},
                headers=await session_headers(redis, settings, "device-0001"),
        )
    assert response.status_code == 200
    body = response.json()
    assert [alert["event_id"] for alert in body["alerts"]] == ["candidate-1", "official-1"]
    assert body["alerts"][0]["critical"] is True
    assert body["alerts"][1]["magnitude"] == 5.4
    assert body["cursor"]


@pytest.mark.asyncio
async def test_cursor_returns_only_what_happened_after_the_last_sync() -> None:
    redis = FakeRedis(decode_responses=True)
    settings = AppSettings()
    await register(redis)
    await emit(redis, settings, [candidate("candidate-1")])
    app = build_app(redis, settings)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        headers = await session_headers(redis, settings, "device-0001")
        first = await client.get(
            "/v1/alerts/recent",
            params={"device_id": "device-0001"},
            headers=headers,
        )
        cursor = first.json()["cursor"]
        await emit(redis, settings, [official("official-2")])
        second = await client.get(
            "/v1/alerts/recent",
            params={"device_id": "device-0001", "since": cursor},
            headers=headers,
        )
    assert [alert["event_id"] for alert in second.json()["alerts"]] == ["official-2"]


@pytest.mark.asyncio
async def test_ledger_applies_the_magnitude_threshold_of_the_device() -> None:
    redis = FakeRedis(decode_responses=True)
    settings = AppSettings()
    await register(redis, minimum_magnitude=7.0)
    await emit(redis, settings, [official("official-1", magnitude=5.4)])

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=build_app(redis, settings)),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/v1/alerts/recent",
            params={"device_id": "device-0001"},
            headers=await session_headers(redis, settings, "device-0001"),
        )
    assert response.json()["alerts"] == []


@pytest.mark.asyncio
async def test_ledger_applies_the_radius_chosen_by_the_device() -> None:
    redis = FakeRedis(decode_responses=True)
    settings = AppSettings()
    await register(redis, latitude=6.25, longitude=-75.57, alert_radius_km=50)
    await emit(redis, settings, [candidate()])

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=build_app(redis, settings)),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/v1/alerts/recent",
            params={"device_id": "device-0001"},
            headers=await session_headers(redis, settings, "device-0001"),
        )
    assert response.json()["alerts"] == []


@pytest.mark.asyncio
async def test_ledger_requires_the_matching_device_session() -> None:
    redis = FakeRedis(decode_responses=True)
    settings = AppSettings()
    await register(redis)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=build_app(redis, settings)),
        base_url="http://test",
    ) as client:
        anonymous = await client.get(
            "/v1/alerts/recent", params={"device_id": "device-0001"}
        )
        other_session = await session_headers(redis, settings, "device-0001")
        mismatched = await client.get(
            "/v1/alerts/recent",
            params={"device_id": "device-9999"},
            headers=other_session,
        )
    assert anonymous.status_code == 401
    assert mismatched.status_code == 403
