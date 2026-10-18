"""Correos de acceso (verificar correo y cambiar contraseña) enviados por Seismik, no por Firebase.

Firebase sólo permite editar sus plantillas a quien tiene el proyecto desbloqueado, y su enlace pasa
por una página genérica. Aquí el servidor pide a Firebase el código de acción, arma el enlace directo a la
página de acceso de Seismik (que ya sabe aplicarlo) y envía el correo con su diseño por Resend.

Si algo falla, la página de acceso cae de vuelta al correo de Firebase: nadie se queda sin poder entrar.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from redis.asyncio import Redis

from api.config import AppSettings
from api.dependencies import get_app_settings, get_redis
from api.mail_templates import password_reset, verify_email
from api.mailer import Mailer

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/oauth/email", tags=["email-actions"])

ALLOWED_ORIGIN = "https://auth.seismik.org"
ACTION_PAGE = "https://auth.seismik.org/id"


class ResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254)

    @field_validator("email")
    @classmethod
    def clean(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if "@" not in cleaned or any(ch.isspace() for ch in cleaned):
            raise ValueError("Escribe un correo válido")
        return cleaned


class VerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id_token: str = Field(min_length=20, max_length=16_384)


def action_link(firebase_link: str, mode: str) -> str:
    """Enlace directo a la página de Seismik con el código de acción que generó Firebase."""

    code = parse_qs(urlparse(firebase_link).query).get("oobCode", [""])[0]
    if not code:
        raise ValueError("Firebase no devolvió un código de acción")
    return f"{ACTION_PAGE}?{urlencode({'mode': mode, 'oobCode': code, 'lang': 'es'})}"


async def _rate(redis: Redis, key: str, limit: int, window_seconds: int) -> bool:
    bucket = f"seismik:email-actions:{key}:{int(time.time()) // window_seconds}"
    pipe = redis.pipeline(transaction=True)
    pipe.incr(bucket)
    pipe.expire(bucket, window_seconds * 2)
    count, _ = await pipe.execute()
    return int(count) <= limit


def _guard(request: Request, settings: AppSettings) -> Mailer:
    # Sólo desde la página de acceso: impide que otra web dispare correos con el navegador de alguien.
    if request.headers.get("origin") != ALLOWED_ORIGIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Origen no permitido")
    mailer = Mailer(settings)
    if not mailer.enabled:
        # La página usa el correo de Firebase en su lugar.
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "El envío de correo de Seismik no está activo")
    return mailer


def _client_bucket(request: Request, settings: AppSettings) -> str:
    host = request.client.host if request.client else "unknown"
    if settings.edge_origin_secret.get_secret_value():
        host = request.headers.get("cf-connecting-ip") or host
    return hashlib.sha256(host.encode()).hexdigest()[:20]


@router.post("/reset-request", status_code=status.HTTP_202_ACCEPTED)
async def request_password_reset(
    body: ResetRequest, request: Request,
    settings: AppSettings = Depends(get_app_settings), redis: Redis = Depends(get_redis),
) -> dict[str, bool]:
    mailer = _guard(request, settings)
    if not await _rate(redis, f"ip:{_client_bucket(request, settings)}", 20, 60):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Demasiados intentos; espera un minuto")
    email_hash = hashlib.sha256(body.email.encode()).hexdigest()[:20]
    # Siempre la misma respuesta, exista o no la cuenta: no se puede usar para averiguar quién tiene una.
    if not await _rate(redis, f"reset:{email_hash}", 3, 3600):
        return {"accepted": True}
    from firebase_admin import auth

    from api.developer_keys import _firebase_app

    try:
        link = await asyncio.to_thread(auth.generate_password_reset_link, body.email, None, _firebase_app(request))
        await mailer.send(password_reset(body.email, link=action_link(link, "resetPassword")))
    except auth.UserNotFoundError:
        pass
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001 - no revelar si la cuenta existe; el error queda en el registro
        LOGGER.exception("No se pudo preparar el correo de recuperación")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "No se pudo enviar el correo") from None
    return {"accepted": True}


@router.post("/verify-request", status_code=status.HTTP_202_ACCEPTED)
async def request_email_verification(
    body: VerifyRequest, request: Request,
    settings: AppSettings = Depends(get_app_settings), redis: Redis = Depends(get_redis),
) -> dict[str, Any]:
    mailer = _guard(request, settings)
    if not await _rate(redis, f"ip:{_client_bucket(request, settings)}", 20, 60):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Demasiados intentos; espera un minuto")
    from firebase_admin import auth

    from api.developer_keys import _firebase_app

    app = _firebase_app(request)
    try:
        identity = await asyncio.to_thread(auth.verify_id_token, body.id_token, app, True)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No se pudo validar tu sesión") from exc
    email = str(identity.get("email") or "")
    if not email:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "La cuenta no tiene correo")
    if identity.get("email_verified"):
        return {"accepted": True, "already_verified": True}
    if not await _rate(redis, f"verify:{hashlib.sha256(str(identity['uid']).encode()).hexdigest()[:20]}", 5, 3600):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Ya enviamos varios enlaces; revisa tu correo y tu carpeta de spam")
    try:
        link = await asyncio.to_thread(auth.generate_email_verification_link, email, None, app)
        sent = await mailer.send(verify_email(email, link=action_link(link, "verifyEmail")))
    except Exception:  # noqa: BLE001
        LOGGER.exception("No se pudo preparar el correo de verificación")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "No se pudo enviar el correo") from None
    if not sent:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "El correo no salió")
    return {"accepted": True}
