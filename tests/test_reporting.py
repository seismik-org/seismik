from __future__ import annotations

import json
import time

import httpx
import pytest
from fakeredis.aioredis import FakeRedis
from fastapi import FastAPI
from pydantic import ValidationError

from api.bus import PublishResult
from api.config import AppSettings
from api.dependencies import get_app_settings, get_bus, get_devices, get_redis
from api.security import create_signature, derive_crowd_token
from reporting.agencies import routes_for
from reporting.ingest import router
from reporting.schemas import DamageReport, FeltReport


class FakeBus:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    async def publish_once(self, stream: str, event: dict) -> PublishResult:
        self.events.append((stream, event))
        return PublishResult(accepted=True, stream_id="10-0")


class FakeDevices:
    async def exists(self, device_id: str) -> bool:
        return device_id == "device-0001"


def felt_payload() -> dict:
    return {
        "report_id": "report-0001",
        "device_id": "device-0001",
        "earthquake_event_id": "candidate-123",
        "official_event_id": "us7000abcd",
        "observed_at": "2026-08-19T12:00:00Z",
        "latitude": 4.651234,
        "longitude": -74.051234,
        "location_accuracy_m": 8.0,
        "location_precision": "approximate",
        "country_code": "CO",
        "share_with_official_agencies": True,
        "felt": True,
        "intensity_mmi": 4,
        "indoors": True,
        "objects_moved": True,
    }


def test_felt_report_requires_intensity_only_when_felt() -> None:
    invalid = felt_payload() | {"intensity_mmi": None}
    with pytest.raises(ValidationError, match="intensity_mmi"):
        FeltReport.model_validate(invalid)


def test_damage_report_flags_immediate_danger() -> None:
    payload = felt_payload()
    for key in ("felt", "intensity_mmi", "indoors", "objects_moved"):
        payload.pop(key)
    payload.update(
        type="seismik_damage_report",
        severity="severe",
        hazards=["gas_leak"],
        people_trapped=False,
    )
    report = DamageReport.model_validate(payload)
    assert report.requires_emergency_action


def test_agency_routes_include_local_and_global_official_forms() -> None:
    routes = routes_for("CO", "us7000abcd")
    assert [route.agency_id for route in routes] == ["sgc", "usgs_dyfi"]
    assert routes[1].official_url.endswith("/us7000abcd/tellus")
    assert all(not route.automatic_submission for route in routes)
    selected = routes_for("CO", "us7000abcd", ("sgc",))
    assert [route.agency_id for route in selected] == ["sgc"]


def test_felt_report_rejects_agency_selection_without_consent() -> None:
    payload = felt_payload() | {
        "share_with_official_agencies": False,
        "selected_agency_ids": ["sgc"],
    }
    with pytest.raises(ValidationError, match="share_with_official_agencies"):
        FeltReport.model_validate(payload)


@pytest.mark.asyncio
async def test_felt_endpoint_signs_stores_and_redacts_approximate_location() -> None:
    settings = AppSettings(crowd_master_secret="report-secret")
    redis = FakeRedis(decode_responses=True)
    bus = FakeBus()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_app_settings] = lambda: settings
    app.dependency_overrides[get_bus] = lambda: bus
    app.dependency_overrides[get_devices] = lambda: FakeDevices()
    app.dependency_overrides[get_redis] = lambda: redis
    body = json.dumps(felt_payload(), separators=(",", ":")).encode()
    timestamp = str(time.time())
    crowd_token = derive_crowd_token("report-secret", "device-0001")
    signature = create_signature(crowd_token, timestamp, body)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/reports/felt",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Seismik-Timestamp": timestamp,
                "X-Seismik-Signature": signature,
            },
        )
    assert response.status_code == 202
    assert response.json()["accepted"] is True
    assert len(response.json()["agency_routes"]) == 2
    stored = bus.events[0][1]
    assert stored["event_id"] == "report-0001"
    assert stored["earthquake_event_id"] == "candidate-123"
    assert stored["latitude"] == 4.65
    assert stored["longitude"] == -74.05
    assert stored["location_accuracy_m"] is None


@pytest.mark.asyncio
async def test_agency_catalog_is_available_before_reporting() -> None:
    app = FastAPI()
    app.include_router(router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/v1/reports/agencies",
            params={"country_code": "CO", "official_event_id": "us7000abcd"},
        )
    assert response.status_code == 200
    assert [item["agency_id"] for item in response.json()] == ["sgc", "usgs_dyfi"]
