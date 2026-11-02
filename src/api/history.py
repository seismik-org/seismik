from __future__ import annotations

import asyncio
import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from typing import Any, TypeGuard, cast

from fastapi import APIRouter, Depends, Query, Response
from redis.asyncio import Redis

from api.config import AppSettings
from api.dependencies import ApiPrincipal, get_app_settings, get_redis, require_mobile_events_read
from api.event_association import associate_events
from api.geojson import FORMAT_QUERY, GEOJSON_RESPONSE, OutputFormat, feature_collection
from eew.candidate_evidence import public_candidate_location
from eew.official import OfficialApiClient, OfficialSource, load_sources

router = APIRouter(prefix="/v1/events", tags=["official-history"])

# Bounded lock stripes prevent simultaneous cache fills in this API worker.
_history_locks = [asyncio.Lock() for _ in range(64)]

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


_OWN_MAGNITUDE_METHOD_MAX_LENGTH = 400


def _unavailable_own_magnitude(reason: str, calibration_version: str | None = None,
                               validation_status: str = "not_evaluated") -> dict[str, Any]:
    return {
        "value": None,
        "validation_status": validation_status,
        "scale": "ML",
        "status": "unavailable",
        "reason": reason,
        "uncertainty": None,
        "method": None,
        "station_count": 0,
        "stations": [],
        "calibration_version": calibration_version,
        "source": "seismik_seedlink_estimate",
    }


def _own_magnitude(payload: dict[str, Any]) -> dict[str, Any]:
    """Magnitud propia de Seismik, siempre separada de la oficial asociada.

    Sólo se acepta un valor completo y coherente (escala ML, estado preliminar,
    versión de calibración, incertidumbre y al menos tres estaciones). Cualquier
    otra cosa se publica como ``null`` con la razón: no se rellena ni se infiere.
    """

    raw = payload.get("own_magnitude")
    if not isinstance(raw, dict):
        return _unavailable_own_magnitude("not_computed_for_this_event")
    version = raw.get("calibration_version")
    version = version if isinstance(version, str) and version else None
    value, uncertainty = raw.get("value"), raw.get("uncertainty")
    validation_status = raw.get("validation_status")
    if not isinstance(validation_status, str) or not validation_status:
        return _unavailable_own_magnitude("missing_validation_status", version)
    if value is None:
        reason = raw.get("reason")
        return _unavailable_own_magnitude(reason if isinstance(reason, str) and reason else "unavailable", version,
                                          validation_status)

    def finite(number: object) -> TypeGuard[float]:
        return isinstance(number, (int, float)) and not isinstance(number, bool) and math.isfinite(number)

    stations = raw.get("stations")
    station_ids = [s.get("station_id") for s in stations if isinstance(s, dict)] if isinstance(stations, list) else []
    method = raw.get("method")
    count = raw.get("station_count")
    if not (
        raw.get("scale") == "ML"
        and validation_status in {"validated", "beta_unvalidated"}
        and raw.get("status") == "preliminary"
        and finite(value) and -2 <= value <= 10
        and finite(uncertainty) and 0 <= uncertainty <= 2
        and version is not None
        and isinstance(count, int) and not isinstance(count, bool) and count >= 3
        and isinstance(stations, list) and len(stations) == count
        and all(isinstance(identity, str) and identity for identity in station_ids)
        and len(station_ids) == count and len(set(station_ids)) == count
        and isinstance(method, str) and method
    ):
        return _unavailable_own_magnitude("invalid_estimate_rejected", version)
    return {
        "value": round(float(value), 1),
        "validation_status": validation_status,
        "scale": "ML",
        "status": "preliminary",
        "reason": None,
        "uncertainty": round(float(uncertainty), 2),
        "method": method[:_OWN_MAGNITUDE_METHOD_MAX_LENGTH],
        "station_count": count,
        "stations": [
            {
                "station_id": s.get("station_id"),
                "hypocentral_km": s.get("hypocentral_km"),
                "magnitude": s.get("magnitude"),
                "amplitude_mm": s.get("amplitude_mm"),
                "channels": s.get("channels"),
            }
            for s in stations
            if isinstance(s, dict)
        ][:20],
        "calibration_version": version,
        "source": "seismik_seedlink_estimate",
    }


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
        **public_candidate_location(payload),
        "magnitude": payload.get("magnitude_estimate"),
        "magnitude_type": (
            "M~ experimental" if payload.get("magnitude_estimate") is not None else None
        ),
        "magnitude_estimate_status": payload.get(
            "magnitude_estimate_status", "pending_station_calibration"
        ),
        "own_magnitude": _own_magnitude(payload),
        "association_quality": payload.get("association_quality"),
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
        await redis.xrevrange(settings.candidate_stream, count=max(limit * 4, 200)) or [],
    )
    events: list[dict[str, Any]] = []
    magnitudes: dict[str, dict[str, Any]] = {}
    magnitude_rows = cast(
        list[tuple[str, dict[str, str]]],
        await redis.xrevrange(settings.magnitude_stream, count=max(limit * 4, 200)) or [],
    )
    for _identity, magnitude_fields in magnitude_rows:
        try:
            update = json.loads(magnitude_fields.get("payload", "{}"))
            if isinstance(update, dict) and update.get("type") == "magnitude_estimate_update":
                identity = update.get("candidate_event_id")
                if isinstance(identity, str) and identity:
                    magnitudes.setdefault(identity, update)
        except (TypeError, ValueError, AttributeError):
            continue
    for _message_id, fields in raw:
        raw_payload = fields.get("payload")
        if raw_payload is None:
            continue
        try:
            payload = json.loads(raw_payload)
            event = _preliminary_event(payload)
            if event is None:
                continue
            detected_at = datetime.fromisoformat(str(event["detected_at"]).replace("Z", "+00:00"))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if detected_at >= start:
            if update := magnitudes.get(str(event["event_id"])):
                event["own_magnitude"] = _own_magnitude(update)
            events.append(event)
    return events[:limit]


async def official_history(
    sources: str = Query(default="sgc_colombia,usgs_global,emsc_global", max_length=300),
    days: int = Query(default=7, ge=1, le=30),
    minimum_magnitude: float = Query(default=2.5, ge=0, le=10),
    limit: int = Query(default=200, ge=1, le=500),
    settings: AppSettings = Depends(get_app_settings),
    redis: Redis = Depends(get_redis),
    _authorized: ApiPrincipal = Depends(require_mobile_events_read),
) -> dict[str, Any]:
    requested = tuple(sorted({item.strip().lower() for item in sources.split(",") if item.strip()}))
    available = {
        source.id: source
        for source in load_sources(settings.official_sources_path)
        if source.enabled
    }
    include_preliminary = _PRELIMINARY_SOURCE_ID in requested
    selected = [available[source_id] for source_id in requested if source_id in available]
    if not selected and not include_preliminary:
        selected = [
            available[source_id]
            for source_id in ("sgc_colombia", "usgs_global", "emsc_global")
            if source_id in available
        ]

    if include_preliminary:
        now = datetime.now(timezone.utc)
        official: dict[str, Any] = (
            await official_history(
                sources=",".join(source.id for source in selected),
                days=days,
                minimum_magnitude=minimum_magnitude,
                limit=limit,
                settings=settings,
                redis=redis,
                _authorized=_authorized,
            )
            if selected
            else {
                "events": [],
                "sources": [],
                "errors": [],
                "generated_at": now.isoformat(),
                "cached": False,
            }
        )
        preliminary = await _recent_preliminary_events(
            redis,
            settings,
            start=now - timedelta(days=days),
            limit=limit,
        )
        return {
            **official,
            "events": sorted(
                official["events"] + preliminary,
                key=lambda event: event["origin_time"],
                reverse=True,
            )[:limit],
            "sources": official["sources"] + [_PRELIMINARY_SOURCE],
            "official_generated_at": official["generated_at"],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    cache_key = (
        f"cache:seismik:history:associated-v1:{days}:{minimum_magnitude:.1f}:{limit}:"
        f"{','.join(source.id for source in selected)}"
    )
    lock = _history_locks[int.from_bytes(hashlib.sha256(cache_key.encode()).digest()[:2]) % 64]
    async with lock:
        return await _official_cached(
            redis, settings, cache_key, days, minimum_magnitude, limit, selected
        )


@router.get("/history", response_model=None, responses=GEOJSON_RESPONSE)
async def history_endpoint(
    sources: str = Query(default="sgc_colombia,usgs_global,emsc_global", max_length=300),
    days: int = Query(default=7, ge=1, le=30),
    minimum_magnitude: float = Query(default=2.5, ge=0, le=10),
    limit: int = Query(default=200, ge=1, le=500),
    format: OutputFormat = FORMAT_QUERY,
    settings: AppSettings = Depends(get_app_settings),
    redis: Redis = Depends(get_redis),
    _authorized: ApiPrincipal = Depends(require_mobile_events_read),
) -> dict[str, Any] | Response:
    payload = await official_history(
        sources=sources,
        days=days,
        minimum_magnitude=minimum_magnitude,
        limit=limit,
        settings=settings,
        redis=redis,
        _authorized=_authorized,
    )
    if format == "geojson":
        return feature_collection(
            payload["events"],
            id_field="event_id",
            metadata={name: value for name, value in payload.items() if name != "events"},
        )
    return payload


async def _official_cached(
    redis: Redis,
    settings: AppSettings,
    cache_key: str,
    days: int,
    minimum_magnitude: float,
    limit: int,
    selected: list[OfficialSource],
) -> dict[str, Any]:
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
        events.extend(result)
    events = [event for event in associate_events(events) if any(
        report.get("magnitude") is None or report["magnitude"] >= minimum_magnitude
        for report in event["source_reports"]
    )]
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
    # Los candidatos cambian rápidamente y su ventana de seguridad es corta;
    # no se mezclan con la caché de los catálogos oficiales.
    await redis.set(cache_key, json.dumps(payload), ex=settings.official_history_cache_seconds)
    return payload
