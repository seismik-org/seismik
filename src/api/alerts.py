"""Bitácora de alertas emitidas para sincronizar apps que estuvieron sin red.

Una alerta crítica viaja por push, y el push se pierde cuando el teléfono está
apagado, en modo avión o sin datos. Este endpoint deja que la app reconstruya
lo ocurrido cuando vuelve a conectarse, aplicando los mismos filtros que el
dispatcher habría aplicado para ese dispositivo.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query, status
from redis.asyncio import Redis

from api.config import AppSettings
from api.dependencies import (
    DevicePrincipal,
    get_app_settings,
    get_devices,
    get_redis,
    require_device_session,
)
from api.devices_store import DeviceRepository
from api.schemas import AlertLedgerEntry, AlertLedgerPage, DeviceTarget
from dispatcher.policy import ALARM, AlertPolicy

router = APIRouter(
    prefix="/v1/alerts",
    tags=["alerts"],
)


@router.get("/recent", response_model=AlertLedgerPage)
async def recent_alerts(
    device_id: str = Query(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$"),
    since: str | None = Query(
        default=None,
        max_length=64,
        pattern=r"^\d+-\d+$",
        description="Cursor devuelto por una consulta anterior",
    ),
    limit: int | None = Query(default=None, ge=1, le=200),
    devices: DeviceRepository = Depends(get_devices),
    redis: Redis = Depends(get_redis),
    settings: AppSettings = Depends(get_app_settings),
    principal: DevicePrincipal = Depends(require_device_session),
) -> AlertLedgerPage:
    if principal.device_id != device_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Device session mismatch")
    target = await devices.resolve(device_id)
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device is not registered",
        )
    count = limit or settings.alert_recent_limit
    entries = await _read_ledger(redis, settings, since=since, count=count)
    policy = AlertPolicy(redis, settings)
    alerts: list[AlertLedgerEntry] = []
    cursor = since
    for stream_id, entry in entries:
        cursor = stream_id
        payload = _decode_payload(entry)
        if payload is None:
            continue
        critical = _delivery(
            policy,
            target,
            str(entry.get("type")),
            payload,
            critical=entry.get("critical") == "true",
        )
        if critical is None:
            continue
        alerts.append(
            AlertLedgerEntry(
                event_id=str(entry["event_id"]),
                type=str(entry["type"]),
                critical=critical,
                emitted_at=datetime.fromisoformat(
                    str(entry["emitted_at"]).replace("Z", "+00:00")
                ),
                zone_id=payload.get("zone_id"),
                latitude=payload.get("latitude"),
                longitude=payload.get("longitude"),
                magnitude=payload.get("magnitude"),
                depth_km=payload.get("depth_km"),
                place=payload.get("place"),
                agency=payload.get("agency"),
                official_url=payload.get("official_url"),
            )
        )
    return AlertLedgerPage(alerts=tuple(alerts), cursor=cursor)


async def _read_ledger(
    redis: Redis, settings: AppSettings, *, since: str | None, count: int
) -> list[tuple[str, dict[str, str]]]:
    if since:
        return cast(
            list[tuple[str, dict[str, str]]],
            await redis.xrange(settings.alert_ledger_stream, min=f"({since}", count=count),
        )
    newest = cast(
        list[tuple[str, dict[str, str]]],
        await redis.xrevrange(settings.alert_ledger_stream, count=count),
    )
    return list(reversed(newest))


def _decode_payload(entry: dict[str, str]) -> dict[str, Any] | None:
    try:
        decoded = json.loads(entry.get("payload", "{}"))
    except ValueError:
        return None
    return decoded if isinstance(decoded, dict) else None


def _delivery(
    policy: AlertPolicy,
    target: DeviceTarget,
    event_type: str,
    payload: dict[str, Any],
    *,
    critical: bool,
) -> bool | None:
    """Reaplica los filtros del dispatcher sobre un único dispositivo.

    ``None`` si el aviso no era para él; si lo era, si sonó como alarma.
    """

    latitude = _as_float(payload.get("latitude"))
    longitude = _as_float(payload.get("longitude"))
    magnitude = _as_float(payload.get("magnitude"))
    depth_km = _as_float(payload.get("depth_km"))
    if event_type == "official_report_update":
        delivery = policy.classify_official(
            target,
            magnitude=magnitude,
            latitude=latitude,
            longitude=longitude,
            depth_km=depth_km,
            origin_time=payload.get("origin_time"),
        )
        return None if delivery is None else delivery == ALARM
    if policy.filter_critical(
        [target], latitude=latitude, longitude=longitude, magnitude=magnitude, depth_km=depth_km
    ):
        return critical
    return None


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
