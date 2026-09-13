"""Búsqueda de familiares: estado y ubicación tras un sismo.

Cada círculo agrupa cuentas Seismik, no teléfonos. Tras un sismo, cada persona
avisa si está bien o necesita ayuda; ese mismo toque comparte su ubicación con
el círculo por unas horas y envía un aviso push a sus familiares.

No es rastreo en segundo plano ni sustituye a los canales de emergencia. Nada
se comparte sin una acción explícita, la ubicación aproximada se redondea en el
servidor y tanto la ubicación como el estado vencen solos.
"""
from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from redis.asyncio import Redis

from api.accounts import (
    AccountPrincipal,
    link_device,
    require_account_session,
    unlink_device,
)
from api.dependencies import DevicePrincipal, get_redis, require_device_session

router = APIRouter(prefix="/v1/family", tags=["family-safety"])
account_router = APIRouter(prefix="/v1/account", tags=["account"])

_INVITE_TTL_SECONDS = 86_400
_CIRCLE_TTL_SECONDS = 31_536_000  # 365 días sin actividad.
# Pulsar «Estoy bien» dos veces seguidas no debe despertar dos veces a la
# familia. Cambiar a «Necesito ayuda» sí avisa de inmediato.
_NOTIFY_THROTTLE_SECONDS = 120


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CircleCreate(_StrictModel):
    display_name: str = Field(min_length=1, max_length=36)
    circle_name: str = Field(default="Mi círculo", min_length=1, max_length=48)


class InviteCreate(_StrictModel):
    # El código es intencionalmente de una sola invitación y expira en 24 h.
    display_name: str = Field(min_length=1, max_length=36)


class CircleJoin(_StrictModel):
    invite_code: str = Field(min_length=12, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    display_name: str = Field(min_length=1, max_length=36)


class LocationPoint(_StrictModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    precision: Literal["approximate", "precise"] = "approximate"
    precise_location_consent: bool = False

    @model_validator(mode="after")
    def explicit_precise_consent(self) -> "LocationPoint":
        if self.precision == "precise" and not self.precise_location_consent:
            raise ValueError("Precise sharing requires explicit consent")
        return self


class LocationShare(LocationPoint):
    share_minutes: int = Field(default=60, ge=15, le=240)


class StatusReport(_StrictModel):
    status: Literal["safe", "need_help"]
    message: str | None = Field(default=None, max_length=140)
    # Sismo que motivó el reporte, para que la familia sepa a qué responde.
    event_id: str | None = Field(default=None, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    location: LocationPoint | None = None
    # Tras un sismo la familia necesita saber dónde está cada quien durante
    # horas, no minutos; por defecto se comparte 4 horas.
    share_minutes: int = Field(default=240, ge=15, le=720)

    @field_validator("message")
    @classmethod
    def blank_message_is_none(cls, value: str | None) -> str | None:
        return value or None


def _circle_key(circle_id: str) -> str:
    return f"seismik:family:circle:{circle_id}"


def family_members_key(circle_id: str) -> str:
    """Integrantes del círculo: cuentas y, hasta que migren, teléfonos antiguos."""
    return f"seismik:family:members:{circle_id}"


def _member_key(circle_id: str, member_id: str) -> str:
    return f"seismik:family:member:{circle_id}:{member_id}"


def _location_key(circle_id: str, member_id: str) -> str:
    return f"seismik:family:location:{circle_id}:{member_id}"


def _status_key(circle_id: str, member_id: str) -> str:
    return f"seismik:family:status:{circle_id}:{member_id}"


def _account_circle_key(uid: str) -> str:
    return f"seismik:family:account:{uid}"


def _legacy_device_circle_key(device_id: str) -> str:
    """Círculos creados antes de exigir cuenta, ligados a un teléfono."""
    return f"seismik:family:device:{device_id}"


def _public_member_id(circle_id: str, member_id: str) -> str:
    # La app necesita un identificador estable por integrante, pero no el
    # identificador de la cuenta en Google ni el del teléfono.
    return hashlib.sha256(f"{circle_id}:{member_id}".encode()).hexdigest()[:16]


async def _circle_for_account(redis: Redis, uid: str) -> str:
    circle_id = await redis.get(_account_circle_key(uid))
    if not circle_id or not await redis.exists(_circle_key(str(circle_id))):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No family circle found")
    return str(circle_id)


async def _touch_circle(redis: Redis, circle_id: str) -> None:
    pipe = redis.pipeline(transaction=True)
    pipe.expire(_circle_key(circle_id), _CIRCLE_TTL_SECONDS)
    pipe.expire(family_members_key(circle_id), _CIRCLE_TTL_SECONDS)
    await pipe.execute()


async def _store_location(
    redis: Redis, circle_id: str, member_id: str, point: LocationPoint, minutes: int
) -> dict[str, object]:
    latitude, longitude = point.latitude, point.longitude
    # La precisión aproximada se degrada en el servidor; nunca se conserva la
    # coordenada exacta para poder reconstruirla después.
    if point.precision == "approximate":
        latitude, longitude = round(latitude, 2), round(longitude, 2)
    now = datetime.now(timezone.utc)
    data: dict[str, object] = {
        "latitude": latitude,
        "longitude": longitude,
        "precision": point.precision,
        "shared_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=minutes)).isoformat(),
    }
    await redis.set(_location_key(circle_id, member_id), json.dumps(data), ex=minutes * 60)
    return data


@router.post("/circle", status_code=status.HTTP_201_CREATED)
async def create_circle(
    payload: CircleCreate,
    redis: Redis = Depends(get_redis),
    account: AccountPrincipal = Depends(require_account_session),
) -> dict[str, str]:
    existing = await redis.get(_account_circle_key(account.uid))
    if existing and await redis.exists(_circle_key(str(existing))):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Account already belongs to a family circle")
    circle_id = secrets.token_urlsafe(18)
    now = datetime.now(timezone.utc).isoformat()
    pipe = redis.pipeline(transaction=True)
    pipe.hset(
        _circle_key(circle_id),
        mapping={
            "circle_id": circle_id,
            "circle_name": payload.circle_name,
            "owner_uid": account.uid,
            "created_at": now,
        },
    )
    pipe.sadd(family_members_key(circle_id), account.uid)
    pipe.hset(_member_key(circle_id, account.uid), mapping={"display_name": payload.display_name, "joined_at": now})
    pipe.set(_account_circle_key(account.uid), circle_id, ex=_CIRCLE_TTL_SECONDS)
    pipe.expire(_circle_key(circle_id), _CIRCLE_TTL_SECONDS)
    pipe.expire(family_members_key(circle_id), _CIRCLE_TTL_SECONDS)
    pipe.expire(_member_key(circle_id, account.uid), _CIRCLE_TTL_SECONDS)
    await pipe.execute()
    return {"circle_id": circle_id, "circle_name": payload.circle_name}


@router.post("/circle/invitations", status_code=status.HTTP_201_CREATED)
async def create_invitation(
    payload: InviteCreate,
    redis: Redis = Depends(get_redis),
    account: AccountPrincipal = Depends(require_account_session),
) -> dict[str, object]:
    circle_id = await _circle_for_account(redis, account.uid)
    owner = await redis.hget(_circle_key(circle_id), "owner_uid")
    if owner != account.uid:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the circle owner can invite")
    code = secrets.token_urlsafe(18)
    await redis.set(
        f"seismik:family:invite:{code}",
        json.dumps({"circle_id": circle_id, "created_by": account.uid, "display_name": payload.display_name}),
        ex=_INVITE_TTL_SECONDS,
    )
    return {"invite_code": code, "expires_in_minutes": _INVITE_TTL_SECONDS // 60}


@router.post("/join")
async def join_circle(
    payload: CircleJoin,
    redis: Redis = Depends(get_redis),
    account: AccountPrincipal = Depends(require_account_session),
) -> dict[str, str]:
    existing = await redis.get(_account_circle_key(account.uid))
    if existing and await redis.exists(_circle_key(str(existing))):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Account already belongs to a family circle")
    raw = await redis.get(f"seismik:family:invite:{payload.invite_code}")
    if not raw:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation is invalid or expired")
    invitation = json.loads(raw)
    circle_id = str(invitation["circle_id"])
    if not await redis.exists(_circle_key(circle_id)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Family circle no longer exists")
    now = datetime.now(timezone.utc).isoformat()
    pipe = redis.pipeline(transaction=True)
    pipe.sadd(family_members_key(circle_id), account.uid)
    pipe.hset(_member_key(circle_id, account.uid), mapping={"display_name": payload.display_name, "joined_at": now})
    pipe.set(_account_circle_key(account.uid), circle_id, ex=_CIRCLE_TTL_SECONDS)
    pipe.delete(f"seismik:family:invite:{payload.invite_code}")
    pipe.expire(_member_key(circle_id, account.uid), _CIRCLE_TTL_SECONDS)
    await pipe.execute()
    await _touch_circle(redis, circle_id)
    return {"circle_id": circle_id, "circle_name": str(await redis.hget(_circle_key(circle_id), "circle_name"))}


@router.put("/location")
async def share_location(
    payload: LocationShare,
    redis: Redis = Depends(get_redis),
    account: AccountPrincipal = Depends(require_account_session),
) -> dict[str, object]:
    circle_id = await _circle_for_account(redis, account.uid)
    await _store_location(redis, circle_id, account.uid, payload, payload.share_minutes)
    await _touch_circle(redis, circle_id)
    return {"sharing": True, "expires_in_minutes": payload.share_minutes, "precision": payload.precision}


@router.delete("/location", status_code=status.HTTP_204_NO_CONTENT)
async def stop_sharing_location(
    redis: Redis = Depends(get_redis),
    account: AccountPrincipal = Depends(require_account_session),
) -> None:
    circle_id = await _circle_for_account(redis, account.uid)
    await redis.delete(_location_key(circle_id, account.uid))


@router.put("/status")
async def report_status(
    payload: StatusReport,
    request: Request,
    redis: Redis = Depends(get_redis),
    account: AccountPrincipal = Depends(require_account_session),
) -> dict[str, object]:
    """«Estoy bien» o «Necesito ayuda», con la ubicación si la persona la da."""

    settings = request.app.state.settings
    circle_id = await _circle_for_account(redis, account.uid)
    now = datetime.now(timezone.utc)
    ttl = int(settings.family_status_ttl_seconds)
    report: dict[str, object] = {
        "status": payload.status,
        "message": payload.message,
        "event_id": payload.event_id,
        "reported_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=ttl)).isoformat(),
    }
    await redis.set(_status_key(circle_id, account.uid), json.dumps(report), ex=ttl)
    sharing = payload.location is not None
    if payload.location is not None:
        await _store_location(redis, circle_id, account.uid, payload.location, payload.share_minutes)
    await _touch_circle(redis, circle_id)
    notified = await _enqueue_status_notification(redis, settings, circle_id, account, report)
    return {
        "status": payload.status,
        "reported_at": report["reported_at"],
        "sharing_location": sharing,
        "notified": notified,
    }


async def _enqueue_status_notification(
    redis: Redis,
    settings: object,
    circle_id: str,
    account: AccountPrincipal,
    report: dict[str, object],
) -> bool:
    claimed = await redis.set(
        f"seismik:family:notify:{circle_id}:{account.uid}:{report['status']}",
        "1",
        nx=True,
        ex=_NOTIFY_THROTTLE_SECONDS,
    )
    if not claimed:
        return False
    profile = cast(dict[str, str], await redis.hgetall(_member_key(circle_id, account.uid)))
    display_name = profile.get("display_name") or account.name or "Tu familiar"
    event = {
        "type": "family_status",
        "event_id": f"family-{secrets.token_urlsafe(12)}",
        "thread_id": "family",
        "circle_id": circle_id,
        # Sólo lo usa el dispatcher para no avisar al propio autor; nunca llega
        # a los teléfonos (ver `notification_content`).
        "member_id": account.uid,
        "display_name": display_name,
        "status": report["status"],
        "message": report["message"],
        "related_event_id": report["event_id"],
        "reported_at": report["reported_at"],
    }
    await redis.xadd(
        getattr(settings, "family_notification_stream"),
        {"payload": json.dumps(event, ensure_ascii=False, separators=(",", ":"))},
        maxlen=getattr(settings, "stream_maxlen"),
        approximate=True,
    )
    return True


@router.get("/circle")
async def get_circle(
    redis: Redis = Depends(get_redis),
    account: AccountPrincipal = Depends(require_account_session),
) -> dict[str, object]:
    circle_id = await _circle_for_account(redis, account.uid)
    circle = cast(dict[str, str], await redis.hgetall(_circle_key(circle_id)))
    owners = {circle.get("owner_uid"), circle.get("owner_device_id")} - {None}
    member_ids = sorted(str(item) for item in await redis.smembers(family_members_key(circle_id)))
    members: list[dict[str, object]] = []
    for member_id in member_ids:
        profile = cast(dict[str, str], await redis.hgetall(_member_key(circle_id, member_id)))
        raw_location = await redis.get(_location_key(circle_id, member_id))
        raw_status = await redis.get(_status_key(circle_id, member_id))
        members.append({
            "member_id": _public_member_id(circle_id, member_id),
            "display_name": profile.get("display_name", "Familiar"),
            "is_you": member_id == account.uid,
            "is_owner": member_id in owners,
            "location": json.loads(raw_location) if raw_location else None,
            "status": json.loads(raw_status) if raw_status else None,
        })
    await _touch_circle(redis, circle_id)
    return {
        "circle_id": circle_id,
        "circle_name": circle.get("circle_name", "Mi círculo"),
        "is_owner": account.uid in owners,
        "members": members,
    }


async def migrate_device_circle(redis: Redis, device_id: str, uid: str) -> bool:
    """Pasa a la cuenta el círculo que este teléfono tenía antes de exigirla.

    Conserva el nombre visible, la propiedad del círculo y la ubicación que
    siguiera vigente. Si la cuenta ya pertenece a otro círculo no se mezclan
    familias: el teléfono sólo sale del círculo antiguo.
    """

    legacy = await redis.get(_legacy_device_circle_key(device_id))
    if not legacy:
        return False
    circle_id = str(legacy)
    circle_key = _circle_key(circle_id)
    members_key = family_members_key(circle_id)
    if not await redis.exists(circle_key):
        await redis.delete(_legacy_device_circle_key(device_id))
        return False

    current = await redis.get(_account_circle_key(uid))
    if current and str(current) != circle_id and await redis.exists(_circle_key(str(current))):
        pipe = redis.pipeline(transaction=True)
        pipe.srem(members_key, device_id)
        pipe.delete(_member_key(circle_id, device_id))
        pipe.delete(_location_key(circle_id, device_id))
        pipe.delete(_legacy_device_circle_key(device_id))
        await pipe.execute()
        return False

    profile = cast(dict[str, str], await redis.hgetall(_member_key(circle_id, device_id)))
    account_profile_exists = bool(await redis.exists(_member_key(circle_id, uid)))
    location = await redis.get(_location_key(circle_id, device_id))
    location_ttl_ms = int(await redis.pttl(_location_key(circle_id, device_id)))
    owner_device = await redis.hget(circle_key, "owner_device_id")

    pipe = redis.pipeline(transaction=True)
    pipe.srem(members_key, device_id)
    pipe.sadd(members_key, uid)
    if profile and not account_profile_exists:
        pipe.hset(_member_key(circle_id, uid), mapping=cast(dict[Any, Any], profile))
        pipe.expire(_member_key(circle_id, uid), _CIRCLE_TTL_SECONDS)
    pipe.delete(_member_key(circle_id, device_id))
    if location and location_ttl_ms > 0:
        pipe.set(_location_key(circle_id, uid), location, px=location_ttl_ms)
    pipe.delete(_location_key(circle_id, device_id))
    if owner_device is not None and str(owner_device) == device_id:
        pipe.hset(circle_key, "owner_uid", uid)
        pipe.hdel(circle_key, "owner_device_id")
    pipe.set(_account_circle_key(uid), circle_id, ex=_CIRCLE_TTL_SECONDS)
    pipe.delete(_legacy_device_circle_key(device_id))
    await pipe.execute()
    await _touch_circle(redis, circle_id)
    return True


@account_router.post("/device")
async def link_current_device(
    redis: Redis = Depends(get_redis),
    account: AccountPrincipal = Depends(require_account_session),
    device: DevicePrincipal = Depends(require_device_session),
) -> dict[str, bool]:
    """Asocia este teléfono a la cuenta para recibir los avisos de la familia."""

    await link_device(redis, account.uid, device.device_id)
    migrated = await migrate_device_circle(redis, device.device_id, account.uid)
    return {"linked": True, "migrated_circle": migrated}


@account_router.delete("/device", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_current_device(
    redis: Redis = Depends(get_redis),
    account: AccountPrincipal = Depends(require_account_session),
    device: DevicePrincipal = Depends(require_device_session),
) -> None:
    """Al cerrar sesión el teléfono deja de recibir los avisos familiares."""

    await unlink_device(redis, account.uid, device.device_id)
