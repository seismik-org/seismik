"""Solicitud pública de eliminación de cuenta desde seismik.org.

No borra nada por sí sola: quien escribe un correo ajeno no debería poder
borrar la cuenta de otra persona sólo por teclearla en un formulario público.
Lo que hace es dejar la solicitud en la bitácora, protegida de spam con
Turnstile y un límite por IP, para que el equipo la verifique y complete por
el mismo canal que ya se documenta en la página: contactando al correo
indicado. Es el mismo compromiso que antes exigía redactar el correo a mano;
esto sólo evita ese paso manual.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import secrets
from datetime import datetime, timezone
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from redis.asyncio import Redis

from api.config import AppSettings
from api.dependencies import get_app_settings, get_redis

LOGGER = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/account", tags=["account-deletion"])

# Une el hostname a la acción: un token que Turnstile emitió para crear una
# clave de la API en devs.seismik.org no debe servir aquí, ni al revés.
TURNSTILE_ACTION = "delete_account_request"

_EMAIL_PATTERN = re.compile(r"^[^\s@]{1,64}@[^\s@]{1,255}\.[^\s@]{2,24}$")


class DeletionRequestPayload(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    scope: Literal["full", "partial"] = "full"
    details: str | None = Field(default=None, max_length=2_000)
    turnstile_token: str | None = Field(default=None, max_length=2_048)

    @field_validator("email")
    @classmethod
    def clean_email(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if not _EMAIL_PATTERN.match(cleaned):
            raise ValueError("Escribe un correo válido")
        return cleaned

    @field_validator("details")
    @classmethod
    def clean_details(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class DeletionRequestResponse(BaseModel):
    request_id: str
    message: str


class DeletionFormConfig(BaseModel):
    enabled: bool
    site_key: str | None = None
    action: str | None = None


async def _verify_turnstile(request: Request, token: str | None) -> None:
    settings: AppSettings = request.app.state.settings
    site_key = settings.turnstile_site_key.strip()
    secret = settings.turnstile_secret_key.get_secret_value()
    if not site_key and not secret:
        # Entorno local o beta sin Turnstile configurado: no bloquear la
        # solicitud por un control de abuso que aún no existe ahí.
        return
    if not site_key or not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="La verificación de seguridad está configurándose; inténtalo de nuevo pronto",
        )
    if not token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Completa la verificación de seguridad para enviar la solicitud",
        )

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                "https://challenges.cloudflare.com/turnstile/v0/siteverify",
                data={"secret": secret, "response": token},
            )
            response.raise_for_status()
            result = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No fue posible verificar la solicitud; inténtalo de nuevo",
        ) from exc

    if (
        not result.get("success")
        or result.get("hostname") != settings.turnstile_web_hostname
        or result.get("action") != TURNSTILE_ACTION
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="La verificación de seguridad no fue válida; inténtalo de nuevo",
        )


async def _enforce_rate(request: Request, redis: Redis, settings: AppSettings) -> None:
    """Una ventana de una hora por IP.

    El formulario no exige sesión, así que no hay cuenta de la que colgar el
    límite: sin esto, cualquiera podría llenar la bitácora de solicitudes o
    forzar llamadas a Turnstile sin freno. No se guarda la IP en la
    solicitud misma, sólo se usa aquí, de paso, para contar.
    """

    client_host = request.client.host if request.client else "unknown"
    # No se necesita la IP en claro para contar: su hash basta y evita
    # dejarla en Redis si alguien lista las claves del contador.
    bucket = hashlib.sha256(client_host.encode()).hexdigest()[:16]
    window = datetime.now(timezone.utc).strftime("%Y%m%d%H")
    counter = f"seismik:account-deletion-requests:{bucket}:{window}"

    pipe = redis.pipeline(transaction=True)
    pipe.incr(counter)
    pipe.expire(counter, 7_200)
    count, _ = await pipe.execute()
    if count > settings.account_deletion_requests_per_hour:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Demasiadas solicitudes desde este origen; inténtalo más tarde",
        )


@router.get("/deletion-config", response_model=DeletionFormConfig)
async def deletion_config(
    settings: AppSettings = Depends(get_app_settings),
) -> DeletionFormConfig:
    """Lo mínimo que necesita el formulario: si hay que mostrar Turnstile y con
    qué site key. El secret nunca sale de aquí."""

    enabled = bool(settings.turnstile_site_key.strip())
    return DeletionFormConfig(
        enabled=enabled,
        site_key=settings.turnstile_site_key.strip() or None,
        action=TURNSTILE_ACTION if enabled else None,
    )


@router.post(
    "/deletion-requests",
    response_model=DeletionRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_deletion_request(
    payload: DeletionRequestPayload,
    request: Request,
    settings: AppSettings = Depends(get_app_settings),
    redis: Redis = Depends(get_redis),
) -> DeletionRequestResponse:
    await _verify_turnstile(request, payload.turnstile_token)
    await _enforce_rate(request, redis, settings)

    request_id = "delreq_" + secrets.token_hex(8)
    event = {
        "request_id": request_id,
        "received_at": datetime.now(timezone.utc).isoformat(),
        "email": payload.email,
        "scope": payload.scope,
        "details": payload.details or "",
        "source": "web",
    }
    await redis.xadd(
        settings.account_deletion_request_stream,
        {"payload": json.dumps(event, ensure_ascii=False)},
        maxlen=settings.stream_maxlen,
        approximate=True,
    )
    LOGGER.info(
        "Account deletion request received request_id=%s scope=%s",
        request_id,
        payload.scope,
    )
    return DeletionRequestResponse(
        request_id=request_id,
        message="Recibimos tu solicitud. Te escribiremos a ese correo para verificarla.",
    )
