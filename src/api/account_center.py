"""Centro de la cuenta (auth.seismik.org/account): ver los datos, administrar los accesos y borrar.

Vive bajo `/v1/oauth/account` porque el Worker sólo enruta a la API las rutas `/v1/oauth/` del dominio de
acceso. Todo exige la sesión del portal; lo que cambia algo exige además un inicio de sesión reciente.

Formas de acceso. La cuenta tiene una identidad principal (con la que nació) y puede enlazar otras: un
correo con contraseña (Firebase) y cuentas de Google o GitHub, todas apuntando al mismo `uid`. Enlazar nunca
fusiona cuentas con datos: si la identidad nueva ya tiene los suyos, se rechaza. Apple no se enlaza aquí
porque su respuesta llega por POST desde otro sitio y no trae la cookie con la que se comprueba el navegador.
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import time
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Cookie, Depends, HTTPException, Path, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict
from redis.asyncio import Redis

from api import account_erasure
from api.accounts import account_devices_key
from api.config import AppSettings
from api.dependencies import get_app_settings, get_redis
from api.family import (
    _account_circle_key,
    _circle_key,
    _location_key,
    _member_key,
    _status_key,
    automatic_location_key,
    family_members_key,
)

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/oauth/account", tags=["account-center"])

ACCOUNT_URL = "https://auth.seismik.org/account/"
LOGIN_URL = "https://auth.seismik.org/id"
LINK_COOKIE = "seismik_link"
AFTER_LOGIN_COOKIE = "seismik_after_login"
ACCOUNT_MARKER = "account"
LINK_TTL_SECONDS = 600
LINK_COMPLETION_SECONDS = 900
PROVIDERS = {"google": "Google", "github": "GitHub", "apple": "Apple", "email": "Correo y contraseña"}
LINKABLE = ("google", "github", "email")
CATEGORIES = ("devices", "family", "developer", "reports")
EXPORT_REPORT_LIMIT = 200


def provider_link_key(puid: str) -> str:
    return "seismik:identity:linked:" + hashlib.sha256(puid.encode()).hexdigest()


def firebase_binding_key(firebase_uid: str) -> str:
    return "seismik:identity:firebase:" + hashlib.sha256(firebase_uid.encode()).hexdigest()


def links_key(uid: str) -> str:
    return f"seismik:account:links:{uid}"


def link_token_key(token: str) -> str:
    return f"seismik:oauth:link:{token}"


def _identity_data_keys(uid: str) -> tuple[str, ...]:
    return (
        f"seismik:developer-keys:{uid}", f"seismik:developer-profile:{uid}", f"seismik:family:account:{uid}",
        f"seismik:account:devices:{uid}", f"seismik:webhooks:{uid}", f"seismik:billing:balance:{uid}",
        f"seismik:billing:ledger:{uid}",
    )


async def canonical_method(redis: Redis, uid: str) -> str:
    if uid.startswith("github:"):
        return "github"
    if uid.startswith("apple:"):
        return "apple"
    if await redis.get(firebase_binding_key(uid)) == uid:
        return "email"
    return "google"


async def methods_for(redis: Redis, uid: str) -> list[dict[str, Any]]:
    primary = await canonical_method(redis, uid)
    links = {str(k): json.loads(v) for k, v in (await redis.hgetall(links_key(uid))).items()}
    total = 1 + len([m for m in links if m != primary])
    methods: list[dict[str, Any]] = []
    for method, label in PROVIDERS.items():
        entry: dict[str, Any] = {
            "id": method, "label": label, "linked": False, "primary": False, "removable": False,
            "linkable": method in LINKABLE,
        }
        if method == primary:
            entry.update(linked=True, primary=True, linkable=False)
        elif method in links:
            entry.update(linked=True, linkable=False, removable=total > 1, added_at=links[method].get("added_at"))
        methods.append(entry)
    return methods


async def _device_ids(redis: Redis, uid: str) -> set[str]:
    return {str(item) for item in await redis.smembers(account_devices_key(uid))}


def _mask(email: str) -> str:
    local, _, domain = email.partition("@")
    return (local[:1] + "•••@" + domain) if domain else "•••"


async def _report_entries(redis: Redis, settings: AppSettings, device_ids: set[str], limit: int) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for stream, kind in ((settings.felt_reports_stream, "sismo_sentido"), (settings.damage_reports_stream, "danos")):
        cursor = "-"
        while len(found) < limit:
            batch = await redis.xrange(stream, min=cursor, max="+", count=account_erasure.SCAN_BATCH)
            if not batch:
                break
            for _entry_id, fields in batch:
                try:
                    payload = json.loads((fields or {}).get("payload", "{}"))
                except (TypeError, ValueError):
                    continue
                if isinstance(payload, dict) and str(payload.get("device_id", "")) in device_ids:
                    payload.pop("device_id", None)
                    found.append({"tipo": kind, **payload})
                    if len(found) >= limit:
                        break
            if len(batch) < account_erasure.SCAN_BATCH:
                break
            cursor = "(" + str(batch[-1][0])
    return found


async def collect_data(redis: Redis, settings: AppSettings, user: dict[str, Any]) -> dict[str, Any]:
    """Todo lo que Seismik guarda de esta cuenta, tal como lo guarda."""

    uid = str(user["uid"])
    device_ids = await _device_ids(redis, uid)
    devices = []
    for device_id in sorted(device_ids):
        record = await redis.hgetall(f"seismik:device:{device_id}")
        if not record:
            continue
        devices.append({
            "id": device_id, "plataforma": record.get("platform"), "ultimo_registro": record.get("updated_at"),
            "zona": record.get("zone_id") or None, "pais": record.get("country_code") or None, "idioma": record.get("locale"),
            "ubicacion_guardada": {"latitud": record.get("latitude") or None, "longitud": record.get("longitude") or None},
            "alertas": {
                "tempranas": record.get("receive_early_alerts") == "1", "oficiales": record.get("receive_official_updates") == "1",
                "magnitud_minima": record.get("minimum_notification_magnitude"), "radio_km": record.get("alert_radius_km"),
                "criticas_autorizadas": record.get("critical_alerts_authorized") == "1",
            },
            "token_de_notificaciones_guardado": bool(record.get("token")), "verificado_con_app_check": record.get("integrity_verified") == "1",
        })
    family: dict[str, Any] | None = None
    circle = await redis.get(_account_circle_key(uid))
    if circle and await redis.exists(_circle_key(str(circle))):
        circle = str(circle)
        info = await redis.hgetall(_circle_key(circle))
        member = await redis.hgetall(_member_key(circle, uid))
        family = {
            "circulo": info.get("circle_name"), "rol": "dueño" if info.get("owner_uid") == uid else "integrante",
            "alias": member.get("display_name"), "desde": member.get("joined_at"),
            "integrantes": int(await redis.scard(family_members_key(circle))),
            "ubicacion_compartida_ahora": bool(await redis.exists(_location_key(circle, uid))),
            "estado_reciente": bool(await redis.exists(_status_key(circle, uid))),
            "ubicacion_automatica_activada": (await redis.get(automatic_location_key(uid))) == "1",
        }
    keys = []
    for key_id in sorted(str(item) for item in await redis.smembers(f"seismik:developer-keys:{uid}")):
        digest = await redis.get(f"seismik:developer-key-id:{key_id}")
        record = await redis.hgetall(f"seismik:developer-key:{str(digest) if digest else key_id}")
        if record:
            keys.append({k: record.get(k) for k in ("key_id", "name", "prefix", "plan", "status", "created_at", "last_used_at", "scopes")})
    webhooks = []
    for webhook_id in sorted(str(item) for item in await redis.smembers(f"seismik:webhooks:{uid}")):
        record = await redis.hgetall(f"seismik:webhook:{webhook_id}")
        if record and record.get("uid") == uid:
            webhooks.append({"id": webhook_id, **{k: v for k, v in record.items() if k not in ("uid",) and "secret" not in k}})
    billing = None
    if await redis.exists(f"seismik:billing:balance:{uid}", f"seismik:billing:ledger:{uid}"):
        billing = {"saldo": await redis.get(f"seismik:billing:balance:{uid}"), "movimientos": int(await redis.llen(f"seismik:billing:ledger:{uid}")) if await redis.type(f"seismik:billing:ledger:{uid}") == "list" else None}
    return {
        "generado": datetime.now(timezone.utc).isoformat(),
        "cuenta": {
            "identificador": hashlib.sha256(uid.encode()).hexdigest()[:12], "nombre": user.get("name") or None, "correo": user.get("email") or None,
            "accesos": [{"metodo": m["label"], "principal": m["primary"]} for m in await methods_for(redis, uid) if m["linked"]],
        },
        "dispositivos": devices, "familia": family,
        "desarrollador": {
            "claves_de_api": keys, "perfil": await redis.hgetall(f"seismik:developer-profile:{uid}") or None, "webhooks": webhooks,
        },
        "facturacion": billing,
        "reportes": await _report_entries(redis, settings, set(device_ids), EXPORT_REPORT_LIMIT),
        "no_guardamos": ["contraseñas de Google, GitHub o Apple", "contactos del teléfono", "fotos, videos ni audio"],
    }


async def _counts(redis: Redis, settings: AppSettings, uid: str) -> dict[str, Any]:
    device_ids = await _device_ids(redis, uid)
    return {
        "devices": len(device_ids), "family_circle": bool(await redis.exists(_account_circle_key(uid))),
        "api_keys": int(await redis.scard(f"seismik:developer-keys:{uid}")), "webhooks": int(await redis.scard(f"seismik:webhooks:{uid}")),
        "reports": len(await _report_entries(redis, settings, device_ids, EXPORT_REPORT_LIMIT)) if device_ids else 0,
        "billing": bool(await redis.exists(f"seismik:billing:ledger:{uid}", f"seismik:billing:balance:{uid}")),
    }


def _origin_ok(request: Request) -> None:
    if request.headers.get("origin") not in account_erasure.ALLOWED_ORIGINS:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Origen no permitido")


async def _rate(redis: Redis, uid: str, what: str, limit: int) -> None:
    bucket = f"seismik:account-center:rate:{what}:{hashlib.sha256(uid.encode()).hexdigest()[:16]}:{int(time.time()) // 3600}"
    pipe = redis.pipeline(transaction=True)
    pipe.incr(bucket)
    pipe.expire(bucket, 7_200)
    count, _ = await pipe.execute()
    if int(count) > limit:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Demasiados intentos; espera una hora")


async def _recent_user(request: Request, token: str | None) -> dict[str, Any]:
    user = await account_erasure._session(request, token)
    if not account_erasure._is_recent(user):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "reauth_required")
    return user


@router.get("/login")
async def start_login(settings: AppSettings = Depends(get_app_settings)) -> Response:
    """Entrar y volver al centro de la cuenta (destino fijo, sin parámetros)."""

    response = RedirectResponse(LOGIN_URL, status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(
        AFTER_LOGIN_COOKIE, ACCOUNT_MARKER, max_age=600, secure=True, httponly=True,
        samesite="none", path="/", domain=settings.oauth_cookie_domain,
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/center")
async def center(
    request: Request, response: Response, seismik_session: str | None = Cookie(default=None),
    redis: Redis = Depends(get_redis), settings: AppSettings = Depends(get_app_settings),
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    user = await account_erasure._session(request, seismik_session)
    uid = str(user["uid"])
    return {
        "name": str(user.get("name", "")), "email": str(user.get("email", "")),
        "account_id": hashlib.sha256(uid.encode()).hexdigest()[:12],
        "recent_login": account_erasure._is_recent(user), "methods": await methods_for(redis, uid),
        "data": await _counts(redis, settings, uid),
    }


@router.get("/data")
async def export_data(
    request: Request, response: Response, download: bool = False, seismik_session: str | None = Cookie(default=None),
    redis: Redis = Depends(get_redis), settings: AppSettings = Depends(get_app_settings),
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    user = await account_erasure._session(request, seismik_session)
    await _rate(redis, str(user["uid"]), "export", 20)
    if download:
        response.headers["Content-Disposition"] = 'attachment; filename="mis-datos-seismik.json"'
    return await collect_data(redis, settings, user)


@router.delete("/data/{category}")
async def delete_category(
    request: Request, response: Response, category: str = Path(pattern=r"^(devices|family|developer|reports)$"),
    seismik_session: str | None = Cookie(default=None), redis: Redis = Depends(get_redis),
    settings: AppSettings = Depends(get_app_settings),
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    _origin_ok(request)
    user = await _recent_user(request, seismik_session)
    uid = str(user["uid"])
    await _rate(redis, uid, "delete", 10)
    result: dict[str, Any] = {"category": category}
    if category == "devices":
        result["devices"] = len(await account_erasure._erase_devices(redis, settings, uid))
    elif category == "family":
        result["family_circle"] = await account_erasure._erase_family(redis, uid)
    elif category == "developer":
        keys, webhooks = await account_erasure._erase_developer(redis, uid)
        result.update(api_keys=keys, webhooks=webhooks)
    else:
        result["reports"] = await account_erasure._erase_reports(redis, settings, await _device_ids(redis, uid))
    LOGGER.info("Account data category erased category=%s", category)
    return result


class UnlinkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    method: Literal["google", "github", "email"]


@router.post("/methods/unlink")
async def unlink_method(
    body: UnlinkRequest, request: Request, response: Response, seismik_session: str | None = Cookie(default=None),
    redis: Redis = Depends(get_redis),
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    _origin_ok(request)
    user = await _recent_user(request, seismik_session)
    uid = str(user["uid"])
    await _rate(redis, uid, "unlink", 10)
    current = {m["id"]: m for m in await methods_for(redis, uid)}
    target = current[body.method]
    if not target["linked"] or target["primary"]:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ese acceso es el principal de la cuenta o no está vinculado")
    if not target["removable"]:
        raise HTTPException(status.HTTP_409_CONFLICT, "Debe quedar al menos un acceso")
    entry = json.loads(await redis.hget(links_key(uid), body.method) or "{}")
    puid = str(entry.get("puid") or "")
    pipe = redis.pipeline(transaction=True)
    if puid:
        pipe.delete(firebase_binding_key(puid) if body.method == "email" else provider_link_key(puid))
    pipe.hdel(links_key(uid), body.method)
    await pipe.execute()
    return {"methods": await methods_for(redis, uid)}


@router.get("/methods/link/{provider}")
async def start_link(
    request: Request, provider: str = Path(pattern=r"^(google|github|email)$"),
    seismik_session: str | None = Cookie(default=None), redis: Redis = Depends(get_redis),
    settings: AppSettings = Depends(get_app_settings),
) -> Response:
    user = await account_erasure._session(request, seismik_session)
    if not account_erasure._is_recent(user):
        return RedirectResponse(f"{ACCOUNT_URL}?link=reauth", status_code=status.HTTP_303_SEE_OTHER)
    uid = str(user["uid"])
    methods = {m["id"]: m for m in await methods_for(redis, uid)}
    if methods[provider]["linked"]:
        return RedirectResponse(f"{ACCOUNT_URL}?link=already", status_code=status.HTTP_303_SEE_OTHER)
    if provider == "email":
        response = RedirectResponse(f"{LOGIN_URL}?link=1", status_code=status.HTTP_303_SEE_OTHER)
        response.set_cookie(
            AFTER_LOGIN_COOKIE, ACCOUNT_MARKER, max_age=600, secure=True, httponly=True,
            samesite="none", path="/", domain=settings.oauth_cookie_domain,
        )
        response.headers["Cache-Control"] = "no-store"
        return response
    token = secrets.token_urlsafe(32)
    await redis.set(link_token_key(token), json.dumps({"uid": uid, "provider": provider}), ex=LINK_TTL_SECONDS)
    response = RedirectResponse(f"/v1/oauth/{provider}/start?link={token}", status_code=status.HTTP_303_SEE_OTHER)
    # La cookie liga el enlace a ESTE navegador: sin ella, alguien podría hacer que otra persona
    # termine el flujo y enlazar su identidad a una cuenta ajena.
    response.set_cookie(
        LINK_COOKIE, token, max_age=LINK_TTL_SECONDS, secure=True, httponly=True, samesite="lax", path="/",
        domain=settings.oauth_cookie_domain,
    )
    response.headers["Cache-Control"] = "no-store"
    return response


async def link_state(request: Request, link: str | None) -> dict[str, str]:
    """Para `*_start`: valida el token del enlace y lo guarda en el estado OAuth."""

    if not link:
        return {}
    if request.cookies.get(LINK_COOKIE) != link or not await request.app.state.redis.exists(link_token_key(link)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El enlace para vincular expiró; empieza de nuevo")
    return {"link_token": link}


async def _bind(redis: Redis, uid: str, provider: str, puid: str) -> str:
    if puid == uid:
        return "already"
    existing = await redis.get(provider_link_key(puid))
    if existing:
        return "already" if str(existing) == uid else "conflict"
    methods = {m["id"]: m for m in await methods_for(redis, uid)}
    if methods[provider]["linked"]:
        return "duplicate"
    if await redis.exists(*_identity_data_keys(puid)):
        return "conflict"
    if not await redis.set(provider_link_key(puid), uid, nx=True):
        return "conflict"
    await redis.hset(links_key(uid), provider, json.dumps({"puid": puid, "added_at": datetime.now(timezone.utc).isoformat()}))
    return "ok"


async def complete_link(request: Request, provider: str, identity: dict[str, str], token: str) -> Response:
    """Para `*_callback`: enlaza la identidad que acaba de entrar a la cuenta que inició el flujo."""

    redis: Redis = request.app.state.redis
    settings: AppSettings = request.app.state.settings
    result = "expired"
    raw = await redis.getdel(link_token_key(token))
    if raw and request.cookies.get(LINK_COOKIE) == token:
        record = json.loads(raw)
        session_raw = await redis.get(f"seismik:oauth:session:{request.cookies.get('seismik_session', '')}")
        session = json.loads(session_raw) if session_raw else {}
        fresh = 0 <= time.time() - float(session.get("authenticated_at", 0) or 0) <= LINK_COMPLETION_SECONDS
        if record.get("provider") == provider and session.get("uid") == record.get("uid") and fresh:
            result = await _bind(redis, str(record["uid"]), provider, str(identity["uid"]))
    response = RedirectResponse(f"{ACCOUNT_URL}?link={result}", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(LINK_COOKIE, path="/", domain=settings.oauth_cookie_domain)
    response.headers["Cache-Control"] = "no-store"
    return response


# Las mismas rutas de eliminación inmediata, alcanzables desde auth.seismik.org.
router.add_api_route("/erasure", account_erasure.erasure_summary, methods=["GET"])
router.add_api_route("/erasure", account_erasure.erase_my_account, methods=["POST"])

__all__ = ["router", "link_state", "complete_link", "provider_link_key", "methods_for"]
