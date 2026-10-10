"""admin.seismik.org: teléfonos de prueba de la beta y simulacros dirigidos.

Un simulacro sólo llega a teléfonos que el administrador inscribió antes; nunca
a la población, ni a webhooks, X, Facebook ni familias. Llega marcado como
SIMULACRO (`drill-…`, la misma marca que ya reconocen las apps). Inscribir,
quitar y enviar piden un código MFA nuevo y quedan en la auditoría.
"""
from __future__ import annotations

import json
import re
import secrets
from datetime import datetime, timezone
from typing import Any, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from redis.asyncio import Redis

from api.admin_security import digest, rate, require_action, require_admin
from api.beta_phones import DRILL_INDEX_KEY, DRILL_KEY_PREFIX, PHONES_KEY, digest16, phone_ref
from api.config import AppSettings
from api.dependencies import get_app_settings, get_redis
from api.devices_store import DeviceRepository
from eew.simulation import PROFILES

router = APIRouter(prefix="/v1/admin", tags=["admin-beta"])

MAX_PHONES = 50
MAX_DRILL_TARGETS = 10
DRILLS_PER_HOUR = 6
KEEP_DRILLS = 50
DRILL_TTL = 7 * 86_400
REF = r"^[0-9a-f]{16}$"
REF_PATTERN = re.compile(REF)


def drill_action(scenario: str, critical: bool, refs: list[str]) -> str:
    """Lo que el MFA aprueba: ni otro escenario ni otros teléfonos."""

    return f"drill:{scenario}:{'critical' if critical else 'notice'}:{digest16(','.join(sorted(refs)))}"


class PhoneIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    device_id: str = Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    label: str = Field(min_length=1, max_length=40)


class DrillIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario: Literal["bogota", "pacifico", "atacama"]
    critical: StrictBool
    refs: list[str] = Field(min_length=1, max_length=MAX_DRILL_TARGETS)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _audit(redis: Redis, settings: AppSettings, fields: dict[str, str]) -> None:
    await redis.xadd(settings.developer_audit_stream, cast(dict[Any, Any], {**fields, "at": _now()}),
                     maxlen=settings.stream_maxlen, approximate=True)


async def _phones(redis: Redis) -> list[dict[str, Any]]:
    devices = DeviceRepository(redis)
    result = []
    stored = cast(dict[str, str], await redis.hgetall(PHONES_KEY))
    for ref, raw in sorted(stored.items()):
        try:
            record = json.loads(raw)
            device_id = str(record["device_id"])
        except (ValueError, KeyError, TypeError):
            continue
        fields = cast(dict[str, str], await redis.hgetall(f"seismik:device:{device_id}"))
        target = await devices.resolve(device_id)
        result.append({
            "ref": str(ref), "label": str(record.get("label", "")), "suffix": device_id[-4:],
            "platform": fields.get("platform") or None, "registered": bool(fields),
            "push_ready": target is not None,
            "critical_alerts": bool(target and target.critical_alerts_authorized),
            "added_at": record.get("added_at"),
        })
    return result


@router.get("/beta-phones")
async def beta_phones(
    response: Response, admin: str = Depends(require_admin), redis: Redis = Depends(get_redis),
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    return {"phones": await _phones(redis), "scenarios": [
        {"id": name, "place": profile.place, "magnitude": profile.magnitude} for name, profile in PROFILES.items()
    ], "max_phones": MAX_PHONES}


@router.post("/beta-phones", status_code=201)
async def enroll_phone(
    phone: PhoneIn, request: Request, response: Response,
    admin: str = Depends(require_admin), redis: Redis = Depends(get_redis),
    settings: AppSettings = Depends(get_app_settings),
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    ref = phone_ref(phone.device_id)
    if not await redis.exists(f"seismik:device:{phone.device_id}"):
        raise HTTPException(404, "Ese identificador no está registrado. Abre la app con las notificaciones activas y copia el identificador de nuevo.")
    if await redis.hexists(PHONES_KEY, ref):
        raise HTTPException(409, "Ese teléfono ya está inscrito")
    if await redis.hlen(PHONES_KEY) >= MAX_PHONES:
        raise HTTPException(409, f"La beta admite hasta {MAX_PHONES} teléfonos")
    await rate(redis, digest(admin), "beta", 30, 3600)
    await require_action(request, redis, f"beta:add:{ref}")
    record = {"device_id": phone.device_id, "label": phone.label.strip(), "added_by": admin, "added_at": _now()}
    if not await redis.hsetnx(PHONES_KEY, ref, json.dumps(record, ensure_ascii=False)):
        raise HTTPException(409, "Ese teléfono ya está inscrito")
    await _audit(redis, settings, {"action": "beta_phone.enrolled", "ref": ref, "by": admin})
    return {"phones": await _phones(redis)}


@router.delete("/beta-phones/{ref}")
async def remove_phone(
    request: Request, response: Response, ref: str = Path(pattern=REF),
    admin: str = Depends(require_admin), redis: Redis = Depends(get_redis),
    settings: AppSettings = Depends(get_app_settings),
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    if not await redis.hexists(PHONES_KEY, ref):
        raise HTTPException(404, "Teléfono no inscrito")
    await rate(redis, digest(admin), "beta", 30, 3600)
    await require_action(request, redis, f"beta:remove:{ref}")
    await redis.hdel(PHONES_KEY, ref)
    await _audit(redis, settings, {"action": "beta_phone.removed", "ref": ref, "by": admin})
    return {"phones": await _phones(redis)}


async def _drills(redis: Redis) -> list[dict[str, Any]]:
    ids = await redis.zrevrange(DRILL_INDEX_KEY, 0, 9)
    drills = []
    for drill_id in ids:
        data = cast(dict[str, str], await redis.hgetall(DRILL_KEY_PREFIX + str(drill_id)))
        if data:
            drills.append({"id": str(drill_id), **data})
    return drills


@router.get("/drills")
async def drills(
    response: Response, admin: str = Depends(require_admin), redis: Redis = Depends(get_redis),
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    return {"drills": await _drills(redis)}


@router.post("/drills", status_code=202)
async def send_drill(
    body: DrillIn, request: Request, response: Response,
    admin: str = Depends(require_admin), redis: Redis = Depends(get_redis),
    settings: AppSettings = Depends(get_app_settings),
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    refs = sorted(set(body.refs))
    devices = DeviceRepository(redis)
    device_ids: list[str] = []
    for ref in refs:
        if not REF_PATTERN.fullmatch(ref):
            raise HTTPException(422, "Teléfono no válido")
        raw = await redis.hget(PHONES_KEY, ref)
        if not raw:
            raise HTTPException(409, "Uno de los teléfonos ya no está inscrito")
        device_id = str(json.loads(raw)["device_id"])
        if await devices.resolve(device_id) is None:
            raise HTTPException(409, "Uno de los teléfonos no tiene notificaciones listas; ábrelo en la app e inténtalo de nuevo")
        device_ids.append(device_id)
    await rate(redis, digest(admin), "drill", DRILLS_PER_HOUR, 3600)
    await require_action(request, redis, drill_action(body.scenario, body.critical, refs))

    profile = PROFILES[body.scenario]
    drill_id = "drill-" + secrets.token_hex(8)
    now = _now()
    event = {
        "type": "admin_drill", "event_id": drill_id, "device_ids": device_ids, "critical": body.critical,
        "scenario": body.scenario, "requested_by": admin, "requested_at": now,
        "preferred_report": {
            "official_event_id": drill_id, "source_id": "simulation", "agency": "Simulacro Seismik",
            "attribution": "Simulacro de Seismik", "place": profile.place,
            "latitude": profile.latitude, "longitude": profile.longitude, "magnitude": profile.magnitude,
            "depth_km": profile.depth_km, "origin_time": now, "jurisdiction": profile.country_code,
            "official_url": None,
        },
    }
    pipe = redis.pipeline(transaction=True)
    pipe.hset(DRILL_KEY_PREFIX + drill_id, mapping={
        "status": "queued", "scenario": body.scenario, "critical": "true" if body.critical else "false",
        "targets": str(len(device_ids)), "by": admin, "at": now,
    })
    pipe.expire(DRILL_KEY_PREFIX + drill_id, DRILL_TTL)
    pipe.zadd(DRILL_INDEX_KEY, {drill_id: datetime.now(timezone.utc).timestamp()})
    pipe.zremrangebyrank(DRILL_INDEX_KEY, 0, -(KEEP_DRILLS + 1))
    pipe.xadd(settings.admin_drill_stream, {"payload": json.dumps(event, ensure_ascii=False, separators=(",", ":"))},
              maxlen=1_000, approximate=True)
    pipe.xadd(settings.developer_audit_stream, {
        "action": "drill.requested", "drill_id": drill_id, "scenario": body.scenario,
        "critical": "true" if body.critical else "false", "targets": str(len(device_ids)), "by": admin, "at": now,
    }, maxlen=settings.stream_maxlen, approximate=True)
    await pipe.execute()
    return {"id": drill_id, "drills": await _drills(redis)}
