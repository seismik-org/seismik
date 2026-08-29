from __future__ import annotations

import httpx
import pytest
from fakeredis.aioredis import FakeRedis
from fastapi import FastAPI

from api import history
from api.config import AppSettings
from api.dependencies import get_app_settings, get_redis


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
