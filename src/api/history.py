from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any, cast

from fastapi import APIRouter, Depends, Query
from redis.asyncio import Redis

from api.config import AppSettings
from api.dependencies import ApiPrincipal, get_app_settings, get_redis, require_mobile_events_read
from eew.official import OfficialApiClient, OfficialSource, load_sources

router = APIRouter(prefix="/v1/events", tags=["official-history"])

_PRELIMINARY_SOURCE_ID = "seismik_seedlink_preliminary"
_PRELIMINARY_SOURCE = {
    "source_id": _PRELIMINARY_SOURCE_ID,
    "agency": "Seismik / SeedLink",
    "jurisdiction": "Red SeedLink configurada",
    "attribution": "Detección automática multiestación; no es un reporte oficial.",
    "preliminary": True,
}


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


def _preliminary_event(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Reduce un candidato interno a un contrato apto para la app.

    Un candidato STA/LTA no tiene, por definición, magnitud ni profundidad
    confiables. La amplitud y el índice de señal se muestran como telemetría;
    la magnitud queda nula hasta contar con respuesta instrumental y
    calibración validadas por red.
    """
    if payload.get("type") != "earthquake_candidate":
        return None
    event_id = str(payload.get("event_id") or "")
    detected_at = payload.get("detected_at")
    if not event_id or not detected_at or event_id.startswith("drill-"):
        return None
    stations = payload.get("stations")
    if not isinstance(stations, list):
        stations = []
    return {
        "event_id": event_id,
        "type": "earthquake_candidate",
        "source_id": _PRELIMINARY_SOURCE_ID,
        "agency": "Seismik / SeedLink",
        "origin_time": detected_at,
        "detected_at": detected_at,
        "latitude": payload.get("estimated_latitude"),
        "longitude": payload.get("estimated_longitude"),
        "magnitude": payload.get("magnitude_estimate"),
        "magnitude_type": (
            "M~ experimental" if payload.get("magnitude_estimate") is not None else None
        ),
        "magnitude_estimate_status": payload.get(
            "magnitude_estimate_status", "pending_station_calibration"
        ),
        "depth_km": None,
        "place": f"Zona técnica {payload.get('zone_id', 'sin ubicar')}",
        "review_status": "preliminar · sin revisión humana",
        "preliminary": True,
        "algorithm": "STA/LTA con coincidencia multiestación",
        "zone_id": payload.get("zone_id"),
        "country_code": payload.get("country_code"),
        "country_codes": payload.get("country_codes", []),
        "coincidence_window_seconds": payload.get("coincidence_window_seconds"),
        "required_stations": payload.get("required_stations"),
        "station_count": payload.get("station_count"),
        "wave_strength_index": payload.get("wave_strength_index"),
        "stations": stations,
    }


async def _recent_preliminary_events(
    redis: Redis,
    settings: AppSettings,
    *,
    start: datetime,
    limit: int,
) -> list[dict[str, Any]]:
    raw = cast(
        list[tuple[str, dict[str, str]]],
        await redis.xrevrange(settings.candidate_stream, count=max(limit * 4, 200))
        or [],
    )
    events: list[dict[str, Any]] = []
    for _message_id, fields in raw:
        raw_payload = fields.get("payload")
        if raw_payload is None:
            continue
        try:
            payload = json.loads(raw_payload)
            event = _preliminary_event(payload)
            if event is None:
                continue
            detected_at = datetime.fromisoformat(
                str(event["detected_at"]).replace("Z", "+00:00")
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if detected_at >= start:
            events.append(event)
    return events[:limit]


@router.get("/history")
async def official_history(
    sources: str = Query(default="sgc_colombia,usgs_global", max_length=300),
    days: int = Query(default=7, ge=1, le=30),
    minimum_magnitude: float = Query(default=2.5, ge=0, le=10),
    limit: int = Query(default=200, ge=1, le=500),
    settings: AppSettings = Depends(get_app_settings),
    redis: Redis = Depends(get_redis),
    _authorized: ApiPrincipal = Depends(require_mobile_events_read),
) -> dict[str, Any]:
    requested = tuple(
        sorted({item.strip().lower() for item in sources.split(",") if item.strip()})
    )
    available = {
        source.id: source
        for source in load_sources(settings.official_sources_path)
        if source.enabled
    }
    include_preliminary = _PRELIMINARY_SOURCE_ID in requested
    selected = [available[source_id] for source_id in requested if source_id in available]
    if not selected and not include_preliminary:
        selected = [available[source_id] for source_id in ("sgc_colombia", "usgs_global") if source_id in available]

    cache_key = (
        f"cache:seismik:history:{days}:{minimum_magnitude:.1f}:{limit}:"
        f"{','.join(source.id for source in selected)}"
    )
    cached = await redis.get(cache_key)
    if cached and not include_preliminary:
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
    if include_preliminary:
        events.extend(
            await _recent_preliminary_events(
                redis,
                settings,
                start=start,
                limit=limit,
            )
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
        ] + ([_PRELIMINARY_SOURCE] if include_preliminary else []),
        "errors": errors,
        "generated_at": end.isoformat(),
        "cached": False,
    }
    # Los candidatos cambian rápidamente y su ventana de seguridad es corta;
    # no se mezclan con la caché de los catálogos oficiales.
    if not include_preliminary:
        await redis.set(cache_key, json.dumps(payload), ex=settings.official_history_cache_seconds)
    return payload
