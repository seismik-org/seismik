from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from redis.asyncio import Redis

from api.config import AppSettings
from api.dependencies import get_app_settings, get_redis, require_consumer_api_key
from eew.official import OfficialApiClient, OfficialSource, load_sources

router = APIRouter(prefix="/v1/events", tags=["official-history"])


def _public_event(source: OfficialSource, report: Any) -> dict[str, Any]:
    return {
        "event_id": f"{source.id}:{report.official_event_id}",
        "type": "official_report_update",
        "source_id": source.id,
        "official_event_id": report.official_event_id,
        "origin_time": report.origin_time,
        "updated_at": report.updated_at,
        "latitude": report.latitude,
        "longitude": report.longitude,
        "magnitude": report.magnitude,
        "magnitude_type": report.magnitude_type,
        "depth_km": report.depth_km,
        "agency": report.agency,
        "place": report.place,
        "review_status": report.review_status,
        "official_url": report.official_url,
        "attribution": report.attribution,
        "tsunami": report.tsunami,
        "country_code": source.countries[0] if len(source.countries) == 1 else None,
    }


async def _fetch_source(
    source: OfficialSource,
    start: datetime,
    end: datetime,
    timeout_seconds: float,
) -> list[dict[str, Any]]:
    client = OfficialApiClient(source, timeout_seconds=timeout_seconds)
    reports = await asyncio.to_thread(client.fetch, start, end)
    return [_public_event(source, report) for report in reports]


@router.get("/history")
async def official_history(
    sources: str = Query(default="sgc_colombia,usgs_global", max_length=300),
    days: int = Query(default=7, ge=1, le=30),
    minimum_magnitude: float = Query(default=2.5, ge=0, le=10),
    limit: int = Query(default=200, ge=1, le=500),
    settings: AppSettings = Depends(get_app_settings),
    redis: Redis = Depends(get_redis),
    _authorized: None = Depends(require_consumer_api_key),
) -> dict[str, Any]:
    requested = tuple(
        sorted({item.strip().lower() for item in sources.split(",") if item.strip()})
    )
    available = {
        source.id: source
        for source in load_sources(settings.official_sources_path)
        if source.enabled
    }
    selected = [available[source_id] for source_id in requested if source_id in available]
    if not selected:
        selected = [available[source_id] for source_id in ("sgc_colombia", "usgs_global") if source_id in available]

    cache_key = (
        f"cache:seismik:history:{days}:{minimum_magnitude:.1f}:{limit}:"
        f"{','.join(source.id for source in selected)}"
    )
    cached = await redis.get(cache_key)
    if cached:
        result = json.loads(cached)
        result["cached"] = True
        return result

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    results = await asyncio.gather(
        *(
            _fetch_source(source, start, end, settings.official_history_timeout_seconds)
            for source in selected
        ),
        return_exceptions=True,
    )
    events: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for source, result in zip(selected, results, strict=True):
        if isinstance(result, BaseException):
            errors.append({"source_id": source.id, "message": type(result).__name__})
            continue
        events.extend(
            event
            for event in result
            if event["magnitude"] is None or event["magnitude"] >= minimum_magnitude
        )
    events.sort(key=lambda event: event["origin_time"], reverse=True)
    payload: dict[str, Any] = {
        "events": events[:limit],
        "sources": [
            {
                "source_id": source.id,
                "agency": source.agency,
                "jurisdiction": source.jurisdiction,
                "attribution": source.attribution,
            }
            for source in selected
        ],
        "errors": errors,
        "generated_at": end.isoformat(),
        "cached": False,
    }
    await redis.set(cache_key, json.dumps(payload), ex=settings.official_history_cache_seconds)
    return payload
