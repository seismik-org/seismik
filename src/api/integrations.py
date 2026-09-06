"""Webhooks de organizaciones para el Sprint 6.

Este módulo entrega información sísmica, nunca órdenes de control. Todos los
mensajes incluyen una barrera contractual ``simulation_only`` para que una
integración de pruebas no pueda presentarse como señal apta para gas,
ascensores, agua o electricidad.
"""
from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import secrets
import socket
from datetime import datetime, timezone
from typing import Any, Literal
from urllib.parse import urlparse

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field, HttpUrl, field_validator

from api.developer_keys import get_developer_identity
from integrations.security import derive_webhook_secret

router = APIRouter(prefix="/v1/developer/webhooks", tags=["organization-webhooks"])

EVENT_TYPES = frozenset({"earthquake_candidate", "official_report_update"})
SAFETY_MODE: Literal["simulation_only"] = "simulation_only"


class WebhookCreateRequest(BaseModel):
    name: str = Field(min_length=3, max_length=60)
    endpoint: HttpUrl
    event_types: set[str] = Field(default_factory=lambda: {"official_report_update"})
    mode: Literal["simulation_only"] = SAFETY_MODE

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if len(normalized) < 3:
            raise ValueError("Name must contain at least three visible characters")
        return normalized

    @field_validator("event_types")
    @classmethod
    def validate_event_types(cls, value: set[str]) -> set[str]:
        if not value or not value.issubset(EVENT_TYPES):
            raise ValueError("Unsupported or empty webhook event type set")
        return value


class WebhookSummary(BaseModel):
    webhook_id: str
    name: str
    endpoint: str
    event_types: list[str]
    mode: Literal["simulation_only"]
    status: Literal["active", "disabled"]
    created_at: str
    last_delivered_at: str | None = None
    last_error: str | None = None


class WebhookSecretResponse(WebhookSummary):
    signing_secret: str
    warning: str = "Guárdalo ahora: Seismik no volverá a mostrar este secreto."


class WebhookListResponse(BaseModel):
    webhooks: list[WebhookSummary]
    safety_notice: str = (
        "Integración de simulación: nunca conecta ni autoriza controles físicos de IoT."
    )


def _summary(record: dict[str, str]) -> WebhookSummary:
    return WebhookSummary(
        webhook_id=record["webhook_id"],
        name=record["name"],
        endpoint=record["endpoint"],
        event_types=sorted(filter(None, record.get("event_types", "").split(","))),
        mode="simulation_only",
        status=record.get("status", "active"),  # type: ignore[arg-type]
        created_at=record["created_at"],
        last_delivered_at=record.get("last_delivered_at") or None,
        last_error=record.get("last_error") or None,
    )


async def _is_safe_public_https(url: str) -> bool:
    """Evita SSRF hacia metadatos cloud, loopback y redes privadas."""

    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        return False
    try:
        addresses = await asyncio.to_thread(
            socket.getaddrinfo, parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM
        )
    except OSError:
        return False
    for _family, _kind, _proto, _canon, sockaddr in addresses:
        address = ipaddress.ip_address(sockaddr[0])
        if not address.is_global:
            return False
    return bool(addresses)


async def _owned_records(request: Request, uid: str) -> list[dict[str, str]]:
    ids = await request.app.state.redis.smembers(f"seismik:webhooks:{uid}")
    records: list[dict[str, str]] = []
    for webhook_id in sorted(ids):
        record = await request.app.state.redis.hgetall(f"seismik:webhook:{webhook_id}")
        if record and record.get("uid") == uid:
            records.append(record)
    return records


async def _identity_from_portal(
    request: Request,
    authorization: str | None = Header(default=None),
    seismik_session: str | None = Cookie(default=None),
) -> dict[str, Any]:
    return await get_developer_identity(request, authorization, seismik_session)


@router.get("", response_model=WebhookListResponse)
async def list_webhooks(
    request: Request,
    identity: dict[str, Any] = Depends(_identity_from_portal),
) -> WebhookListResponse:
    records = await _owned_records(request, str(identity["uid"]))
    return WebhookListResponse(webhooks=sorted((_summary(item) for item in records), key=lambda item: item.created_at, reverse=True))


@router.post("", response_model=WebhookSecretResponse, status_code=status.HTTP_201_CREATED)
async def create_webhook(
    payload: WebhookCreateRequest,
    request: Request,
    identity: dict[str, Any] = Depends(_identity_from_portal),
) -> WebhookSecretResponse:
    endpoint = str(payload.endpoint).rstrip("/")
    if not await _is_safe_public_https(endpoint):
        raise HTTPException(status_code=422, detail="Webhook endpoint must resolve only to public HTTPS addresses")
    uid = str(identity["uid"])
    webhook_id = "wh_" + secrets.token_hex(10)
    signing_secret = derive_webhook_secret(
        request.app.state.settings.integration_webhook_master_secret.get_secret_value(), webhook_id
    )
    now = datetime.now(timezone.utc).isoformat()
    record = {
        "webhook_id": webhook_id,
        "uid": uid,
        "name": payload.name,
        "endpoint": endpoint,
        "event_types": ",".join(sorted(payload.event_types)),
        "mode": SAFETY_MODE,
        "status": "active",
        "secret_digest": hashlib.sha256(signing_secret.encode()).hexdigest(),
        "created_at": now,
        "last_delivered_at": "",
        "last_error": "",
    }
    pipe = request.app.state.redis.pipeline(transaction=True)
    pipe.hset(f"seismik:webhook:{webhook_id}", mapping=record)
    pipe.sadd(f"seismik:webhooks:{uid}", webhook_id)
    pipe.sadd("seismik:webhooks:active", webhook_id)
    pipe.xadd(
        request.app.state.settings.integration_audit_stream,
        {"action": "webhook.created", "uid": uid, "webhook_id": webhook_id, "at": now},
        maxlen=request.app.state.settings.stream_maxlen,
        approximate=True,
    )
    await pipe.execute()
    return WebhookSecretResponse(**_summary(record).model_dump(), signing_secret=signing_secret)


@router.delete("/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def disable_webhook(
    webhook_id: str,
    request: Request,
    identity: dict[str, Any] = Depends(_identity_from_portal),
) -> None:
    record = await request.app.state.redis.hgetall(f"seismik:webhook:{webhook_id}")
    if not record or record.get("uid") != str(identity["uid"]):
        raise HTTPException(status_code=404, detail="Webhook not found")
    now = datetime.now(timezone.utc).isoformat()
    pipe = request.app.state.redis.pipeline(transaction=True)
    pipe.hset(f"seismik:webhook:{webhook_id}", mapping={"status": "disabled"})
    pipe.srem("seismik:webhooks:active", webhook_id)
    pipe.xadd(
        request.app.state.settings.integration_audit_stream,
        {"action": "webhook.disabled", "uid": str(identity["uid"]), "webhook_id": webhook_id, "at": now},
        maxlen=request.app.state.settings.stream_maxlen,
        approximate=True,
    )
    await pipe.execute()
