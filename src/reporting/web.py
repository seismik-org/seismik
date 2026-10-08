from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timedelta, timezone
from typing import cast

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from redis.asyncio import Redis

from api.bus import RedisEventBus
from api.config import AppSettings
from api.dependencies import get_app_settings, get_bus, get_redis
from reporting.agencies import routes_for
from reporting.plausibility import assess
from reporting.schemas import LocationPrecision, ReportAccepted, WebFeltReport

router = APIRouter(prefix="/web")


def client_ip(request: Request) -> str:
    # Only the authenticated edge may supply a visitor's IP.
    if request.scope.get("seismik.edge_authenticated"):
        return request.headers.get("X-Seismik-Client-IP") or "unknown"
    return request.client.host if request.client else "unknown"


@router.get("/config")
async def web_config(response: Response, settings: AppSettings = Depends(get_app_settings)) -> dict:
    response.headers["Cache-Control"] = "no-store"
    site = settings.turnstile_site_key.strip()
    secret = settings.turnstile_secret_key.get_secret_value().strip()
    bypass = settings.environment.lower() == "development" and not site and not secret
    return {
        "enabled": bool(site and secret) or bypass,
        "site_key": site or None,
        "action": "felt_report",
        "google_maps_api_key": settings.google_maps_web_api_key.strip() or None,
        "turnstile_required": not bypass,
    }


async def recent_web_events(redis: Redis, settings: AppSettings) -> list[dict]:
    # Bound public reads, retain the latest revision of each official event.
    raw = cast(
        list[tuple[str, dict[str, str]]],
        await redis.xrevrange(settings.official_stream, count=5000),
    )
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    seen: set[str] = set()
    events: list[dict] = []
    for _, fields in raw:
        try:
            event = json.loads(fields["payload"])
            report = event["preferred_report"]
            event_id = event["event_id"]
            origin = datetime.fromisoformat(report["origin_time"].replace("Z", "+00:00"))
            if event_id in seen:
                continue
            seen.add(event_id)
            if origin < cutoff:
                continue
            events.append(
                {
                    "event_id": event_id,
                    **{
                        name: report.get(name)
                        for name in (
                            "origin_time",
                            "latitude",
                            "longitude",
                            "magnitude",
                            "depth_km",
                            "agency",
                            "place",
                            "official_event_id",
                            "source_id",
                        )
                    },
                }
            )
        except (KeyError, ValueError, TypeError):
            continue
    return events


async def official_events(redis: Redis, settings: AppSettings) -> dict[str, dict]:
    """Última revisión de cada sismo oficial reciente, por `event_id`, sin límite de días.

    La app puede reportar sismos más antiguos que el catálogo web de siete días.
    """
    raw = cast(
        list[tuple[str, dict[str, str]]],
        await redis.xrevrange(settings.official_stream, count=5000),
    )
    index: dict[str, dict] = {}
    for _, fields in raw:
        try:
            event = json.loads(fields["payload"])
            event_id = str(event["event_id"])
            report = event["preferred_report"]
        except (KeyError, ValueError, TypeError):
            continue
        if event_id in index or not isinstance(report, dict):
            continue
        index[event_id] = {
            "event_id": event_id,
            **{
                name: report.get(name)
                for name in (
                    "origin_time",
                    "latitude",
                    "longitude",
                    "magnitude",
                    "depth_km",
                    "agency",
                    "place",
                    "official_event_id",
                    "official_url",
                )
            },
        }
    return index


@router.get("/events")
async def web_events(
    request: Request,
    response: Response,
    q: str = Query(default="", max_length=80),
    settings: AppSettings = Depends(get_app_settings),
    redis: Redis = Depends(get_redis),
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    bucket = hashlib.sha256(client_ip(request).encode()).hexdigest()
    key = f"seismik:reports:web:catalog:{bucket}:{int(time.time() // 60)}"
    pipe = redis.pipeline(transaction=True)
    pipe.incr(key)
    pipe.expire(key, 120)
    count, _ = await pipe.execute()
    if int(count) > settings.public_showcase_requests_per_minute:
        raise HTTPException(429, "Demasiadas consultas; espera un minuto")
    events = await recent_web_events(redis, settings)
    matches: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for event in events:
        identity = (
            event.get("source_id") or event.get("agency") or "",
            event.get("official_event_id") or event["event_id"],
        )
        if identity in seen:
            continue
        seen.add(identity)
        if q.casefold() not in (event.get("place") or "").casefold():
            continue
        matches.append(event)
    matches.sort(
        key=lambda event: datetime.fromisoformat(event["origin_time"].replace("Z", "+00:00")),
        reverse=True,
    )
    return {"events": matches[:200], "period_days": 7}


async def verify_turnstile(token: str | None, settings: AppSettings) -> None:
    site = settings.turnstile_site_key.strip()
    secret = settings.turnstile_secret_key.get_secret_value().strip()
    if not site and not secret and settings.environment.lower() == "development":
        return
    if not site or not secret:
        raise HTTPException(503, "La verificación de seguridad no está configurada")
    if not token:
        raise HTTPException(403, "Completa la verificación de seguridad")
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.post(
                "https://challenges.cloudflare.com/turnstile/v0/siteverify",
                data={"secret": secret, "response": token},
            )
            response.raise_for_status()
            result = response.json()
        if not isinstance(result, dict):
            raise ValueError("Invalid verification response")
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(503, "No fue posible verificar la solicitud") from exc
    if (
        result.get("success") is not True
        or result.get("action") != "felt_report"
        or result.get("hostname") != settings.felt_web_hostname
    ):
        raise HTTPException(403, "La verificación de seguridad no fue válida")


@router.post("/felt", response_model=ReportAccepted, status_code=202)
async def submit_web_felt(
    report: WebFeltReport,
    request: Request,
    response: Response,
    settings: AppSettings = Depends(get_app_settings),
    redis: Redis = Depends(get_redis),
    bus: RedisEventBus = Depends(get_bus),
) -> ReportAccepted:
    response.headers["Cache-Control"] = "no-store"
    bucket = hashlib.sha256(client_ip(request).encode()).hexdigest()
    key = f"seismik:reports:web:rate:{bucket}:{int(time.time() // 60)}"
    pipe = redis.pipeline(transaction=True)
    pipe.incr(key)
    pipe.expire(key, 120)
    count, _ = await pipe.execute()
    if int(count) > settings.report_rate_limit_per_minute:
        raise HTTPException(429, "Demasiados reportes; espera un minuto")
    await verify_turnstile(report.turnstile_token, settings)
    selected = next(
        (
            event
            for event in await recent_web_events(redis, settings)
            if event["event_id"] == report.earthquake_event_id
        ),
        None,
    )
    if selected is None:
        raise HTTPException(422, "Selecciona un sismo disponible en el catálogo reciente")
    if report.official_event_id and report.official_event_id != selected["official_event_id"]:
        raise HTTPException(422, "El identificador oficial no corresponde al sismo seleccionado")
    available = routes_for(report.country_code, selected["official_event_id"])
    if set(report.selected_agency_ids) - {route.agency_id for route in available}:
        raise HTTPException(422, "Organismo desconocido")
    payload = report.model_dump(mode="json")
    payload["official_event_id"] = selected["official_event_id"]
    if report.location_precision == LocationPrecision.APPROXIMATE:
        payload["latitude"] = round(report.latitude, 2)
        payload["longitude"] = round(report.longitude, 2)
        payload["location_accuracy_m"] = None
    # Se calcula con la ubicación ya redondeada: es la que queda guardada.
    payload["plausibility"] = assess(payload, selected)
    # Namespace browser IDs so they cannot suppress a mobile report in the bus.
    payload["event_id"] = f"web:{report.report_id}"
    result = await bus.publish_once(settings.felt_reports_stream, payload)
    return ReportAccepted(
        accepted=result.accepted,
        duplicate=not result.accepted,
        stream_id=result.stream_id,
        report_id=report.report_id,
        stored_location_precision=report.location_precision,
        agency_routes=routes_for(
            report.country_code, selected["official_event_id"], report.selected_agency_ids or None
        )
        if report.share_with_official_agencies
        else (),
        notice="Seismik recibió el reporte. Los organismos oficiales sólo reciben información "
        "cuando completas sus formularios; no enviamos el reporte automáticamente.",
    )
