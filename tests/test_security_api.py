from __future__ import annotations

import json
import time

import httpx
import pytest
from fastapi import FastAPI

from api.bus import PublishResult
from api.config import AppSettings
from api.dependencies import get_bus
from api.security import create_signature, verify_signature
from api.webhooks import router


class FakeBus:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    async def publish_once(self, stream: str, event: dict) -> PublishResult:
        self.events.append((stream, event))
        return PublishResult(True, "1-0")


def candidate_payload() -> dict:
    stations = []
    for station in ("CM.A", "CM.B", "CM.C"):
        stations.append({
            "provider_id": "earthscope", "country_code": "CO", "zone_id": "andes",
            "station_id": station, "stream_id": f"{station}.00.HHZ",
            "trigger_time": "2026-01-01T00:00:10Z", "received_at": "2026-01-01T00:00:11Z",
            "sta_lta_ratio": 4.2, "latitude": 6.8, "longitude": -73.1,
        })
    return {
        "event_id": "candidate-123", "type": "earthquake_candidate",
        "status": "unlocated_unreviewed", "zone_id": "andes", "country_code": "CO",
        "country_codes": ["CO"], "detected_at": "2026-01-01T00:00:12Z",
        "coincidence_window_seconds": 15, "required_stations": 3,
        "station_count": 3, "stations": stations,
        "estimated_latitude": 6.8, "estimated_longitude": -73.1,
    }


def test_hmac_rejects_replay() -> None:
    body = b"{}"
    timestamp = "1000"
    signature = create_signature("secret", timestamp, body)
    with pytest.raises(Exception) as error:
        verify_signature(
            secret="secret", timestamp=timestamp, signature=signature, body=body,
            max_skew_seconds=30, now=1100,
        )
    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_candidate_endpoint_validates_signature_and_enqueues() -> None:
    settings = AppSettings(
        webhook_hmac_secret="test-secret", device_api_key="device-key",
        crowd_master_secret="crowd-secret",
    )
    bus = FakeBus()
    app = FastAPI()
    app.state.settings = settings
    app.include_router(router)
    app.dependency_overrides[get_bus] = lambda: bus
    body = json.dumps(candidate_payload(), separators=(",", ":")).encode()
    timestamp = str(time.time())
    signature = create_signature("test-secret", timestamp, body)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/events/candidate",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Seismik-Timestamp": timestamp,
                "X-Seismik-Signature": signature,
            },
        )
    assert response.status_code == 202
    assert response.json() == {"accepted": True, "duplicate": False, "stream_id": "1-0"}
    assert bus.events[0][0] == settings.candidate_stream
    assert bus.events[0][1]["event_id"] == "candidate-123"


@pytest.mark.asyncio
async def test_candidate_endpoint_rejects_body_tampering() -> None:
    settings = AppSettings(webhook_hmac_secret="test-secret")
    app = FastAPI()
    app.state.settings = settings
    app.include_router(router)
    app.dependency_overrides[get_bus] = lambda: FakeBus()
    body = json.dumps(candidate_payload()).encode()
    timestamp = str(time.time())
    bad_signature = create_signature("test-secret", timestamp, b"different")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/events/candidate", content=body,
            headers={"X-Seismik-Timestamp": timestamp, "X-Seismik-Signature": bad_signature},
        )
    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("headers", "expected_detail"),
    [
        ({}, "Missing signature headers"),
        (
            {"X-Seismik-Timestamp": "not-a-number", "X-Seismik-Signature": "0" * 64},
            "Invalid timestamp",
        ),
    ],
)
async def test_candidate_endpoint_rejects_missing_or_invalid_security_headers(
    headers: dict[str, str], expected_detail: str
) -> None:
    settings = AppSettings(webhook_hmac_secret="test-secret")
    app = FastAPI()
    app.state.settings = settings
    app.include_router(router)
    app.dependency_overrides[get_bus] = lambda: FakeBus()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/events/candidate", content=json.dumps(candidate_payload()), headers=headers
        )
    assert response.status_code == 401
    assert response.json()["detail"] == expected_detail


@pytest.mark.asyncio
async def test_signed_malformed_candidate_is_rejected_before_enqueue() -> None:
    settings = AppSettings(webhook_hmac_secret="test-secret")
    bus = FakeBus()
    app = FastAPI()
    app.state.settings = settings
    app.include_router(router)
    app.dependency_overrides[get_bus] = lambda: bus
    body = b'{"event_id":"broken"}'
    timestamp = str(time.time())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/events/candidate",
            content=body,
            headers={
                "X-Seismik-Timestamp": timestamp,
                "X-Seismik-Signature": create_signature("test-secret", timestamp, body),
            },
        )
    assert response.status_code == 422
    assert bus.events == []


@pytest.mark.asyncio
async def test_oversized_event_is_rejected_before_signature_processing() -> None:
    settings = AppSettings(webhook_hmac_secret="test-secret", event_max_body_bytes=1024)
    app = FastAPI()
    app.state.settings = settings
    app.include_router(router)
    app.dependency_overrides[get_bus] = lambda: FakeBus()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/v1/events/candidate", content=b"x" * 1025)
    assert response.status_code == 413
