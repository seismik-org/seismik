"""LiveAhora calendar: central Seismik login, isolated durable Firestore document."""
from __future__ import annotations

import asyncio
import re
import secrets
from datetime import datetime, timezone
from typing import Any, Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from google.cloud import firestore
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from api.oauth import AFTER_LOGIN_COOKIE, current_session

router = APIRouter(prefix="/v1/liveahora", tags=["liveahora"])
ORIGIN = "https://liveahora.seismik.org"
COLLECTION = "liveahora_calendar"
MAX_EVENTS = 100
IMAGES = {"", "/assets/liveahora/banner.webp", "/assets/liveahora/logo.webp"}
PLATFORMS = {
    "youtube": {"youtube.com", "www.youtube.com", "youtu.be"},
    "kick": {"kick.com", "www.kick.com"},
    "twitch": {"twitch.tv", "www.twitch.tv"},
}


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=3, max_length=160)
    description: str = Field(default="", max_length=1000)
    starts_at: datetime
    ends_at: datetime
    platform: Literal["youtube", "kick", "twitch"]
    url: str = Field(max_length=1000)
    image: str = ""
    status: Literal["draft", "scheduled", "live", "finished", "cancelled"] = "draft"
    rights_confirmed: bool = False

    @field_validator("starts_at", "ends_at")
    @classmethod
    def aware_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Incluye la zona horaria del evento")
        return value.astimezone(timezone.utc)

    @field_validator("image")
    @classmethod
    def local_image(cls, value: str) -> str:
        if value not in IMAGES:
            raise ValueError("Selecciona una imagen de LiveAhora")
        return value

    @model_validator(mode="after")
    def valid_event(self) -> Event:
        parsed = urlsplit(self.url)
        if (parsed.scheme != "https" or parsed.hostname not in PLATFORMS[self.platform]
                or parsed.username or parsed.password or parsed.port not in (None, 443)
                or not parsed.path.strip("/")):
            raise ValueError("Usa un enlace HTTPS de la plataforma seleccionada")
        if not 0 < (self.ends_at - self.starts_at).total_seconds() <= 7 * 86400:
            raise ValueError("El fin debe ser posterior al inicio y no superar siete días")
        if self.status in {"scheduled", "live"} and not self.rights_confirmed:
            raise ValueError("Confirma los derechos del evento antes de publicarlo")
        return self


class SaveEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=0)
    event: Event


def store(request: Request) -> Any:
    existing = getattr(request.app.state, "liveahora_store", None)
    if existing is not None:
        return existing
    # ADC uses the Cloud Run service identity; no exported private keys are needed.
    try:
        settings = request.app.state.settings
        client = firestore.Client(project=settings.firebase_web_project_id or None,
                                  database=settings.liveahora_firestore_database)
        reference = client.collection(COLLECTION).document("schedule")
        request.app.state.liveahora_store = reference
        return reference
    except Exception:
        raise HTTPException(503, "El almacenamiento del cronograma no está configurado") from None


def read_schedule(request: Request) -> dict[str, Any]:
    try:
        return store(request).get().to_dict() or {"revision": 0, "events": {}}
    except Exception:
        raise HTTPException(503, "El cronograma no está disponible; vuelve a intentarlo") from None


def save_schedule(request: Request, event_id: str, body: SaveEvent,
                  updating: bool = False) -> dict[str, Any]:
    reference = store(request)

    @firestore.transactional
    def change(transaction: Any) -> dict[str, Any]:
        snapshot = reference.get(transaction=transaction)
        saved = snapshot.to_dict() or {"revision": 0, "events": {}}
        if saved["revision"] != body.revision:
            raise HTTPException(409, "El cronograma cambió. Recarga antes de guardar")
        events = dict(saved["events"])
        if updating and event_id not in events:
            raise HTTPException(404, "Evento no encontrado")
        if event_id not in events and len(events) >= MAX_EVENTS:
            raise HTTPException(409, "Límite de 100 eventos; elimina los antiguos para continuar")
        events[event_id] = body.event.model_dump(mode="json")
        result = {"revision": saved["revision"] + 1, "events": events}
        transaction.set(reference, result)
        return result

    try:
        return change(reference._client.transaction())
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "No se pudo guardar el evento; vuelve a intentarlo") from None


def remove_event(request: Request, event_id: str, revision: int) -> dict[str, Any]:
    reference = store(request)

    @firestore.transactional
    def change(transaction: Any) -> dict[str, Any]:
        saved = reference.get(transaction=transaction).to_dict() or {"revision": 0, "events": {}}
        if saved["revision"] != revision:
            raise HTTPException(409, "El cronograma cambió. Recarga antes de eliminar")
        events = dict(saved["events"])
        if event_id not in events:
            raise HTTPException(404, "Evento no encontrado")
        del events[event_id]
        result = {"revision": saved["revision"] + 1, "events": events}
        transaction.set(reference, result)
        return result

    try:
        return change(reference._client.transaction())
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "No se pudo eliminar el evento") from None


def records(saved: dict[str, Any], public: bool = False) -> list[dict[str, Any]]:
    result = []
    now = datetime.now(timezone.utc)
    for event_id, raw in saved["events"].items():
        event = Event.model_validate(raw)
        if public and (event.status not in {"scheduled", "live", "cancelled"}
                       or event.ends_at < now or not event.rights_confirmed):
            continue
        data = event.model_dump(mode="json")
        if public:
            data.pop("rights_confirmed")
        result.append({"id": event_id, **data})
    return sorted(result, key=lambda row: (row["starts_at"], row["id"]))


async def administrator(request: Request, response: Response,
                        user: dict[str, str] = Depends(current_session)) -> dict[str, str]:
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    settings = request.app.state.settings
    if (not settings.liveahora_admin_email.strip()
            or user.get("email", "").strip().casefold() != settings.liveahora_admin_email.strip().casefold()):
        raise HTTPException(403, "Esta cuenta no puede administrar LiveAhora")
    if settings.liveahora_admin_uid and user.get("uid") != settings.liveahora_admin_uid:
        raise HTTPException(403, "Usa la identidad autorizada para LiveAhora")
    if settings.environment.lower() != "development" and not request.scope.get("seismik.edge_authenticated"):
        raise HTTPException(403, "Acceso sólo desde el borde autenticado")
    if request.method not in {"GET", "HEAD"}:
        if (request.headers.get("origin") != ORIGIN
                or request.headers.get("x-liveahora-admin") != "1"
                or request.headers.get("sec-fetch-site") == "cross-site"):
            raise HTTPException(403, "Origen de administración no permitido")
        # A fixed-size calendar and a per-account write budget bound storage and abuse.
        from api.admin_security import digest, rate

        await rate(request.app.state.redis, digest(user["uid"]), "liveahora-writes", 30, 60)
    return user


@router.get("/login")
async def login(request: Request) -> Response:
    response = RedirectResponse("https://auth.seismik.org/id", status_code=303)
    response.headers["Cache-Control"] = "no-store"
    response.set_cookie(AFTER_LOGIN_COOKIE, "liveahora", max_age=600, secure=True,
                        httponly=True, samesite="none", path="/",
                        domain=request.app.state.settings.oauth_cookie_domain)
    return response


@router.post("/logout", status_code=204)
async def logout(request: Request) -> Response:
    # May be used by an authenticated account which lacks LiveAhora editing rights.
    if (request.headers.get("origin") != ORIGIN
            or request.headers.get("x-liveahora-admin") != "1"
            or request.headers.get("sec-fetch-site") == "cross-site"):
        raise HTTPException(403, "Origen de administración no permitido")
    token = request.cookies.get("seismik_session")
    if token:
        await request.app.state.redis.delete(f"seismik:oauth:session:{token}")
    response = Response(status_code=204, headers={"Cache-Control": "no-store"})
    response.delete_cookie("seismik_session", path="/",
                          domain=request.app.state.settings.oauth_cookie_domain,
                          secure=True, httponly=True, samesite="lax")
    return response


@router.get("/events")
async def public_events(request: Request, response: Response) -> dict[str, Any]:
    # Short revalidation; a draft or admin response is never cached.
    response.headers["Cache-Control"] = "public, max-age=0, s-maxage=30"
    saved = await asyncio.to_thread(read_schedule, request)
    return {"events": records(saved, public=True), "timezone": "America/Bogota"}


@router.get("/admin/events")
async def admin_events(request: Request, user: dict[str, str] = Depends(administrator)) -> dict[str, Any]:
    saved = await asyncio.to_thread(read_schedule, request)
    return {"revision": saved["revision"], "events": records(saved), "email": user["email"]}


@router.post("/admin/events")
async def create_event(request: Request, body: SaveEvent,
                       user: dict[str, str] = Depends(administrator)) -> dict[str, Any]:
    event_id = secrets.token_hex(12)
    saved = await asyncio.to_thread(save_schedule, request, event_id, body)
    return {"id": event_id, "revision": saved["revision"]}


@router.put("/admin/events/{event_id}")
async def update_event(request: Request, event_id: str, body: SaveEvent,
                       user: dict[str, str] = Depends(administrator)) -> dict[str, Any]:
    if not re.fullmatch(r"[a-f0-9]{24}", event_id):
        raise HTTPException(404, "Evento no encontrado")
    saved = await asyncio.to_thread(save_schedule, request, event_id, body, True)
    return {"id": event_id, "revision": saved["revision"]}


@router.delete("/admin/events/{event_id}")
async def delete_event(request: Request, event_id: str, revision: int = 0,
                       user: dict[str, str] = Depends(administrator)) -> dict[str, Any]:
    if not re.fullmatch(r"[a-f0-9]{24}", event_id) or revision < 0:
        raise HTTPException(404, "Evento no encontrado")
    saved = await asyncio.to_thread(remove_event, request, event_id, revision)
    return {"revision": saved["revision"]}
