from __future__ import annotations

import httpx
import pytest
from fakeredis.aioredis import FakeRedis
from fastapi import FastAPI

from api import history
from api.config import AppSettings
from api.dependencies import (
    UNLIMITED_PRINCIPAL,
    get_app_settings,
    get_redis,
    require_mobile_events_read,
)


@pytest.mark.asyncio
async def test_history_aggregates_filters_and_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    async def fake_fetch(source, start, end, timeout_seconds):
        calls.append(source.id)
        magnitude = 4.2 if source.id == "sgc_colombia" else 1.0
        return [
            {
                "event_id": f"{source.id}:event-1",
                "type": "official_report_update",
                "source_id": source.id,
                "official_event_id": "event-1",
                "origin_time": "2026-08-29T12:00:00+00:00",
                "updated_at": None,
                "latitude": 4.6,
                "longitude": -74.0,
                "magnitude": magnitude,
                "magnitude_type": "mw",
                "depth_km": 10.0,
                "agency": source.agency,
                "place": "Zona de prueba",
                "review_status": "reviewed",
                "official_url": source.official_site,
                "attribution": source.attribution,
                "tsunami": False,
                "country_code": source.countries[0] if source.countries else None,
            }
        ]

    monkeypatch.setattr(history, "_fetch_source", fake_fetch)
    redis = FakeRedis(decode_responses=True)
    settings = AppSettings(official_sources_path="official_sources.json")
    app = FastAPI()
    app.include_router(history.router)
    app.dependency_overrides[get_app_settings] = lambda: settings
    app.dependency_overrides[get_redis] = lambda: redis
    app.dependency_overrides[require_mobile_events_read] = lambda: UNLIMITED_PRINCIPAL

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/v1/events/history",
            params={
                "sources": "sgc_colombia,usgs_global",
                "minimum_magnitude": 2.5,
            },
        )
        cached = await client.get(
            "/v1/events/history",
            params={
                "sources": "sgc_colombia,usgs_global",
                "minimum_magnitude": 2.5,
            },
        )

    assert response.status_code == 200
    assert response.json()["cached"] is False
    assert [item["source_id"] for item in response.json()["events"]] == ["sgc_colombia"]
    assert cached.json()["cached"] is True
    assert sorted(calls) == ["sgc_colombia", "usgs_global"]


@pytest.mark.asyncio
async def test_history_cache_is_scoped_by_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    async def fake_fetch(source, start, end, timeout_seconds):
        nonlocal calls
        calls += 1
        return [
            {
                "event_id": f"{source.id}:event-{index}",
                "type": "official_report_update",
                "source_id": source.id,
                "official_event_id": f"event-{index}",
                "origin_time": f"2026-08-29T12:00:0{index}+00:00",
                "updated_at": None,
                "latitude": 4.6,
                "longitude": -74.0,
                "magnitude": 4.2,
                "magnitude_type": "mw",
                "depth_km": 10.0,
                "agency": source.agency,
                "place": "Zona de prueba",
                "review_status": "reviewed",
                "official_url": source.official_site,
                "attribution": source.attribution,
                "tsunami": False,
                "country_code": source.countries[0] if source.countries else None,
            }
            for index in range(3)
        ]

    monkeypatch.setattr(history, "_fetch_source", fake_fetch)
    redis = FakeRedis(decode_responses=True)
    app = FastAPI()
    app.include_router(history.router)
    app.dependency_overrides[get_app_settings] = lambda: AppSettings(
        official_sources_path="official_sources.json"
    )
    app.dependency_overrides[get_redis] = lambda: redis
    app.dependency_overrides[require_mobile_events_read] = lambda: UNLIMITED_PRINCIPAL

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        one = await client.get(
            "/v1/events/history", params={"sources": "sgc_colombia", "limit": 1}
        )
        three = await client.get(
            "/v1/events/history", params={"sources": "sgc_colombia", "limit": 3}
        )

    assert len(one.json()["events"]) == 1
    assert len(three.json()["events"]) == 3
    assert calls == 2


@pytest.mark.asyncio
async def test_history_includes_seedlink_candidates_only_when_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_fetch(source, start, end, timeout_seconds):
        return []

    monkeypatch.setattr(history, "_fetch_source", fake_fetch)
    redis = FakeRedis(decode_responses=True)
    await redis.xadd(
        "stream:seismik:candidates",
        {
            "payload": __import__("json").dumps(
                {
                    "event_id": "candidate-live-1",
                    "type": "earthquake_candidate",
                    "detected_at": "2026-09-05T12:00:00Z",
                    "zone_id": "CO-central",
                    "country_code": "CO",
                    "country_codes": ["CO"],
                    "coincidence_window_seconds": 8.0,
                    "required_stations": 2,
                    "station_count": 2,
                    "wave_strength_index": 1.5,
                    "magnitude_estimate_status": "pending_station_calibration",
                    "estimated_latitude": 4.6,
                    "estimated_longitude": -74.0,
                    "stations": [
                        {
                            "provider_id": "earthscope_colombia",
                            "country_code": "CO",
                            "zone_id": "CO-central",
                            "station_id": "CM.PRA",
                            "stream_id": "CM.PRA.00.HHZ",
                            "trigger_time": "2026-09-05T12:00:00Z",
                            "received_at": "2026-09-05T12:00:01Z",
                            "sta_lta_ratio": 4.5,
                            "peak_amplitude_counts": 42.0,
                            "noise_rms_counts": 2.0,
                        },
                        {
                            "provider_id": "earthscope_colombia",
                            "country_code": "CO",
                            "zone_id": "CO-central",
                            "station_id": "CM.SJC",
                            "stream_id": "CM.SJC.00.HHZ",
                            "trigger_time": "2026-09-05T12:00:01Z",
                            "received_at": "2026-09-05T12:00:02Z",
                            "sta_lta_ratio": 4.0,
                        },
                    ],
                }
            )
        },
    )
    app = FastAPI()
    app.include_router(history.router)
    app.dependency_overrides[get_app_settings] = lambda: AppSettings(
        official_sources_path="official_sources.json"
    )
    app.dependency_overrides[get_redis] = lambda: redis
    app.dependency_overrides[require_mobile_events_read] = lambda: UNLIMITED_PRINCIPAL

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        hidden = await client.get("/v1/events/history", params={"sources": "sgc_colombia"})
        visible = await client.get(
            "/v1/events/history",
            params={"sources": "seismik_seedlink_preliminary"},
        )

    assert hidden.json()["events"] == []
    item = visible.json()["events"][0]
    assert item["preliminary"] is True
    assert item["source_id"] == "seismik_seedlink_preliminary"
    assert item["magnitude"] is None
    assert item["wave_strength_index"] == 1.5
    assert item["magnitude_estimate_status"] == "pending_station_calibration"
    assert item["station_count"] == 2
