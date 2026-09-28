from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from redis.asyncio import Redis

from api.config import AppSettings
from api.dependencies import (
    ApiPrincipal,
    get_app_settings,
    get_redis,
    require_mobile_events_read,
    require_mobile_stations_read,
)

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
    _authorized: ApiPrincipal = Depends(require_mobile_stations_read),
) -> dict[str, list[dict[str, Any]]]:
    try:
        stations = _load_stations(settings.station_catalog_path)
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="Station catalog is unavailable")
    return {"stations": list(stations)}


async def _enforce_showcase_rate(request: Request, redis: Redis, settings: AppSettings) -> None:
    """Ventana de un minuto por IP.

    Es la Always Free API: sin clave no hay cuenta de la que colgar una cuota,
    así que el límite va por IP. No se guarda la IP en claro, sólo su hash, y
    sólo para contar.
    """

    client_host = request.client.host if request.client else "unknown"
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


@router.get("/public/showcase-events")
async def showcase_events(
    request: Request,
    limit: int | None = Query(default=None, ge=1, le=20),
    settings: AppSettings = Depends(get_app_settings),
    redis: Redis = Depends(get_redis),
) -> dict[str, Any]:
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
    events: list[dict[str, Any]] = []
    for _message_id, fields in raw:
        event = json.loads(fields["payload"])
        report = event.get("preferred_report", {})
        magnitude = report.get("magnitude")
        if not isinstance(magnitude, (int, float)) or magnitude < minimum_magnitude:
            continue
        events.append(
            {
                "event_id": event["event_id"],
                "origin_time": report.get("origin_time"),
                "latitude": report.get("latitude"),
                "longitude": report.get("longitude"),
                "magnitude": magnitude,
                "magnitude_type": report.get("magnitude_type"),
                "depth_km": report.get("depth_km"),
                "agency": report.get("agency"),
                "place": report.get("place"),
                "official_url": report.get("official_url"),
            }
        )
        if len(events) >= result_limit:
            break
    return {"events": events, "minimum_magnitude": minimum_magnitude}


@router.get("/events/recent")
async def recent_events(
    settings: AppSettings = Depends(get_app_settings),
    redis: Redis = Depends(get_redis),
    _authorized: ApiPrincipal = Depends(require_mobile_events_read),
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
