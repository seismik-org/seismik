"""Círculos familiares voluntarios para consulta tras un evento.

No es rastreo en segundo plano ni una herramienta de emergencias. Cada
instalación comparte una ubicación por un tiempo acotado y sólo con miembros
que aceptaron la misma invitación. Las credenciales de dispositivo evitan que
un código de invitación baste para consultar una ubicación.
"""
from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from redis.asyncio import Redis

from api.dependencies import DevicePrincipal, get_redis, require_device_session

router = APIRouter(prefix="/v1/family", tags=["family-safety"])

_INVITE_TTL_SECONDS = 86_400
_CIRCLE_TTL_SECONDS = 31_536_000  # 365 días sin actividad.


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


class LocationShare(_StrictModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    share_minutes: int = Field(default=60, ge=15, le=240)
    precision: Literal["approximate", "precise"] = "approximate"
    precise_location_consent: bool = False

    @model_validator(mode="after")
    def explicit_precise_consent(self) -> "LocationShare":
        if self.precision == "precise" and not self.precise_location_consent:
            raise ValueError("Precise sharing requires explicit consent")
        return self


def _circle_key(circle_id: str) -> str:
    return f"seismik:family:circle:{circle_id}"


def _members_key(circle_id: str) -> str:
    return f"seismik:family:members:{circle_id}"


def _member_key(circle_id: str, device_id: str) -> str:
    return f"seismik:family:member:{circle_id}:{device_id}"


def _location_key(circle_id: str, device_id: str) -> str:
    return f"seismik:family:location:{circle_id}:{device_id}"


async def _circle_for_device(redis: Redis, device_id: str) -> str:
    circle_id = await redis.get(f"seismik:family:device:{device_id}")
    if not circle_id or not await redis.exists(_circle_key(str(circle_id))):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No family circle found")
    return str(circle_id)


async def _assert_owner(redis: Redis, circle_id: str, device_id: str) -> None:
    owner = await redis.hget(_circle_key(circle_id), "owner_device_id")
    if owner != device_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the circle owner can invite")


async def _touch_circle(redis: Redis, circle_id: str) -> None:
    pipe = redis.pipeline(transaction=True)
    pipe.expire(_circle_key(circle_id), _CIRCLE_TTL_SECONDS)
    pipe.expire(_members_key(circle_id), _CIRCLE_TTL_SECONDS)
    await pipe.execute()


@router.post("/circle", status_code=status.HTTP_201_CREATED)
async def create_circle(
    payload: CircleCreate,
    redis: Redis = Depends(get_redis),
    principal: DevicePrincipal = Depends(require_device_session),
) -> dict[str, str]:
    existing = await redis.get(f"seismik:family:device:{principal.device_id}")
    if existing and await redis.exists(_circle_key(str(existing))):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Device already belongs to a family circle")
    circle_id = secrets.token_urlsafe(18)
    now = datetime.now(timezone.utc).isoformat()
    pipe = redis.pipeline(transaction=True)
    pipe.hset(
        _circle_key(circle_id),
        mapping={
            "circle_id": circle_id,
            "circle_name": payload.circle_name,
            "owner_device_id": principal.device_id,
            "created_at": now,
        },
    )
    pipe.sadd(_members_key(circle_id), principal.device_id)
    pipe.hset(_member_key(circle_id, principal.device_id), mapping={"display_name": payload.display_name, "joined_at": now})
    pipe.set(f"seismik:family:device:{principal.device_id}", circle_id, ex=_CIRCLE_TTL_SECONDS)
    pipe.expire(_circle_key(circle_id), _CIRCLE_TTL_SECONDS)
    pipe.expire(_members_key(circle_id), _CIRCLE_TTL_SECONDS)
    pipe.expire(_member_key(circle_id, principal.device_id), _CIRCLE_TTL_SECONDS)
    await pipe.execute()
    return {"circle_id": circle_id, "circle_name": payload.circle_name}


@router.post("/circle/invitations", status_code=status.HTTP_201_CREATED)
async def create_invitation(
    payload: InviteCreate,
    redis: Redis = Depends(get_redis),
    principal: DevicePrincipal = Depends(require_device_session),
) -> dict[str, object]:
    circle_id = await _circle_for_device(redis, principal.device_id)
    await _assert_owner(redis, circle_id, principal.device_id)
    code = secrets.token_urlsafe(18)
    await redis.set(
        f"seismik:family:invite:{code}",
        json.dumps({"circle_id": circle_id, "created_by": principal.device_id, "display_name": payload.display_name}),
        ex=_INVITE_TTL_SECONDS,
    )
    return {"invite_code": code, "expires_in_minutes": _INVITE_TTL_SECONDS // 60}


@router.post("/join")
async def join_circle(
    payload: CircleJoin,
    redis: Redis = Depends(get_redis),
    principal: DevicePrincipal = Depends(require_device_session),
) -> dict[str, str]:
    if await redis.get(f"seismik:family:device:{principal.device_id}"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Device already belongs to a family circle")
    raw = await redis.get(f"seismik:family:invite:{payload.invite_code}")
    if not raw:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation is invalid or expired")
    invitation = json.loads(raw)
    circle_id = str(invitation["circle_id"])
    if not await redis.exists(_circle_key(circle_id)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Family circle no longer exists")
    now = datetime.now(timezone.utc).isoformat()
    pipe = redis.pipeline(transaction=True)
    pipe.sadd(_members_key(circle_id), principal.device_id)
    pipe.hset(_member_key(circle_id, principal.device_id), mapping={"display_name": payload.display_name, "joined_at": now})
    pipe.set(f"seismik:family:device:{principal.device_id}", circle_id, ex=_CIRCLE_TTL_SECONDS)
    pipe.delete(f"seismik:family:invite:{payload.invite_code}")
    pipe.expire(_member_key(circle_id, principal.device_id), _CIRCLE_TTL_SECONDS)
    await pipe.execute()
    await _touch_circle(redis, circle_id)
    return {"circle_id": circle_id, "circle_name": str(await redis.hget(_circle_key(circle_id), "circle_name"))}


@router.put("/location")
async def share_location(
    payload: LocationShare,
    redis: Redis = Depends(get_redis),
    principal: DevicePrincipal = Depends(require_device_session),
) -> dict[str, object]:
    circle_id = await _circle_for_device(redis, principal.device_id)
    latitude, longitude = payload.latitude, payload.longitude
    # La precisión aproximada se degrada en el servidor; nunca se conserva la
    # coordenada exacta para poder reconstruirla después.
    if payload.precision == "approximate":
        latitude, longitude = round(latitude, 2), round(longitude, 2)
    now = datetime.now(timezone.utc)
    expires_seconds = payload.share_minutes * 60
    data = {
        "latitude": latitude,
        "longitude": longitude,
        "precision": payload.precision,
        "shared_at": now.isoformat(),
        "expires_at": datetime.fromtimestamp(now.timestamp() + expires_seconds, tz=timezone.utc).isoformat(),
    }
    await redis.set(
        _location_key(circle_id, principal.device_id),
        json.dumps(data),
        ex=expires_seconds,
    )
    await _touch_circle(redis, circle_id)
    return {"sharing": True, "expires_in_minutes": payload.share_minutes, "precision": payload.precision}


@router.delete("/location", status_code=status.HTTP_204_NO_CONTENT)
async def stop_sharing_location(
    redis: Redis = Depends(get_redis),
    principal: DevicePrincipal = Depends(require_device_session),
) -> None:
    circle_id = await _circle_for_device(redis, principal.device_id)
    await redis.delete(_location_key(circle_id, principal.device_id))


@router.get("/circle")
async def get_circle(
    redis: Redis = Depends(get_redis),
    principal: DevicePrincipal = Depends(require_device_session),
) -> dict[str, object]:
    circle_id = await _circle_for_device(redis, principal.device_id)
    circle = await redis.hgetall(_circle_key(circle_id))
    device_ids = sorted(str(item) for item in await redis.smembers(_members_key(circle_id)))
    members: list[dict[str, object]] = []
    for device_id in device_ids:
        profile = await redis.hgetall(_member_key(circle_id, device_id))
        raw_location = await redis.get(_location_key(circle_id, device_id))
        location = json.loads(raw_location) if raw_location else None
        members.append({
            "display_name": profile.get("display_name", "Familiar"),
            "is_you": device_id == principal.device_id,
            "location": location,
        })
    await _touch_circle(redis, circle_id)
    return {"circle_id": circle_id, "circle_name": circle.get("circle_name", "Mi círculo"), "members": members}
