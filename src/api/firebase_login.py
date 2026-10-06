"""Firebase proves an identity; Redis keeps the existing Seismik account ID."""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from typing import Any

from fastapi import APIRouter, Cookie, HTTPException, Request
from firebase_admin import auth
from pydantic import BaseModel, Field

from api.developer_keys import _firebase_app
from api.oauth import _finish_login

router = APIRouter(prefix="/v1/oauth/email", tags=["oauth"])


class EmailExchange(BaseModel):
    id_token: str = Field(min_length=20, max_length=16_384)
    flow_id: str | None = Field(default=None, min_length=24, max_length=128)
    link: bool = False


def binding_key(uid: str) -> str:
    return "seismik:identity:firebase:" + hashlib.sha256(uid.encode()).hexdigest()


async def resolve_identity(request: Request, identity: dict[str, Any]) -> dict[str, Any]:
    """NX makes the first binding immutable; no lookup or merge by email."""
    uid = str(identity["uid"])
    key = binding_key(uid)
    await request.app.state.redis.set(key, uid, nx=True)
    account_uid = await request.app.state.redis.get(key)
    return {**identity, "uid": account_uid}


async def validate_session(request: Request, user: dict[str, Any]) -> None:
    """Password resets, disabling and verification changes invalidate sessions."""
    if not user.get("firebase_uid"):
        return
    try:
        record = await asyncio.to_thread(
            auth.get_user, user["firebase_uid"], app=_firebase_app(request)
        )
    except Exception as exc:
        raise HTTPException(401, "Sesión expirada; vuelve a iniciar sesión") from exc
    if (
        record.disabled
        or not record.email_verified
        or float(user.get("firebase_auth_time", 0)) * 1000 < record.tokens_valid_after_timestamp
    ):
        raise HTTPException(401, "Sesión expirada; vuelve a iniciar sesión")


@router.get("/config")
async def email_config(request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    enabled = settings.email_login_enabled and all((
        settings.firebase_web_api_key, settings.firebase_web_project_id,
        settings.firebase_web_auth_domain, settings.firebase_web_app_id,
    ))
    return {"enabled": bool(enabled), "firebase": {
        "apiKey": settings.firebase_web_api_key,
        "authDomain": settings.firebase_web_auth_domain,
        "projectId": settings.firebase_web_project_id,
        "appId": settings.firebase_web_app_id,
    } if enabled else None}


@router.post("/exchange")
async def email_exchange(
    request: Request, body: EmailExchange, seismik_session: str | None = Cookie(default=None),
) -> Any:
    if not request.app.state.settings.email_login_enabled:
        raise HTTPException(503, "El acceso con correo aún no está disponible")
    # Browser-only endpoint: Origin plus JSON prevents login CSRF and linking CSRF.
    if request.headers.get("origin") != "https://auth.seismik.org":
        raise HTTPException(403, "Origen de acceso no permitido")
    bucket = hashlib.sha256((request.client.host if request.client else "unknown").encode()).hexdigest()
    key = f"seismik:email-rate:{bucket}:{int(time.time()) // 60}"
    pipe = request.app.state.redis.pipeline(transaction=True)
    pipe.incr(key)
    pipe.expire(key, 120)
    count, _ = await pipe.execute()
    if count > 20:
        raise HTTPException(429, "Demasiados intentos; espera un minuto", headers={"Retry-After": "60"})
    try:
        identity = await asyncio.to_thread(
            auth.verify_id_token, body.id_token, app=_firebase_app(request), check_revoked=True,
        )
    except Exception as exc:
        raise HTTPException(401, "No se pudo validar el acceso; vuelve a intentarlo") from exc
    if not identity.get("email_verified") or not identity.get("email"):
        raise HTTPException(403, "Verifica tu correo antes de continuar")
    if identity.get("firebase", {}).get("sign_in_provider") != "password":
        raise HTTPException(403, "Inicia sesión con correo y contraseña")
    auth_time = int(identity.get("auth_time", 0))
    if not 0 <= time.time() - auth_time <= 300:
        raise HTTPException(401, "Vuelve a iniciar sesión para confirmar tu identidad")
    firebase_uid = str(identity["uid"])
    redis = request.app.state.redis
    flow = None
    if body.flow_id:
        raw = await redis.get(f"seismik:oauth:identity:{body.flow_id}")
        flow = json.loads(raw) if raw else None
        if not flow or flow.get("provider") != "email" or not flow.get("app_challenge"):
            raise HTTPException(410, "La solicitud móvil expiró; inicia el acceso desde la app")
    if body.link:
        raw = await redis.get(f"seismik:oauth:session:{seismik_session}") if seismik_session else None
        existing = json.loads(raw) if raw else {}
        if not existing.get("uid") or existing.get("firebase_uid") or not 0 <= time.time() - float(existing.get("authenticated_at", 0)) <= 300:
            raise HTTPException(401, "Primero vuelve a entrar con Apple, Google o GitHub y regresa aquí")
        # A Firebase identity with prior usage must keep its original account/data.
        data_keys = (
            f"seismik:developer-keys:{firebase_uid}", f"seismik:developer-profile:{firebase_uid}",
            f"seismik:family:account:{firebase_uid}", f"seismik:account:devices:{firebase_uid}",
            f"seismik:webhooks:{firebase_uid}", f"seismik:billing:balance:{firebase_uid}",
            f"seismik:billing:ledger:{firebase_uid}",
        )
        if await redis.exists(*data_keys):
            raise HTTPException(409, "Esta identidad ya tiene datos; conserva sus accesos y contacta soporte")
        key = binding_key(firebase_uid)
        await redis.set(key, str(existing["uid"]), nx=True)
        if await redis.get(key) != str(existing["uid"]):
            raise HTTPException(409, "Esta identidad ya está vinculada; no se modificó ninguna cuenta")
    resolved = await resolve_identity(request, identity)
    user = {
        "uid": str(resolved["uid"]), "email": str(identity["email"]),
        "name": str(identity.get("name") or identity["email"].split("@")[0]),
        "firebase_uid": firebase_uid, "firebase_auth_time": str(auth_time),
    }
    if flow:
        if not await redis.getdel(f"seismik:oauth:identity:{body.flow_id}"):
            raise HTTPException(410, "La solicitud móvil ya fue utilizada")
    response = await _finish_login(request, user, flow.get("return_to") if flow else None, flow.get("app_challenge") if flow else None)
    # The client follows the approved target only after Firebase signOut.
    response.status_code = 200
    response.body = json.dumps({"redirect": response.headers["location"]}).encode()
    del response.headers["location"]
    response.headers["content-type"] = "application/json"
    response.headers["content-length"] = str(len(response.body))
    response.headers["cache-control"] = "no-store"
    if seismik_session:
        await redis.delete(f"seismik:oauth:session:{seismik_session}")
    return response
