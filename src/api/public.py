from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException
from redis.asyncio import Redis

from api.config import AppSettings
from api.dependencies import get_app_settings, get_redis, require_consumer_api_key

router = APIRouter(prefix="/v1", tags=["public-monitor"])


@lru_cache(maxsize=4)
def _load_stations(catalog_path: str) -> tuple[dict[str, Any], ...]:
    path = Path(catalog_path)
    if not path.is_file():
        raise FileNotFoundError(catalog_path)
    document = json.loads(path.read_text(encoding="utf-8"))
    stations: list[dict[str, Any]] = []
    for provider in document.get("seedlink", {}).get("providers", []):
        if not provider.get("enabled", True):
            continue
        for station in provider.get("stations", []):
            stations.append(
                {
                    "station_id": station["station"],
                    "network": station["network"],
                    "country_code": station.get("country_code"),
                    "latitude": station["latitude"],
                    "longitude": station["longitude"],
                    "provider_id": provider["id"],
                }
            )
    return tuple(stations)


@router.get("/network/stations")
async def network_stations(
    settings: AppSettings = Depends(get_app_settings),
    _authorized: None = Depends(require_consumer_api_key),
) -> dict[str, list[dict[str, Any]]]:
    try:
        stations = _load_stations(settings.station_catalog_path)
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="Station catalog is unavailable")
    return {"stations": list(stations)}


@router.get("/events/recent")
async def recent_events(
    settings: AppSettings = Depends(get_app_settings),
    redis: Redis = Depends(get_redis),
    _authorized: None = Depends(require_consumer_api_key),
) -> dict[str, list[dict[str, Any]]]:
    raw = cast(
        list[tuple[str, dict[str, str]]],
        await redis.xrevrange(settings.official_stream, count=settings.public_recent_event_limit),
    )
    events: list[dict[str, Any]] = []
    for _message_id, fields in raw:
        event = json.loads(fields["payload"])
        report = event.get("preferred_report", {})
        events.append(
            {
                "event_id": event["event_id"],
                "type": "official_report_update",
                "origin_time": report.get("origin_time"),
                "latitude": report.get("latitude"),
                "longitude": report.get("longitude"),
                "magnitude": report.get("magnitude"),
                "depth_km": report.get("depth_km"),
                "agency": report.get("agency"),
                "place": report.get("place"),
                "official_url": report.get("official_url"),
            }
        )
    return {"events": events}
