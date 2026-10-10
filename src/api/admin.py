"""admin.seismik.org: números y registros internos de Seismik.

Sólo entran los correos de `admin_emails` con la sesión de auth.seismik.org
(cookie `seismik_session`). Todo es de lectura salvo la revisión de reportes, y
los registros ocultan tokens, firmas, secretos e IP antes de salir de la API.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, StrictBool
from redis.asyncio import Redis

from api.admin_notify import notify
from api.admin_privacy import view_for
from api.admin_security import readonly, require_action, require_admin
from api.config import AppSettings
from api.dependencies import get_app_settings, get_redis
from api.runtime_controls import FEATURES, PAUSE_KEY, state

router = APIRouter(prefix="/v1/admin", tags=["admin"])

# Prefijos de claves que se cuentan en el resumen. El orden importa: gana el
# primero que coincide, así `seismik:device-session:` no cuenta como dispositivo.
KEY_GROUPS = (
    ("devices", "seismik:device:"),
    ("accounts_with_devices", "seismik:account:devices:"),
    ("developer_accounts", "seismik:developer-profile:"),
    ("api_keys", "seismik:developer-key:"),
    ("webhook_owners", "seismik:webhooks:"),
    ("family_circles", "seismik:family:circle:"),
    ("admin_sessions", "seismik:admin:session:"),
    ("web_sessions", "seismik:oauth:session:"),
    ("app_sessions", "seismik:oauth:mobile-session:"),
)
# Un recorrido acotado: el panel no debe competir con la API por Redis.
MAX_SCANNED_KEYS = 200_000
SECRET_FIELD = re.compile(
    r"token|secret|signature|password|hash|session|cookie|authorization|credential|"
    r"private.?key|totp|recovery|otp|mfa|client.?ip|ip.?address|(^|_)ip($|_)|(^|_)key$", re.I
)


def streams(settings: AppSettings) -> dict[str, tuple[str, str]]:
    """Registros que se pueden consultar: nombre público -> (stream, título)."""
    return {
        "official": (settings.official_stream, "Sismos oficiales"),
        "candidates": (settings.candidate_stream, "Detecciones preliminares"),
        "alerts": (settings.alert_ledger_stream, "Alertas enviadas"),
        "felt": (settings.felt_reports_stream, "Reportes «¿Lo sentiste?»"),
        "damage": (settings.damage_reports_stream, "Reportes de daños"),
        "family": (settings.family_notification_stream, "Avisos de familia"),
        "deletions": (settings.account_deletion_request_stream, "Solicitudes de borrado"),
        "developer_audit": (settings.developer_audit_stream, "Auditoría del portal"),
        "integrations": (settings.integration_stream, "Integraciones"),
        "integration_failures": (settings.integration_dead_letter_stream, "Integraciones fallidas"),
        "dead_letter": (settings.dead_letter_stream, "Eventos fallidos"),
        "x_publisher": ("stream:seismik:x-audit", "Publicaciones en X"),
        "facebook_audit": ("stream:seismik:facebook-audit", "Publicaciones en Facebook"),
        "integration_audit": (settings.integration_audit_stream, "Auditoría de integraciones"),
        "push_audit": (settings.push_audit_stream, "Pruebas de notificaciones"),
    }



def redact(value: Any, depth: int = 0) -> Any:
    if depth > 12:
        return "•••"
    if isinstance(value, dict):
        return {
            key: "•••" if SECRET_FIELD.search(str(key)) and value_ else redact(value_, depth + 1)
            for key, value_ in value.items()
        }
    if isinstance(value, list):
        return [redact(item, depth + 1) for item in value]
    if isinstance(value, str):
        if value.lstrip().startswith(("{", "[")):
            try:
                return redact(json.loads(value, parse_constant=lambda _: None), depth + 1)
            except (ValueError, RecursionError):
                return "•••"
        value = re.sub(r"(?i)(Bearer\s+)[A-Za-z0-9._~+/=-]+", r"\1•••", value)
        value = re.sub(r"(?i)((?:token|secret|password|api_key|signature)=)[^&\s]+", r"\1•••", value)
        value = re.sub(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", "•••", value)
    return value


def _decode(fields: dict[str, str]) -> dict[str, Any]:
    """Los streams guardan JSON en `payload`; algunos guardan campos sueltos."""
    if "payload" in fields:
        try:
            payload = json.loads(fields["payload"], parse_constant=lambda _: None)
            if isinstance(payload, dict):
                return payload
        except (ValueError, RecursionError):
            pass
        # Malformed payloads must not turn a decoding failure into a secret leak.
        return {"payload": "•••"}
    return dict(fields)


def _stream_time(stream_id: str) -> datetime:
    return datetime.fromtimestamp(int(stream_id.split("-", 1)[0]) / 1000, timezone.utc)


async def _recent_count(redis: Redis, stream: str, since: datetime) -> int:
    start = f"{int(since.timestamp() * 1000)}-0"
    raw = cast(list[Any], await redis.xrange(stream, min=start, max="+", count=10_000))
    return len(raw)


@router.get("/me")
async def admin_me(admin: str = Depends(require_admin), settings: AppSettings = Depends(get_app_settings)) -> dict[str, Any]:
    return {"email": admin, "readonly": readonly(settings, admin)}


@router.get("/overview")
async def overview(
    response: Response,
    admin: str = Depends(require_admin),
    settings: AppSettings = Depends(get_app_settings),
    redis: Redis = Depends(get_redis),
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    now = datetime.now(timezone.utc)
    stream_stats = []
    for name, (stream, title) in streams(settings).items():
        total = int(await redis.xlen(stream))
        last = cast(list[tuple[str, dict[str, str]]], await redis.xrevrange(stream, count=1))
        stream_stats.append(
            {
                "name": name,
                "title": title,
                "total": total,
                "last_24h": await _recent_count(redis, stream, now - timedelta(days=1)) if total else 0,
                "last_7d": await _recent_count(redis, stream, now - timedelta(days=7)) if total else 0,
                "last_at": _stream_time(last[0][0]).isoformat() if last else None,
            }
        )
    counts = {name: 0 for name, _ in KEY_GROUPS}
    scanned = 0
    complete = True
    async for key in redis.scan_iter(match="seismik:*", count=1000):
        scanned += 1
        if scanned > MAX_SCANNED_KEYS:
            complete = False
            break
        for name, prefix in KEY_GROUPS:
            if str(key).startswith(prefix):
                counts[name] += 1
                break
    return {
        "admin": admin,
        "generated_at": now.isoformat(),
        "streams": stream_stats,
        "keys": counts,
        "keys_complete": complete,
    }


@router.get("/records/{name}")
async def records(
    name: str,
    response: Response,
    limit: int = Query(default=100, ge=1, le=500),
    admin: str = Depends(require_admin),
    settings: AppSettings = Depends(get_app_settings),
    redis: Redis = Depends(get_redis),
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    available = streams(settings)
    if name not in available:
        raise HTTPException(404, "Registro desconocido")
    stream, title = available[name]
    raw = cast(list[tuple[str, dict[str, str]]], await redis.xrevrange(stream, count=limit))
    # Nombres, correos, mensajes y ubicaciones de clientes no salen de la API.
    private = view_for(name, settings)
    return {
        "name": name,
        "title": title,
        "total": int(await redis.xlen(stream)),
        "records": [
            {"id": stream_id, "at": _stream_time(stream_id).isoformat(), "data": private(redact(_decode(fields)))}
            for stream_id, fields in raw
        ],
    }


class ControlChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: StrictBool


@router.get("/controls")
async def controls(
    admin: str = Depends(require_admin), redis: Redis = Depends(get_redis),
) -> dict[str, Any]:
    return {"controls": await state(redis)}


@router.put("/controls/{feature}")
async def change_control(
    feature: str, change: ControlChange, request: Request,
    admin: str = Depends(require_admin),
    redis: Redis = Depends(get_redis),
    settings: AppSettings = Depends(get_app_settings),
) -> dict[str, Any]:
    if feature not in FEATURES:
        raise HTTPException(404, "Control desconocido")
    current = next(item for item in await state(redis) if item["id"] == feature)
    if change.enabled and not current["configured"]:
        raise HTTPException(409, "El servicio no está configurado o no está disponible para reanudarlo")
    await require_action(request, redis, f"control:{feature}:{str(change.enabled).lower()}")
    # The switch and its audit record succeed or fail together.
    pipe = redis.pipeline(transaction=True)
    pipe.hset(PAUSE_KEY, feature, "0" if change.enabled else "1")
    pipe.xadd(settings.developer_audit_stream, {
        "action": "operation.resumed" if change.enabled else "operation.paused",
        "feature": feature, "by": admin,
        "at": datetime.now(timezone.utc).isoformat(),
    }, maxlen=settings.stream_maxlen, approximate=True)
    await pipe.execute()
    notify(settings, f"{admin} {'reanudó' if change.enabled else 'pausó'}: {FEATURES[feature]}")
    return {"controls": await state(redis)}
