"""Revisión interna de los reportes ciudadanos (app y ifeltit.seismik.org).

La usa admin.seismik.org con el mismo acceso que el resto del panel
(`api.admin.require_admin`). La revisión nunca borra el reporte del stream:
guarda aparte si es válido o se descarta, con quién y cuándo.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
from pydantic import BaseModel
from redis.asyncio import Redis

from api.admin import require_admin
from api.config import AppSettings
from api.dependencies import get_app_settings, get_redis
from reporting.plausibility import assess
from reporting.web import official_events

router = APIRouter(prefix="/admin")

REVIEW_KEY = "seismik:reports:review"
STREAM_ID = r"^\d{1,20}-\d{1,20}$"
# Datos técnicos del bus o del dispositivo que no aportan a la revisión.
HIDDEN_FIELDS = {"device_id", "event_id", "plausibility", "consent_version", "type"}


class Review(BaseModel):
    status: Literal["valid", "dismissed", "pending"]


def _received_at(stream_id: str) -> str:
    milliseconds = int(stream_id.split("-", 1)[0])
    return datetime.fromtimestamp(milliseconds / 1000, timezone.utc).isoformat()


async def _entries(redis: Redis, stream: str, limit: int) -> list[tuple[str, dict[str, Any]]]:
    raw = cast(list[tuple[str, dict[str, str]]], await redis.xrevrange(stream, count=limit))
    entries: list[tuple[str, dict[str, Any]]] = []
    for stream_id, fields in raw:
        try:
            payload = json.loads(fields["payload"])
        except (KeyError, ValueError, TypeError):
            continue
        if isinstance(payload, dict):
            entries.append((stream_id, payload))
    return entries


@router.get("/reports")
async def list_reports(
    response: Response,
    limit: int = Query(default=500, ge=1, le=2000),
    admin: str = Depends(require_admin),
    settings: AppSettings = Depends(get_app_settings),
    redis: Redis = Depends(get_redis),
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    events = await official_events(redis, settings)
    reviews = cast(dict[str, str], await redis.hgetall(REVIEW_KEY))
    reports: list[dict[str, Any]] = []
    streams = (("felt", settings.felt_reports_stream), ("damage", settings.damage_reports_stream))
    for kind, stream in streams:
        for stream_id, payload in await _entries(redis, stream, limit):
            event = events.get(str(payload.get("earthquake_event_id") or ""))
            review_raw = reviews.get(f"{stream}|{stream_id}")
            reports.append(
                {
                    "id": f"{stream}|{stream_id}",
                    "stream_id": stream_id,
                    "received_at": _received_at(stream_id),
                    "kind": kind,
                    "source": "web" if payload.get("source") == "web" else "app",
                    "report": {k: v for k, v in payload.items() if k not in HIDDEN_FIELDS},
                    "event": event,
                    # Se recalcula: el sismo pudo revisarse después del envío.
                    "plausibility": assess(payload, event),
                    "review": json.loads(review_raw) if review_raw else None,
                }
            )
    reports.sort(key=lambda item: str(item["received_at"]), reverse=True)
    return {"admin": admin, "reports": reports[:limit]}


@router.post("/reports/{stream}/{stream_id}/review")
async def review_report(
    review: Review,
    response: Response,
    stream: Literal["felt", "damage"],
    stream_id: str = Path(pattern=STREAM_ID),
    admin: str = Depends(require_admin),
    settings: AppSettings = Depends(get_app_settings),
    redis: Redis = Depends(get_redis),
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    name = settings.felt_reports_stream if stream == "felt" else settings.damage_reports_stream
    if not await redis.xrange(name, min=stream_id, max=stream_id):
        raise HTTPException(404, "Reporte no encontrado")
    field = f"{name}|{stream_id}"
    if review.status == "pending":
        await redis.hdel(REVIEW_KEY, field)
        return {"id": field, "review": None}
    record = {
        "status": review.status,
        "by": admin,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    await redis.hset(REVIEW_KEY, field, json.dumps(record))
    return {"id": field, "review": record}
