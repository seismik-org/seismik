from __future__ import annotations

import httpx
import pytest
from fakeredis.aioredis import FakeRedis
from fastapi import FastAPI

from api import history
from api.config import AppSettings
from api.dependencies import UNLIMITED_PRINCIPAL, get_app_settings, get_redis, require_events_read


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
    app.dependency_overrides[require_events_read] = lambda: UNLIMITED_PRINCIPAL

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
    app.dependency_overrides[require_events_read] = lambda: UNLIMITED_PRINCIPAL

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
