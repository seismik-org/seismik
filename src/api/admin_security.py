"""Isolated admin sessions, mandatory TOTP and single-use action approvals."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import struct
import time
from typing import Any
from urllib.parse import quote, urlencode

from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field
from redis.asyncio import Redis
from redis.exceptions import WatchError

from api.config import AppSettings
from api.dependencies import get_app_settings, get_redis

router = APIRouter(prefix="/v1/admin/auth", tags=["admin-security"])
COOKIE = "__Host-Seismik-Admin"
LOGIN_COOKIE = "__Host-Seismik-Admin-Login"
SESSION_PREFIX = "seismik:admin:session:"
MFA_PREFIX = "seismik:admin:mfa:"
BINDING_PREFIX = "seismik:admin:identity:"
ABSOLUTE_TTL = 8 * 3600
IDLE_TTL = 15 * 60
PREAUTH_TTL = 5 * 60


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def account(user: dict[str, Any]) -> str:
    # Never attach an authenticator to a mutable email address.
    return digest(str(user.get("firebase_uid") or user["uid"]))


def guard(request: Request, settings: AppSettings) -> None:
    production = settings.environment.lower() != "development"
    if production and (not request.scope.get("seismik.edge_authenticated")
                       or request.headers.get("x-seismik-admin-host") != "admin.seismik.org"):
        raise HTTPException(403, "Acceso sólo desde el borde autenticado del panel")
    allowed = {"https://admin.seismik.org"}
    if not production:
        allowed |= {"http://localhost:8080", "http://127.0.0.1:8080"}
    origin = request.headers.get("origin")
    if origin is not None and origin not in allowed:
        raise HTTPException(403, "Origen de administración no permitido")
    if request.headers.get("sec-fetch-site") == "cross-site" and request.method != "GET":
        raise HTTPException(403, "Petición de administración no permitida")
    if request.method not in {"GET", "HEAD", "OPTIONS"} and (
        origin not in allowed or request.headers.get("x-seismik-admin") != "1"
    ):
        raise HTTPException(403, "Petición de administración no permitida")


def cipher(settings: AppSettings) -> Fernet:
    try:
        return Fernet(settings.admin_mfa_encryption_key.get_secret_value().encode())
    except (ValueError, TypeError):
        raise HTTPException(503, "La protección MFA no está disponible") from None


def cookie(response: Response, token: str, ttl: int) -> None:
    response.set_cookie(COOKIE, token, max_age=ttl, secure=True, httponly=True,
                        samesite="strict", path="/")


async def audit(redis: Redis, settings: AppSettings, action: str, email: str) -> None:
    await redis.xadd(settings.developer_audit_stream,
                    {"action": action, "by": email, "at": str(int(time.time()))},
                    maxlen=settings.stream_maxlen, approximate=True)


async def rate(redis: Redis, identity: str, kind: str, limit: int, seconds: int) -> None:
    key = f"seismik:admin:rate:{kind}:{identity}:{int(time.time() // seconds)}"
    await redis.set(key, 0, ex=seconds * 2, nx=True)
    if int(await redis.incr(key)) > limit:
        raise HTTPException(429, "Demasiados intentos; espera antes de volver a probar")


async def primary(
    request: Request, response: Response,
    settings: AppSettings = Depends(get_app_settings), redis: Redis = Depends(get_redis),
) -> dict[str, Any]:
    guard(request, settings)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    token = request.cookies.get(COOKIE, "")
    raw = await redis.get(SESSION_PREFIX + digest(token)) if token else None
    try:
        user = json.loads(raw) if raw else {}
        now = time.time()
        age = now - float(user.get("authenticated_at", 0))
        idle = now - float(user.get("last_seen", 0))
        if not user.get("uid") or not 0 <= age <= ABSOLUTE_TTL or not 0 <= idle <= IDLE_TTL:
            raise ValueError
        if not user.get("mfa_version") and age > PREAUTH_TTL:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(401, "Inicia sesión en auth.seismik.org") from None
    email = str(user.get("email", "")).strip().casefold()
    if email not in {item.strip().casefold() for item in settings.admin_emails.split(",") if item.strip()}:
        raise HTTPException(403, "Esta cuenta no tiene acceso a la administración de Seismik")
    binding = await redis.get(BINDING_PREFIX + digest(email))
    if binding and binding != account(user):
        raise HTTPException(403, "Usa la identidad con la que configuraste MFA; otro proveedor requiere vinculación revisada")
    from api.firebase_login import validate_session

    await validate_session(request, user)
    await rate(redis, digest(token), "queries", 120, 60)
    user["email"] = email
    user["last_seen"] = now
    # XX cannot resurrect a session concurrently revoked by logout/MFA rotation.
    await redis.set(SESSION_PREFIX + digest(token), json.dumps(user),
                    ex=max(1, int(ABSOLUTE_TTL - age)), xx=True)
    request.state.admin_user = user
    return user


async def require_admin(
    request: Request, user: dict[str, Any] = Depends(primary),
    redis: Redis = Depends(get_redis),
) -> str:
    raw = await redis.get(MFA_PREFIX + account(user))
    record = json.loads(raw) if raw else {}
    if not user.get("mfa_version") or user["mfa_version"] != record.get("version"):
        raise HTTPException(428, "Configura o verifica tu autenticador para entrar")
    return str(user["email"])


async def require_action(request: Request, redis: Redis, action: str) -> None:
    token = request.headers.get("x-seismik-admin-approval", "")
    session_id = digest(request.cookies.get(COOKIE, ""))
    raw = await redis.getdel("seismik:admin:approval:" + digest(token)) if token else None
    if not raw or json.loads(raw) != {"session": session_id, "action": action}:
        raise HTTPException(428, "Verifica MFA de nuevo para confirmar este cambio")


@router.post("/start")
async def start(request: Request, settings: AppSettings = Depends(get_app_settings),
                redis: Redis = Depends(get_redis)) -> Response:
    guard(request, settings)
    cipher(settings)  # Fail closed before sending the visitor to OAuth.
    await rate(redis, digest(request.headers.get("x-seismik-client-ip", request.client.host if request.client else "unknown") if request.scope.get("seismik.edge_authenticated") else (request.client.host if request.client else "unknown")), "login", 20, 600)
    state = secrets.token_urlsafe(32)
    await redis.set("seismik:admin:login:" + digest(state), "1", ex=600)
    response = Response(content=json.dumps({"redirect": "https://auth.seismik.org/id"}),
                        media_type="application/json")
    response.set_cookie(LOGIN_COOKIE, state, max_age=600, secure=True, httponly=True,
                        samesite="lax", path="/")
    # Correlation only, no session credential. Apple returns a cross-site POST.
    response.set_cookie("seismik_after_login", "admin:" + state, max_age=600,
                        secure=True, httponly=True, samesite="none", path="/", domain=".seismik.org")
    return response


async def finish_admin_login(request: Request, user: dict[str, Any]) -> Response | None:
    marker = request.cookies.get("seismik_after_login", "")
    if not marker.startswith("admin:"):
        return None
    state = marker.removeprefix("admin:")
    redis = request.app.state.redis
    settings = request.app.state.settings
    if not await redis.getdel("seismik:admin:login:" + digest(state)):
        raise HTTPException(401, "Vuelve a iniciar el acceso desde el panel admin")
    email = str(user.get("email", "")).strip().casefold()
    if email not in {x.strip().casefold() for x in settings.admin_emails.split(",") if x.strip()}:
        raise HTTPException(403, "Esta cuenta no tiene acceso a la administración de Seismik")
    code = secrets.token_urlsafe(32)
    now = time.time()
    await redis.set("seismik:admin:handoff:" + digest(code),
                    json.dumps({"state": state, "user": {**user, "email": email,
                                "authenticated_at": now, "last_seen": now}}), ex=60)
    response = RedirectResponse("https://admin.seismik.org/?" + urlencode({"admin_code": code}), 303)
    response.delete_cookie("seismik_after_login", domain=".seismik.org", path="/")
    return response


class Exchange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=32, max_length=128)


@router.post("/exchange")
async def exchange(body: Exchange, request: Request,
                   settings: AppSettings = Depends(get_app_settings), redis: Redis = Depends(get_redis)) -> Response:
    guard(request, settings)
    raw = await redis.getdel("seismik:admin:handoff:" + digest(body.code))
    if not raw:
        raise HTTPException(401, "El acceso expiró; vuelve a iniciar sesión")
    ticket = json.loads(raw)
    if not hmac.compare_digest(ticket["state"], request.cookies.get(LOGIN_COOKIE, "")):
        raise HTTPException(401, "El acceso no corresponde a este navegador")
    token = secrets.token_urlsafe(48)
    await redis.set(SESSION_PREFIX + digest(token), json.dumps(ticket["user"]), ex=PREAUTH_TTL)
    response = Response(content='{"ok":true}', media_type="application/json")
    cookie(response, token, PREAUTH_TTL)
    response.delete_cookie(LOGIN_COOKIE, secure=True, httponly=True, samesite="lax", path="/")
    await audit(redis, settings, "admin.primary_login", ticket["user"]["email"])
    return response


@router.get("/status")
async def status(user: dict[str, Any] = Depends(primary), redis: Redis = Depends(get_redis)) -> dict[str, Any]:
    raw = await redis.get(MFA_PREFIX + account(user))
    record = json.loads(raw) if raw else {}
    return {"email": user["email"], "enrolled": bool(raw),
            "verified": bool(record and user.get("mfa_version") == record["version"])}


def otp(secret: str, counter: int, digits: int = 6) -> str:
    value = hmac.new(base64.b32decode(secret), struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = value[-1] & 15
    number = struct.unpack(">I", value[offset:offset + 4])[0] & 0x7fffffff
    return str(number % (10 ** digits)).zfill(digits)


def match_counter(secret: str, code: str, last: int) -> int | None:
    now = int(time.time() // 30)
    found = None
    for counter in (now - 1, now, now + 1):
        if hmac.compare_digest(otp(secret, counter), code) and counter > last:
            found = counter
    return found


@router.post("/enroll")
async def enroll(request: Request, user: dict[str, Any] = Depends(primary),
                 settings: AppSettings = Depends(get_app_settings), redis: Redis = Depends(get_redis)) -> dict[str, str]:
    identity = account(user)
    if await redis.exists(MFA_PREFIX + identity):
        raise HTTPException(409, "Ya hay un autenticador configurado")
    await rate(redis, identity, "enrollment", 5, 600)
    secret = base64.b32encode(secrets.token_bytes(20)).decode()
    encrypted = cipher(settings).encrypt(secret.encode()).decode()
    # An enrollment candidate is bound to one pre-auth session, expires in 5 min.
    await redis.set("seismik:admin:pending:" + digest(request.cookies[COOKIE]), encrypted, ex=300)
    uri = "otpauth://totp/" + quote("Seismik Admin:" + user["email"], safe="") + "?" + urlencode(
        {"secret": secret, "issuer": "Seismik Admin", "algorithm": "SHA1", "digits": 6, "period": 30})
    return {"secret": secret, "uri": uri}


class Verification(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=6, max_length=64)
    action: str | None = Field(default=None, max_length=160)


def valid_action(action: str) -> bool:
    return bool(re.fullmatch(r"control:(alerts|x|facebook):(true|false)|review:(felt|damage):\d{1,20}-\d{1,20}:(valid|dismissed|pending)", action))


@router.post("/verify")
async def verify(body: Verification, request: Request,
                 user: dict[str, Any] = Depends(primary), settings: AppSettings = Depends(get_app_settings),
                 redis: Redis = Depends(get_redis)) -> Response:
    identity = account(user)
    await rate(redis, identity, "mfa-minute", 5, 60)
    await rate(redis, identity, "mfa-hour", 20, 3600)
    if body.action and not valid_action(body.action):
        raise HTTPException(400, "Acción no permitida")
    code = body.code.strip().replace("-", "").replace(" ", "")
    key = MFA_PREFIX + identity
    pending_key = "seismik:admin:pending:" + digest(request.cookies[COOKIE])
    recovery: list[str] = []
    binding_key = BINDING_PREFIX + digest(user["email"])
    session_key = SESSION_PREFIX + digest(request.cookies[COOKIE])
    rotated_token = secrets.token_urlsafe(48)
    approval = secrets.token_urlsafe(32)
    for _ in range(3):
        async with redis.pipeline(transaction=True) as pipe:
            try:
                await pipe.watch(key, pending_key, session_key, binding_key)
                binding = await pipe.get(binding_key)
                if binding and binding != identity:
                    raise HTTPException(403, "Esta cuenta ya tiene otra identidad administrativa vinculada")
                if not await pipe.exists(session_key):
                    raise HTTPException(401, "La sesión ya se cerró")
                raw = await pipe.get(key)
                record = json.loads(raw) if raw else {}
                encrypted = record.get("secret") or await pipe.get(pending_key)
                if not encrypted:
                    raise HTTPException(428, "Configura primero tu autenticador")
                try:
                    secret = cipher(settings).decrypt(encrypted if isinstance(encrypted, bytes) else encrypted.encode()).decode()
                except InvalidToken:
                    raise HTTPException(503, "La protección MFA no está disponible") from None
                counter = match_counter(secret, code, record.get("last_counter", -1)) if re.fullmatch(r"\d{6}", code) else None
                recovery_hash = digest(code.lower())
                recovering = bool(record and not body.action and recovery_hash in record.get("recovery", []))
                if counter is None and not recovering:
                    await audit(redis, settings, "admin.mfa_failed", user["email"])
                    raise HTTPException(401, "Código incorrecto, expirado o ya utilizado")
                if body.action and (not record or user.get("mfa_version") != record["version"]):
                    raise HTTPException(428, "Verifica primero el acceso al panel")
                if not record:
                    recovery = [secrets.token_hex(16) for _ in range(10)]
                    record = {"version": secrets.token_urlsafe(24), "secret": encrypted,
                              "recovery": [digest(value) for value in recovery], "last_counter": -1}
                if recovering:
                    record["recovery"].remove(recovery_hash)
                else:
                    record["last_counter"] = counter
                pipe.multi()
                pipe.set(binding_key, identity, nx=True)
                pipe.set(key, json.dumps(record))
                pipe.delete(pending_key)
                pipe.xadd(settings.developer_audit_stream,
                          {"action": "admin.mfa_recovery" if recovering else "admin.mfa_verified",
                           "by": user["email"], "at": str(int(time.time()))},
                          maxlen=settings.stream_maxlen, approximate=True)
                if body.action:
                    pipe.set("seismik:admin:approval:" + digest(approval),
                             json.dumps({"session": digest(request.cookies[COOKIE]), "action": body.action}), ex=120)
                else:
                    elevated = {**user, "mfa_version": record["version"], "last_seen": time.time()}
                    pipe.delete(session_key)
                    pipe.set(SESSION_PREFIX + digest(rotated_token), json.dumps(elevated),
                             ex=max(1, int(ABSOLUTE_TTL - (time.time() - float(user["authenticated_at"])))))
                await pipe.execute()
                break
            except WatchError:
                continue
    else:
        raise HTTPException(409, "Otra verificación está en curso; vuelve a probar")
    if body.action:
        return Response(content=json.dumps({"approval": approval}), media_type="application/json")
    response = Response(content=json.dumps({"ok": True, "recovery_codes": recovery}), media_type="application/json")
    cookie(response, rotated_token, ABSOLUTE_TTL)
    return response


@router.post("/logout")
async def logout(request: Request, settings: AppSettings = Depends(get_app_settings),
                 redis: Redis = Depends(get_redis)) -> Response:
    guard(request, settings)
    token = request.cookies.get(COOKIE, "")
    await redis.delete(SESSION_PREFIX + digest(token), "seismik:admin:pending:" + digest(token))
    response = Response(content='{"ok":true}', media_type="application/json")
    response.delete_cookie(COOKIE, secure=True, httponly=True, samesite="strict", path="/")
    return response
