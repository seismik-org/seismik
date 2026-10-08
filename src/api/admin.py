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

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request, Response
from redis.asyncio import Redis

from api.config import AppSettings
from api.dependencies import get_app_settings, get_redis

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
    ("web_sessions", "seismik:oauth:session:"),
    ("app_sessions", "seismik:oauth:mobile-session:"),
)
# Un recorrido acotado: el panel no debe competir con la API por Redis.
MAX_SCANNED_KEYS = 200_000
SECRET_FIELD = re.compile(
    r"token|secret|signature|password|hash|session|cookie|(^|_)ip($|_)|(^|_)key$", re.I
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
        "x_publisher": (settings.x_publisher_stream, "Publicaciones en X"),
    }


async def require_admin(
    request: Request,
    seismik_session: str | None = Cookie(default=None),
    settings: AppSettings = Depends(get_app_settings),
    redis: Redis = Depends(get_redis),
) -> str:
    raw = await redis.get(f"seismik:oauth:session:{seismik_session}") if seismik_session else None
    if not raw:
        raise HTTPException(401, "Inicia sesión en auth.seismik.org")
    session = json.loads(raw)
    from api.firebase_login import validate_session

    await validate_session(request, session)
    email = str(session.get("email") or "").strip().casefold()
    admins = {item.strip().casefold() for item in settings.admin_emails.split(",") if item.strip()}
    if not email or email not in admins:
        raise HTTPException(403, "Esta cuenta no tiene acceso a la administración de Seismik")
    return email


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "•••" if SECRET_FIELD.search(str(key)) and value_ else redact(value_)
            for key, value_ in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def _decode(fields: dict[str, str]) -> dict[str, Any]:
    """Los streams guardan JSON en `payload`; algunos guardan campos sueltos."""
    if "payload" in fields:
        try:
            payload = json.loads(fields["payload"])
            if isinstance(payload, dict):
                return payload
        except ValueError:
            pass
    return dict(fields)


def _stream_time(stream_id: str) -> datetime:
    return datetime.fromtimestamp(int(stream_id.split("-", 1)[0]) / 1000, timezone.utc)


async def _recent_count(redis: Redis, stream: str, since: datetime) -> int:
    start = f"{int(since.timestamp() * 1000)}-0"
    raw = await redis.xrange(stream, min=start, max="+", count=10_000)
    return len(raw)


@router.get("/me")
async def admin_me(admin: str = Depends(require_admin)) -> dict[str, str]:
    return {"email": admin}


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
    return {
        "name": name,
        "title": title,
        "total": int(await redis.xlen(stream)),
        "records": [
            {"id": stream_id, "at": _stream_time(stream_id).isoformat(), "data": redact(_decode(fields))}
            for stream_id, fields in raw
        ],
    }
