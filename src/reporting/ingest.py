from __future__ import annotations

import time
from typing import TypeVar

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, ValidationError
from redis.asyncio import Redis

from api.bus import RedisEventBus
from api.config import AppSettings
from api.dependencies import get_app_settings, get_bus, get_devices, get_redis
from api.devices_store import DeviceRepository
from api.security import derive_crowd_token, verify_signature
from reporting.agencies import routes_for
from reporting.schemas import (
    AgencyRoute,
    DamageReport,
    FeltReport,
    LocationPrecision,
    ReportAccepted,
)

router = APIRouter(prefix="/v1/reports", tags=["citizen-reports"])
ReportModel = TypeVar("ReportModel", bound=BaseModel)


@router.get("/agencies", response_model=tuple[AgencyRoute, ...])
async def list_reporting_agencies(
    country_code: str = Query(min_length=2, max_length=2),
    official_event_id: str | None = Query(default=None, min_length=1, max_length=128),
) -> tuple[AgencyRoute, ...]:
    """Return user-selectable official forms; no report is submitted here."""
    return routes_for(country_code, official_event_id)


async def _ingest_report(
    request: Request,
    *,
    model: type[ReportModel],
    stream: str,
    timestamp: str | None,
    signature: str | None,
    bus: RedisEventBus,
    devices: DeviceRepository,
    redis: Redis,
    settings: AppSettings,
) -> tuple[BaseModel, bool, str | None]:
    body = await request.body()
    try:
        report = model.model_validate_json(body)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    device_id = str(getattr(report, "device_id"))
    selected_agencies = tuple(getattr(report, "selected_agency_ids", ()))
    if selected_agencies:
        available = {
            route.agency_id
            for route in routes_for(
                str(getattr(report, "country_code")),
                getattr(report, "official_event_id", None),
            )
        }
        unknown = sorted(set(selected_agencies) - available)
        if unknown:
            raise HTTPException(
                status_code=422,
                detail={"unknown_agency_ids": unknown},
            )
    if not await devices.exists(device_id):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown device")
    if settings.integrity_verification_enabled and not await devices.is_integrity_verified(device_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Citizen reporting requires verified device integrity",
        )
    secret = derive_crowd_token(settings.crowd_master_secret.get_secret_value(), device_id)
    verify_signature(
        secret=secret,
        timestamp=timestamp,
        signature=signature,
        body=body,
        max_skew_seconds=settings.webhook_max_skew_seconds,
    )
    minute = int(time.time() // 60)
    rate_key = f"seismik:reports:rate:{device_id}:{minute}"
    pipe = redis.pipeline(transaction=True)
    pipe.incr(rate_key)
    pipe.expire(rate_key, 120)
    count, _ = await pipe.execute()
    if int(count) > settings.report_rate_limit_per_minute:
        raise HTTPException(status_code=429, detail="Report rate exceeded")

    payload = report.model_dump(mode="json")
    precision = getattr(report, "location_precision")
    if precision is LocationPrecision.APPROXIMATE:
        payload["latitude"] = round(float(payload["latitude"]), 2)
        payload["longitude"] = round(float(payload["longitude"]), 2)
        payload["location_accuracy_m"] = None
    payload["event_id"] = str(getattr(report, "report_id"))
    result = await bus.publish_once(stream, payload)
    return report, result.accepted, result.stream_id


@router.post("/felt", response_model=ReportAccepted, status_code=202)
async def submit_felt_report(
    request: Request,
    x_timestamp: str | None = Header(default=None, alias="X-Seismik-Timestamp"),
    x_signature: str | None = Header(default=None, alias="X-Seismik-Signature"),
    bus: RedisEventBus = Depends(get_bus),
    devices: DeviceRepository = Depends(get_devices),
    redis: Redis = Depends(get_redis),
    settings: AppSettings = Depends(get_app_settings),
) -> ReportAccepted:
    raw, accepted, stream_id = await _ingest_report(
        request,
        model=FeltReport,
        stream=settings.felt_reports_stream,
        timestamp=x_timestamp,
        signature=x_signature,
        bus=bus,
        devices=devices,
        redis=redis,
        settings=settings,
    )
    report = FeltReport.model_validate(raw)
    agency_routes = (
        routes_for(
            report.country_code,
            report.official_event_id,
            report.selected_agency_ids or None,
        )
        if report.share_with_official_agencies
        else ()
    )
    return ReportAccepted(
        accepted=accepted,
        duplicate=not accepted,
        stream_id=stream_id,
        report_id=report.report_id,
        stored_location_precision=report.location_precision,
        agency_routes=agency_routes,
        notice=(
            "Stored by Seismik. Official agencies require the user to complete their form; "
            "Seismik did not submit it automatically."
        ),
    )


@router.post("/damage", response_model=ReportAccepted, status_code=202)
async def submit_damage_report(
    request: Request,
    x_timestamp: str | None = Header(default=None, alias="X-Seismik-Timestamp"),
    x_signature: str | None = Header(default=None, alias="X-Seismik-Signature"),
    bus: RedisEventBus = Depends(get_bus),
    devices: DeviceRepository = Depends(get_devices),
    redis: Redis = Depends(get_redis),
    settings: AppSettings = Depends(get_app_settings),
) -> ReportAccepted:
    raw, accepted, stream_id = await _ingest_report(
        request,
        model=DamageReport,
        stream=settings.damage_reports_stream,
        timestamp=x_timestamp,
        signature=x_signature,
        bus=bus,
        devices=devices,
        redis=redis,
        settings=settings,
    )
    report = DamageReport.model_validate(raw)
    agency_routes = (
        routes_for(
            report.country_code,
            report.official_event_id,
            report.selected_agency_ids or None,
        )
        if report.share_with_official_agencies
        else ()
    )
    return ReportAccepted(
        accepted=accepted,
        duplicate=not accepted,
        stream_id=stream_id,
        report_id=report.report_id,
        stored_location_precision=report.location_precision,
        emergency_action_recommended=report.requires_emergency_action,
        agency_routes=agency_routes,
        notice=(
            "This is not an emergency-service request. Contact local emergency services for "
            "injuries, trapped people, fire, gas leaks, collapse or immediate danger."
        ),
    )
