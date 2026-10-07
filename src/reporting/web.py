from __future__ import annotations

import hashlib
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from redis.asyncio import Redis

from api.bus import RedisEventBus
from api.config import AppSettings
from api.dependencies import get_app_settings, get_bus, get_redis
from reporting.agencies import routes_for
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
        "turnstile_required": not bypass,
    }


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
    available = routes_for(report.country_code, report.official_event_id)
    if set(report.selected_agency_ids) - {route.agency_id for route in available}:
        raise HTTPException(422, "Organismo desconocido")
    payload = report.model_dump(mode="json")
    if report.location_precision == LocationPrecision.APPROXIMATE:
        payload["latitude"] = round(report.latitude, 2)
        payload["longitude"] = round(report.longitude, 2)
        payload["location_accuracy_m"] = None
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
            report.country_code, report.official_event_id, report.selected_agency_ids or None
        )
        if report.share_with_official_agencies
        else (),
        notice="Seismik recibió el reporte. Los organismos oficiales sólo reciben información "
        "cuando completas sus formularios; no enviamos el reporte automáticamente.",
    )
