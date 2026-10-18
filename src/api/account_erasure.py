"""Eliminación de cuenta hecha por la propia persona, sin pasar por el equipo.

El formulario público (`account_deletion.py`) sólo deja una solicitud en la bitácora: nadie que
escriba un correo ajeno puede borrar la cuenta de otra persona. Aquí la identidad ya está probada:
quien llega tiene una sesión del portal iniciada hace pocos minutos, confirma escribiendo la palabra
y el servidor borra sus datos de una vez.

Qué se borra y qué se conserva está a la vista en `ERASED` y `RETAINED`; la política de privacidad y
la página de eliminación dicen lo mismo y una prueba comprueba que el código no deje nada fuera.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import secrets
import time
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Cookie,
    Depends,
    HTTPException,
    Request,
    Response,
    status,
)
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict
from redis.asyncio import Redis

from api.accounts import account_devices_key, device_account_key
from api.config import AppSettings
from api.dependencies import get_app_settings, get_redis
from api.device_sessions import DeviceSessionRepository
from api.devices_store import DeviceRepository
from api.family import (
    _account_circle_key,
    _circle_key,
    _legacy_device_circle_key,
    _location_key,
    _member_key,
    _status_key,
    automatic_location_key,
    family_members_key,
)
from api.mail_templates import account_erased
from api.mailer import Mailer

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/account", tags=["account-erasure"])

AFTER_LOGIN_COOKIE = "seismik_after_login"
ERASURE_MARKER = "delete-account"
# La sesión del portal dura 24 h; borrar una cuenta exige haber entrado hace poco.
RECENT_LOGIN_SECONDS = 600
# Más que la sesión móvil más larga (90 días): ninguna sesión anterior sobrevive al borrado.
ERASED_MARKER_SECONDS = 100 * 86_400
ALLOWED_ORIGINS = frozenset({"https://seismik.org"})
SCAN_BATCH = 500

ERASED = (
    "dispositivos y tokens de notificaciones",
    "pertenencia a círculos familiares, ubicaciones, estados y alias",
    "claves de API, perfil de desarrollador y webhooks",
    "reportes voluntarios enviados desde sus dispositivos",
    "sesiones abiertas",
)
RETAINED = ("registros contables de facturación, si existen",)

DELETION_KEY = "seismik:admin:deletions"


def erased_marker_key(uid: str) -> str:
    return f"seismik:account:erased:{uid}"


async def session_was_erased(redis: Redis, user: dict[str, Any]) -> bool:
    """¿Esta sesión es anterior a la eliminación de su cuenta? Un inicio de sesión del mismo segundo o posterior es válido."""

    uid = str(user.get("uid") or "")
    if not uid:
        return False
    marker = await redis.get(erased_marker_key(uid))
    if not marker:
        return False
    try:
        return float(user.get("authenticated_at", 0)) < float(marker)
    except (TypeError, ValueError):
        return True


class ErasureConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm: Literal["ELIMINAR"]


async def _scan(redis: Redis, pattern: str) -> list[str]:
    return [str(key) async for key in redis.scan_iter(match=pattern, count=SCAN_BATCH)]


async def _delete(redis: Redis, *keys: str) -> int:
    keys = tuple(key for key in keys if key)
    return int(await redis.delete(*keys)) if keys else 0


async def _erase_devices(redis: Redis, settings: AppSettings, uid: str) -> set[str]:
    device_ids = {str(item) for item in await redis.smembers(account_devices_key(uid))}
    # Teléfonos que apuntan a la cuenta sin figurar ya en su lista (migraciones antiguas).
    for key in await _scan(redis, "seismik:device:account:*"):
        if str(await redis.get(key)) == uid:
            device_ids.add(key.rsplit(":", 1)[1])
    repository = DeviceRepository(redis)
    sessions = DeviceSessionRepository(redis, ttl_seconds=settings.device_session_ttl_seconds)
    for device_id in device_ids:
        await repository.unregister(device_id)
        await sessions.revoke(device_id)
        await _delete(redis, device_account_key(device_id), _legacy_device_circle_key(device_id))
    await _delete(redis, account_devices_key(uid))
    return device_ids


async def _erase_family(redis: Redis, uid: str) -> bool:
    circle_id = await redis.get(_account_circle_key(uid))
    in_circle = False
    if circle_id:
        circle_id = str(circle_id)
        in_circle = bool(await redis.sismember(family_members_key(circle_id), uid))
        pipe = redis.pipeline(transaction=True)
        pipe.srem(family_members_key(circle_id), uid)
        pipe.delete(_member_key(circle_id, uid), _location_key(circle_id, uid), _status_key(circle_id, uid))
        await pipe.execute()
        remaining = {str(item) for item in await redis.smembers(family_members_key(circle_id))}
        if not remaining:
            await _delete(redis, _circle_key(circle_id), family_members_key(circle_id))
        elif await redis.hget(_circle_key(circle_id), "owner_uid") == uid:
            # El círculo sigue siendo de la familia: lo hereda quien entró primero.
            joined: list[tuple[str, str]] = []
            for member in remaining:
                joined.append((str(await redis.hget(_member_key(circle_id, member), "joined_at") or ""), member))
            await redis.hset(_circle_key(circle_id), "owner_uid", min(joined)[1])
    await _delete(redis, _account_circle_key(uid), automatic_location_key(uid))
    for key in await _scan(redis, f"seismik:family:auto-alert:{uid}:*"):
        await redis.delete(key)
    return in_circle


async def _erase_developer(redis: Redis, uid: str) -> tuple[int, int]:
    key_ids = {str(item) for item in await redis.smembers(f"seismik:developer-keys:{uid}")}
    for key_id in key_ids:
        digest = await redis.get(f"seismik:developer-key-id:{key_id}")
        digests = {str(digest)} if digest else set()
        # La primera beta guardaba el digest directamente en la lista.
        digests.add(key_id)
        for item in digests:
            await _delete(redis, f"seismik:developer-key:{item}", *await _scan(redis, f"seismik:developer-usage:*:{item}:*"))
        await _delete(redis, f"seismik:developer-key-id:{key_id}")
    await _delete(
        redis,
        f"seismik:developer-keys:{uid}",
        f"seismik:developer-profile:{uid}",
        *await _scan(redis, f"seismik:developer-key-creations:{uid}:*"),
        *await _scan(redis, f"seismik:developer-account-usage:*:{uid}:*"),
    )
    webhook_ids = {str(item) for item in await redis.smembers(f"seismik:webhooks:{uid}")}
    for webhook_id in webhook_ids:
        record = await redis.hgetall(f"seismik:webhook:{webhook_id}")
        # Sólo se borra lo que la cuenta posee: un identificador ajeno en la lista no vale.
        if record and record.get("uid") == uid:
            await redis.delete(f"seismik:webhook:{webhook_id}")
        await redis.srem("seismik:webhooks:active", webhook_id)
    await _delete(redis, f"seismik:webhooks:{uid}")
    return len(key_ids), len(webhook_ids)


async def _erase_reports(redis: Redis, settings: AppSettings, device_ids: set[str]) -> int:
    """Quita de las colas de reportes los enviados desde los teléfonos de la cuenta."""

    if not device_ids:
        return 0
    removed = 0
    for stream in (settings.felt_reports_stream, settings.damage_reports_stream):
        cursor = "-"
        while True:
            batch = await redis.xrange(stream, min=cursor, max="+", count=SCAN_BATCH)
            if not batch:
                break
            doomed: list[str] = []
            for entry_id, fields in batch:
                try:
                    payload = json.loads((fields or {}).get("payload", "{}"))
                except (TypeError, ValueError):
                    continue
                if isinstance(payload, dict) and str(payload.get("device_id", "")) in device_ids:
                    doomed.append(str(entry_id))
            if doomed:
                removed += int(await redis.xdel(stream, *doomed))
            if len(batch) < SCAN_BATCH:
                break
            cursor = "(" + str(batch[-1][0])
    return removed


async def erase_account(
    redis: Redis,
    settings: AppSettings,
    *,
    uid: str,
    firebase_uid: str | None = None,
    delete_firebase_user: Any = None,
) -> dict[str, Any]:
    """Borra los datos de la cuenta. Cada paso es idempotente: repetirlo no daña nada."""

    started = time.time()
    # Primero la marca: desde este instante ninguna sesión anterior sigue siendo válida.
    await redis.set(erased_marker_key(uid), str(int(started)), ex=ERASED_MARKER_SECONDS)
    device_ids = await _erase_devices(redis, settings, uid)
    was_in_circle = await _erase_family(redis, uid)
    keys, webhooks = await _erase_developer(redis, uid)
    reports = await _erase_reports(redis, settings, device_ids)
    pending: list[str] = []
    if firebase_uid:
        await _delete(redis, "seismik:identity:firebase:" + hashlib.sha256(firebase_uid.encode()).hexdigest())
        if delete_firebase_user is not None:
            try:
                await delete_firebase_user(firebase_uid)
            except Exception:  # noqa: BLE001 - el borrado local ya ocurrió; se deja constancia para repetirlo
                LOGGER.exception("No se pudo borrar el usuario de Firebase Authentication")
                pending.append("firebase_authentication")
    ledger = bool(await redis.exists(f"seismik:billing:ledger:{uid}"))
    summary = {
        "devices": len(device_ids), "family_circle": was_in_circle, "api_keys": keys,
        "webhooks": webhooks, "reports": reports, "billing_retained": ledger, "pending": pending,
    }
    request_id = "delreq_" + secrets.token_hex(8)
    now = datetime.now(timezone.utc).isoformat()
    pipe = redis.pipeline(transaction=True)
    pipe.xadd(
        settings.account_deletion_request_stream,
        {"payload": json.dumps({"request_id": request_id, "received_at": now, "scope": "full", "source": "self_service"})},
        maxlen=settings.stream_maxlen, approximate=True,
    )
    pipe.hset(DELETION_KEY, request_id, json.dumps({"status": "completed", "by": "self-service", "at": now}))
    await pipe.execute()
    LOGGER.info("Account erased request_id=%s %s", request_id, json.dumps(summary))
    return {**summary, "request_id": request_id}


async def _session(request: Request, token: str | None) -> dict[str, Any]:
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Inicia sesión para continuar")
    raw = await request.app.state.redis.get(f"seismik:oauth:session:{token}")
    if not raw:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Tu sesión expiró; inicia sesión de nuevo")
    user: dict[str, Any] = json.loads(raw)
    from api.firebase_login import validate_session

    await validate_session(request, user)
    return user


def _is_recent(user: dict[str, Any]) -> bool:
    try:
        return 0 <= time.time() - float(user.get("authenticated_at", 0)) <= RECENT_LOGIN_SECONDS
    except (TypeError, ValueError):
        return False


def _mask(email: str) -> str:
    local, _, domain = email.partition("@")
    return (local[:1] + "•••@" + domain) if domain else "•••"


@router.get("/erasure/login")
async def start_login(settings: AppSettings = Depends(get_app_settings)) -> Response:
    """Lleva a iniciar sesión y, al volver, a la página de eliminación (destino fijo, sin parámetros)."""

    response = RedirectResponse("https://auth.seismik.org/id", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        AFTER_LOGIN_COOKIE, ERASURE_MARKER, max_age=600, secure=True, httponly=True,
        samesite="none", path="/", domain=settings.oauth_cookie_domain,
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/erasure")
async def erasure_summary(
    request: Request, response: Response, seismik_session: str | None = Cookie(default=None),
    redis: Redis = Depends(get_redis),
) -> dict[str, Any]:
    """Quién es la persona, si su inicio de sesión es reciente y qué se borrará."""

    response.headers["Cache-Control"] = "no-store"
    user = await _session(request, seismik_session)
    uid = str(user["uid"])
    devices = {str(item) for item in await redis.smembers(account_devices_key(uid))}
    return {
        "email": _mask(str(user.get("email", ""))), "name": str(user.get("name", "")),
        "recent_login": _is_recent(user), "devices": len(devices),
        "in_family_circle": bool(await redis.exists(_account_circle_key(uid))),
        "api_keys": int(await redis.scard(f"seismik:developer-keys:{uid}")),
        "erased": list(ERASED), "retained": list(RETAINED),
    }


@router.post("/erasure")
async def erase_my_account(
    confirmation: ErasureConfirmation, request: Request, response: Response, background: BackgroundTasks,
    seismik_session: str | None = Cookie(default=None), redis: Redis = Depends(get_redis),
    settings: AppSettings = Depends(get_app_settings),
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    # Sólo desde la página de eliminación: una página ajena no puede lanzar un borrado con la cookie.
    if request.headers.get("origin") not in ALLOWED_ORIGINS:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Origen no permitido")
    user = await _session(request, seismik_session)
    if not _is_recent(user):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "reauth_required")
    uid = str(user["uid"])
    bucket = f"seismik:account-erasure:rate:{hashlib.sha256(uid.encode()).hexdigest()[:16]}:{int(time.time()) // 3600}"
    pipe = redis.pipeline(transaction=True)
    pipe.incr(bucket)
    pipe.expire(bucket, 7_200)
    count, _ = await pipe.execute()
    if int(count) > 5:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Demasiados intentos; espera una hora")

    async def delete_firebase_user(firebase_uid: str) -> None:
        from firebase_admin import auth

        from api.developer_keys import _firebase_app

        await asyncio.to_thread(auth.delete_user, firebase_uid, app=_firebase_app(request))

    result = await erase_account(
        redis, settings, uid=uid, firebase_uid=str(user.get("firebase_uid") or "") or None,
        delete_firebase_user=delete_firebase_user,
    )
    await redis.delete(f"seismik:oauth:session:{seismik_session}")
    response.delete_cookie(
        "seismik_session", path="/", domain=settings.oauth_cookie_domain,
    )
    email = str(user.get("email") or "")
    if "@" in email:
        # Después de responder y sin guardar el correo: el aviso no debe retrasar ni romper el borrado.
        background.add_task(Mailer(settings).send, account_erased(email, request_id=str(result["request_id"])))
    return {"erased": True, **result}
