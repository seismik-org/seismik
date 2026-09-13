"""Cuenta Seismik dentro de la app móvil.

La sesión de dispositivo identifica una instalación; la cuenta identifica a una
persona. Búsqueda de familiares necesita la segunda: el círculo debe seguir a
la persona si cambia de teléfono o reinstala la app, y el nombre que ve su
familia proviene de un inicio de sesión verificado.

La sesión se emite en ``/v1/oauth/mobile/exchange`` y la app la envía en
``X-Seismik-Account-Session``.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import cast

from fastapi import Header, HTTPException, Request, status
from redis.asyncio import Redis

ACCOUNT_SESSION_HEADER = "X-Seismik-Account-Session"


@dataclass(frozen=True)
class AccountPrincipal:
    uid: str
    email: str
    name: str


def mobile_session_key(token: str) -> str:
    return f"seismik:oauth:mobile-session:{token}"


def account_devices_key(uid: str) -> str:
    """Teléfonos donde la persona inició sesión: destino de los avisos familiares."""
    return f"seismik:account:devices:{uid}"


def device_account_key(device_id: str) -> str:
    return f"seismik:device:account:{device_id}"


async def require_account_session(
    request: Request,
    x_account_session: str | None = Header(default=None, alias=ACCOUNT_SESSION_HEADER),
) -> AccountPrincipal:
    if not x_account_session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Account session required"
        )
    redis: Redis = request.app.state.redis
    key = mobile_session_key(x_account_session)
    raw = await redis.get(key)
    user = json.loads(raw) if raw else {}
    uid = str(user.get("uid") or "")
    if not uid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Account session expired"
        )
    # Renovación deslizante: quien usa la app no debe encontrarse con que su
    # sesión venció justo cuando necesita avisar a su familia tras un sismo.
    await redis.expire(key, request.app.state.settings.mobile_account_session_ttl_seconds)
    return AccountPrincipal(
        uid=uid,
        email=str(user.get("email") or ""),
        name=str(user.get("name") or ""),
    )


async def link_device(redis: Redis, uid: str, device_id: str) -> None:
    """Asocia el teléfono a la cuenta; un teléfono pertenece a una sola cuenta."""

    previous = await redis.get(device_account_key(device_id))
    pipe = redis.pipeline(transaction=True)
    if previous and str(previous) != uid:
        # Otra persona inició sesión en este teléfono: deja de recibir los
        # avisos de la familia anterior.
        pipe.srem(account_devices_key(str(previous)), device_id)
    pipe.sadd(account_devices_key(uid), device_id)
    pipe.set(device_account_key(device_id), uid)
    await pipe.execute()


async def unlink_device(redis: Redis, uid: str, device_id: str) -> None:
    owner = await redis.get(device_account_key(device_id))
    pipe = redis.pipeline(transaction=True)
    pipe.srem(account_devices_key(uid), device_id)
    if owner is not None and str(owner) == uid:
        pipe.delete(device_account_key(device_id))
    await pipe.execute()


async def devices_for_account(redis: Redis, uid: str) -> set[str]:
    members = cast(set[str], await redis.smembers(account_devices_key(uid)))
    return {str(item) for item in members}
