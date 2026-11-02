from __future__ import annotations

import hashlib
import json
import logging
import math
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from redis.asyncio import Redis

from api.config import AppSettings
from api.dependencies import (
    ApiPrincipal,
    get_app_settings,
    get_redis,
    require_mobile_events_read,
    require_mobile_stations_read,
)
from api.event_association import associate_events
from api.geojson import FORMAT_QUERY, GEOJSON_RESPONSE, OutputFormat, feature_collection

router = APIRouter(prefix="/v1", tags=["public-monitor"])
LOGGER = logging.getLogger(__name__)

SHOWCASE_FIELDS = (
    "origin_time", "latitude", "longitude", "magnitude", "magnitude_type",
    "depth_km", "agency", "place", "official_url",
)


def _showcase_catalogue(
    events: list[dict[str, Any]], minimum: float, limit: int,
) -> list[dict[str, Any]]:
    """Group public catalogue cards; retain each agency's original solution."""
    reports: list[dict[str, Any]] = []
    identical: dict[tuple[Any, ...], str] = {}
    aliases: dict[str, list[str]] = {}
    rank = {str(event["event_id"]): index for index, event in enumerate(events)}
    for event in events:
        report = event["preferred_report"]
        event_id = str(event["event_id"])
        parts = event_id.split(":")
        source = report.get("source_id") or (
            parts[1] if len(parts) >= 3 and parts[0] == "catalog" else ""
        )
        source = source if isinstance(source, str) else ""
        row = {field: report.get(field) for field in SHOWCASE_FIELDS}
        row.update(event_id=event_id, source_id=source, type=event.get("type"),
                   preliminary=event.get("preliminary", False))
        # Some catalogues expose the exact same solution under two IDs. Only
        # identical complete solutions from that source are aliases, not nearby
        # aftershocks. Keep all IDs without changing the stored stream.
        numbers = [row[key] for key in ("latitude", "longitude", "depth_km", "magnitude")]
        signature = None
        if (
            isinstance(source, str) and source and event_id.startswith("catalog:")
            and row["type"] == "official_report_update" and not row["preliminary"]
            and isinstance(row["origin_time"], str) and row["origin_time"]
            and isinstance(row["magnitude_type"], (str, type(None)))
            and all(isinstance(n, (int, float)) and not isinstance(n, bool)
                    and math.isfinite(n) for n in numbers)
        ):
            signature = (source, row["origin_time"], *numbers, row["magnitude_type"])
        if signature is not None and signature in identical:
            aliases[identical[signature]].append(event_id)
            continue
        if signature is not None:
            identical[signature] = event_id
        aliases[event_id] = [event_id]
        reports.append(row)

    groups = associate_events(reports)
    groups.sort(key=lambda group: min(
        rank[identity] for report in group["source_reports"]
        for identity in aliases[report["event_id"]]
    ))
    cards: list[dict[str, Any]] = []
    for group in groups:
        sources = group["source_reports"]
        eligible = [report for report in sources if (
            isinstance(report.get("magnitude"), (int, float))
            and not isinstance(report["magnitude"], bool)
            and math.isfinite(report["magnitude"])
            and report["magnitude"] >= minimum
        )]
        if not eligible:
            continue
        # Start with an above-threshold report; lower agency estimates remain
        # selectable. Never average magnitudes or combine incompatible scales.
        primary = eligible[0]
        sources = [primary, *(report for report in sources if report is not primary)]
        public_sources = [
            {"event_id": report["event_id"], **{field: report.get(field) for field in SHOWCASE_FIELDS}}
            for report in sources
        ]
        cards.append({
            **public_sources[0], "source_reports": public_sources,
            "related_event_ids": [identity for report in sources
                                  for identity in aliases[report["event_id"]]],
            "association_method": group["association_method"],
        })
        if len(cards) >= limit:
            break
    return cards


def _latest_official_events(raw: list[tuple[str, dict[str, str]]]) -> list[dict[str, Any]]:
    """Consolidate newest-first stream revisions without changing delivery IDs."""
    seen: set[tuple[str, str]] = set()
    events: list[dict[str, Any]] = []
    for _message_id, fields in raw:
        try:
            event = json.loads(fields["payload"])
            if not isinstance(event, dict) or not isinstance(event.get("preferred_report"), dict):
                raise ValueError("Invalid official event")
            event_id = str(event["event_id"])
            report = event["preferred_report"]
            if report.get("source_id") and report.get("official_event_id"):
                identity = (str(report["source_id"]), str(report["official_event_id"]))
            else:
                # Older catalogue rows still have an unambiguous source/event ID.
                stable = re.sub(r":m\d+$", "", event_id) if event_id.startswith("catalog:") else event_id
                identity = ("event", stable)
            if identity in seen:
                continue
            seen.add(identity)
            events.append(event)
        except (KeyError, TypeError, ValueError):
            # One damaged row must not hide the rest of the public catalogue.
            LOGGER.warning("Skipped malformed official stream row")
    return events


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


@router.get("/network/stations", response_model=None, responses=GEOJSON_RESPONSE)
async def network_stations(
    format: OutputFormat = FORMAT_QUERY,
    settings: AppSettings = Depends(get_app_settings),
    _authorized: ApiPrincipal = Depends(require_mobile_stations_read),
) -> dict[str, list[dict[str, Any]]] | Response:
    try:
        stations = _load_stations(settings.station_catalog_path)
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="Station catalog is unavailable")
    if format == "geojson":
        return feature_collection(list(stations), id_field="station_id")
    return {"stations": list(stations)}


async def _enforce_showcase_rate(request: Request, redis: Redis, settings: AppSettings) -> None:
    """Ventana de un minuto por IP.

    Es la Always Free API: sin clave no hay cuenta de la que colgar una cuota,
    así que el límite va por IP. No se guarda la IP en claro, sólo su hash, y
    sólo para contar.
    """

    client_host = request.client.host if request.client else "unknown"
    if request.scope.get("seismik.edge_authenticated"):
        client_host = request.headers.get("X-Seismik-Client-IP") or "unknown"
    bucket = hashlib.sha256(client_host.encode()).hexdigest()[:16]
    window = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
    counter = f"seismik:public-showcase:{bucket}:{window}"

    pipe = redis.pipeline(transaction=True)
    pipe.incr(counter)
    pipe.expire(counter, 120)
    count, _ = await pipe.execute()
    if count > settings.public_showcase_requests_per_minute:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Demasiadas solicitudes; espera un minuto",
            headers={"Retry-After": "60"},
        )


@router.get("/public/showcase-events", response_model=None, responses=GEOJSON_RESPONSE)
async def showcase_events(
    request: Request,
    limit: int | None = Query(default=None, ge=1, le=20),
    format: OutputFormat = FORMAT_QUERY,
    settings: AppSettings = Depends(get_app_settings),
    redis: Redis = Depends(get_redis),
) -> dict[str, Any] | Response:
    """Los últimos sismos confirmados de magnitud considerable, sin clave.

    Es la Seismik Always Free API: respalda el panel "Así se ve Seismik" de la
    portada y, documentada en devs.seismik.org, sirve como puerta de entrada
    sin registro. Misma fuente que usa la app (el stream oficial ya
    procesado), filtrada a un piso fijo de magnitud -no negociable por
    parámetro, a diferencia de /v1/events/history- para que siga siendo
    barata de servir sin clave ni cuota por cuenta.
    """

    await _enforce_showcase_rate(request, redis, settings)

    raw = cast(
        list[tuple[str, dict[str, str]]],
        await redis.xrevrange(settings.official_stream, count=settings.public_showcase_scan_limit),
    )
    minimum_magnitude = settings.public_showcase_minimum_magnitude
    result_limit = limit or settings.public_showcase_limit
    events = _showcase_catalogue(_latest_official_events(raw), minimum_magnitude, result_limit)
    if format == "geojson":
        return feature_collection(
            events, id_field="event_id", metadata={"minimum_magnitude": minimum_magnitude}
        )
    return {"events": events, "minimum_magnitude": minimum_magnitude}


@router.get("/events/recent", response_model=None, responses=GEOJSON_RESPONSE)
async def recent_events(
    format: OutputFormat = FORMAT_QUERY,
    settings: AppSettings = Depends(get_app_settings),
    redis: Redis = Depends(get_redis),
    _authorized: ApiPrincipal = Depends(require_mobile_events_read),
) -> dict[str, list[dict[str, Any]]] | Response:
    raw = cast(
        list[tuple[str, dict[str, str]]],
        await redis.xrevrange(
            settings.official_stream,
            count=max(settings.public_recent_event_limit, settings.public_showcase_scan_limit),
        ),
    )
    events: list[dict[str, Any]] = []
    for event in _latest_official_events(raw):
        report = event.get("preferred_report", {})
        reports = [
            {**item, "event_id": f"{item.get('source_id', 'official')}:{item.get('official_event_id', event['event_id'])}"}
            for item in (event.get("reports") or [report])
            if isinstance(item, dict)
        ]
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
                "source_id": report.get("source_id"),
                "official_event_id": report.get("official_event_id"),
                "magnitude_type": report.get("magnitude_type"),
                "review_status": report.get("review_status"),
                "source_reports": reports,
                "related_event_ids": [event["event_id"], *[item["event_id"] for item in reports]],
            }
        )
        if len(events) >= settings.public_recent_event_limit:
            break
    if format == "geojson":
        return feature_collection(events, id_field="event_id")
    return {"events": events}
