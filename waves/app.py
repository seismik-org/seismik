"""Isolated, read-only historical Waves pilot. Never feeds the alert pipeline.

Acceso: la persona entra por auth.seismik.org (el mismo acceso único de Seismik que usa admin.seismik.org) y
vuelve a Waves con la cookie de sesión `seismik_session`. Aquí no hay formulario de acceso ni SDK de Firebase: el
servidor pregunta a la API de Seismik quién es esa sesión y sólo después decide si el correo está en el piloto.
El navegador nunca decide la autorización.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import logging
import os
import re
import time
from collections import defaultdict, deque
from functools import lru_cache
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from starlette.staticfiles import StaticFiles

ROOT = Path(__file__).parent
app = FastAPI(title="Seismik Waves · Piloto", docs_url=None, redoc_url=None)

# Debe ser idéntica a la de edge/worker.js (una prueba lo exige). Ya no hay acceso con Google ni Firebase en esta página.
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; "
    "frame-src 'none'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
)
SESSION_COOKIE = "seismik_session"
SESSION_URL = os.getenv("WAVES_SESSION_URL", "https://api.seismik.org/v1/oauth/session")
LOGOUT_URL = os.getenv("WAVES_LOGOUT_URL", "https://api.seismik.org/v1/oauth/logout")
WAVES_ORIGIN = os.getenv("WAVES_ORIGIN", "https://waves.seismik.org")
TOKEN_SHAPE = re.compile(r"[A-Za-z0-9_-]{20,200}")
CACHE_SECONDS = 10.0
_sessions: dict[str, tuple[float, dict]] = {}

# Descargas: el MiniSEED original completo, tal como está en el archivo privado. Sólo para personas aprobadas, con la
# huella SHA-256 comprobada contra el catálogo antes de entregar un solo byte. Apagadas hasta WAVES_DOWNLOADS=on.
ARCHIVE_BUCKET = os.getenv("WAVES_ARCHIVE_BUCKET", "seismik-15bbb-scientific-archive")
ARCHIVE_PREFIX = os.getenv("WAVES_ARCHIVE_PREFIX", "imports/local-2026-10-10/data/")
MAX_DOWNLOAD_BYTES = 8_000_000
DOWNLOADS_PER_MINUTE = 20
_downloads: dict[str, deque] = defaultdict(deque)
log = logging.getLogger("uvicorn.error")


def downloads_enabled() -> bool:
    return os.getenv("WAVES_DOWNLOADS", "").lower() == "on"

# Agregados públicos del archivo: nada que identifique una grabación.
GROUPS = (
    ("evaluation", "calibration/ml-evaluation-", "Evaluación de magnitud",
     "Grabaciones de eventos usadas para comparar el cálculo de magnitud de Seismik con la referencia."),
    ("historical", "calibration/historical-magnitude-", "Sismos históricos de referencia",
     "Eventos pasados con magnitud publicada por catálogos de referencia, para contrastar resultados."),
    ("cases", "calibration/", "Casos de estudio",
     "Sismos concretos recuperados para estudiar fases, latencia y reproducción del detector."),
    ("fixtures", "replay/", "Pruebas de reproducción",
     "Registros fijos para repetir una misma prueba y comparar versiones del software."),
)


@lru_cache
def index() -> dict:
    return json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))


@lru_cache
def view() -> dict:
    """Contexto legible de cada grabación (de qué sismo es), generado con build-previews.py."""
    return json.loads((ROOT / "catalog-view.json").read_text(encoding="utf-8"))


RECORD_ID = re.compile(r"[0-9a-f]{24}")


def group_of(name: str) -> str:
    return next(group for group, prefix, *_ in GROUPS if name.startswith(prefix))


async def account_session(token: str) -> dict:
    """Pregunta a la API de Seismik quién es esta sesión. Sólo positivos, 10 s, para no cargar la API."""
    key = hashlib.sha256(token.encode()).hexdigest()
    now = time.monotonic()
    cached = _sessions.get(key)
    if cached and cached[0] > now:
        return cached[1]
    try:
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=False) as client:
            response = await client.get(SESSION_URL, headers={
                "Cookie": f"{SESSION_COOKIE}={token}", "Accept": "application/json", "User-Agent": "seismik-waves/1"})
    except httpx.HTTPError:
        raise HTTPException(503, "No se pudo comprobar tu sesión. Inténtalo de nuevo en unos minutos.") from None
    if response.status_code in (401, 403):
        raise HTTPException(401, "Inicia sesión con tu cuenta Seismik para consultar tu acceso al piloto.")
    if response.status_code != 200:
        raise HTTPException(503, "No se pudo comprobar tu sesión. Inténtalo de nuevo en unos minutos.")
    try:
        data = response.json()
        email = str(data["email"]).strip().lower()
        claims = {"email": email, "uid": str(data["uid"]), "name": str(data.get("name") or "")}
    except (ValueError, KeyError, TypeError):
        raise HTTPException(503, "No se pudo comprobar tu sesión. Inténtalo de nuevo en unos minutos.") from None
    if "@" not in email:
        raise HTTPException(401, "Tu sesión no tiene un correo válido.")
    if len(_sessions) > 256:
        _sessions.clear()
    _sessions[key] = (now + CACHE_SECONDS, claims)
    return claims


async def identity(request: Request) -> dict:
    token = request.cookies.get(SESSION_COOKIE, "")
    if not token or not TOKEN_SHAPE.fullmatch(token):
        raise HTTPException(401, "Inicia sesión con tu cuenta Seismik para consultar tu acceso al piloto.")
    return await account_session(token)


@lru_cache
def archive_client():
    from google.cloud import storage

    return storage.Client()


def archive_bytes(name: str) -> bytes:
    """El objeto original del archivo privado. Un archivo de grabación pesa pocos MB; si pesa más, algo no es lo esperado."""
    blob = archive_client().bucket(ARCHIVE_BUCKET).get_blob(ARCHIVE_PREFIX + name, timeout=15)
    if blob is None or blob.size is None or blob.size > MAX_DOWNLOAD_BYTES:
        raise FileNotFoundError(name)
    return blob.download_as_bytes(timeout=30)


def is_approved(claims: dict) -> bool:
    allowed = {s.strip().lower() for s in os.getenv("WAVES_PILOT_EMAILS", "").split(";") if s.strip()}
    return claims["email"].lower() in allowed


def approved(claims: dict = Depends(identity)) -> dict:
    if not is_approved(claims):
        raise HTTPException(403, "Tu cuenta aún no está autorizada para Waves. Solicita acceso al piloto.")
    return claims


@app.middleware("http")
async def security(request: Request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = CSP
    return response


@app.get("/health/ready")
def ready():
    return {"status": "ready", "service": "waves", "mode": "historical_pilot"}


@app.get("/v1/waves/summary")
def summary():
    data = index()
    groups = []
    for group, _prefix, label, description in GROUPS:
        members = [r for r in data["records"] if group_of(r["name"]) == group]
        groups.append({"id": group, "label": label, "description": description,
                       "recordings": len(members), "bytes": sum(r["bytes"] for r in members)})
    return {"mode": "historical_pilot", "live": False, "downloads_enabled": downloads_enabled(),
            "files": data["files"], "bytes": data["bytes"], "waveforms": len(data["records"]),
            "recording_bytes": sum(g["bytes"] for g in groups), "groups": groups,
            "formats": ["MiniSEED"], "snapshot_date": "2026-10-10", "scientific_validation": "not_validated"}


@app.get("/v1/waves/session")
def session(claims: dict = Depends(identity)):
    return {"approved": is_approved(claims), "email": claims["email"],
            "downloads_enabled": downloads_enabled(), "mode": "historical_pilot"}


@app.post("/v1/waves/logout", status_code=204)
async def logout(request: Request, origin: str | None = Header(default=None)):
    """Cierra la sesión única de Seismik (la misma de los demás portales) y borra su copia en la API."""
    if origin != WAVES_ORIGIN:
        raise HTTPException(403, "Origen no permitido.")
    token = request.cookies.get(SESSION_COOKIE, "")
    if token and TOKEN_SHAPE.fullmatch(token):
        _sessions.pop(hashlib.sha256(token.encode()).hexdigest(), None)
        try:
            async with httpx.AsyncClient(timeout=5.0, follow_redirects=False) as client:
                await client.post(LOGOUT_URL, headers={"Cookie": f"{SESSION_COOKIE}={token}", "User-Agent": "seismik-waves/1"})
        except httpx.HTTPError:
            raise HTTPException(503, "No se pudo cerrar la sesión. Inténtalo de nuevo.") from None
    return Response(status_code=204)


def date_of(item: dict) -> str:
    return item["view"].get("origin_time") or item["view"].get("start") or ""


def describe(record: dict) -> dict:
    return {**record, "group": group_of(record["name"]), "view": view().get(record["id"], {})}


@app.get("/v1/waves/catalog")
def catalog(q: str = Query(default="", max_length=120),
            category: str = Query(default="", max_length=40),
            group: str = Query(default="", pattern="^(evaluation|historical|cases|fixtures)?$"),
            kind: str = Query(default="", pattern="^(evento|ruido|caso)?$"),
            minimum_magnitude: float = Query(default=0, ge=0, le=10),
            sort: str = Query(default="date", pattern="^(date|magnitude|name)$"),
            offset: int = Query(default=0, ge=0, le=10000),
            limit: int = Query(default=25, ge=1, le=100),
            claims: dict = Depends(approved)):
    needle = q.lower()
    items = []
    for record in index()["records"]:
        item = describe(record)
        text = f"{record['name']} {item['view'].get('title') or ''} {item['view'].get('place') or ''}".lower()
        magnitude = item["view"].get("magnitude")
        if needle not in text or (category and record["category"] != category) or (group and item["group"] != group):
            continue
        if kind and item["view"].get("kind") != kind:
            continue
        if minimum_magnitude and not (isinstance(magnitude, (int, float)) and magnitude >= minimum_magnitude):
            continue
        items.append(item)
    if sort == "name":
        items.sort(key=lambda item: item["name"])
    elif sort == "magnitude":
        items.sort(key=lambda item: (item["view"].get("magnitude") is None, -(item["view"].get("magnitude") or 0), item["name"]))
    else:  # más recientes primero; lo que no tiene fecha (ruido, casos) va al final por nombre
        dated = sorted((item for item in items if date_of(item)), key=date_of, reverse=True)
        undated = sorted((item for item in items if not date_of(item)), key=lambda item: item["name"])
        items = dated + undated
    return {"items": items[offset:offset + limit], "total": len(items),
            "offset": offset, "limit": limit, "mode": "historical_pilot"}


@app.get("/v1/waves/records/{record_id}")
def record(record_id: str, claims: dict = Depends(approved)):
    match = next((r for r in index()["records"] if r["id"] == record_id), None)
    if match is None:
        raise HTTPException(404, "Grabación no encontrada.")
    return describe(match)


@app.get("/v1/waves/records/{record_id}/preview")
def preview(record_id: str, claims: dict = Depends(approved)):
    """Forma de onda reducida (envolvente mín/máx) para dibujar. No es la grabación y no permite reconstruirla."""
    match = next((r for r in index()["records"] if r["id"] == record_id), None)
    path = ROOT / "previews" / f"{record_id}.json.gz"
    if match is None or not RECORD_ID.fullmatch(record_id) or not path.is_file():
        raise HTTPException(404, "Grabación no encontrada.")
    payload = json.loads(gzip.decompress(path.read_bytes()))
    return {**payload, "record": describe(match), "downloads_enabled": downloads_enabled()}


@app.get("/v1/waves/records/{record_id}/download")
def download(record_id: str, claims: dict = Depends(approved)):
    """MiniSEED original y completo (todas las estaciones y canales), con la integridad comprobada en el servidor."""
    if not downloads_enabled():
        raise HTTPException(404, "Las descargas no están habilitadas.")
    match = next((r for r in index()["records"] if r["id"] == record_id), None)
    if match is None:
        raise HTTPException(404, "Grabación no encontrada.")
    who = hashlib.sha256(claims["email"].encode()).hexdigest()[:12]
    now = time.monotonic()
    recent = _downloads[who]
    while recent and now - recent[0] > 60:
        recent.popleft()
    if len(recent) >= DOWNLOADS_PER_MINUTE:
        raise HTTPException(429, "Demasiadas descargas seguidas. Espera un minuto.", headers={"Retry-After": "60"})
    try:
        data = archive_bytes(match["name"])
    except Exception:  # noqa: BLE001 - cualquier fallo del almacenamiento se reporta igual, sin detalles internos
        raise HTTPException(503, "El archivo no está disponible en este momento. Inténtalo de nuevo.") from None
    if len(data) != match["bytes"] or hashlib.sha256(data).hexdigest() != match["sha256"]:
        log.error("waves download integrity mismatch id=%s", record_id)
        raise HTTPException(502, "La integridad del archivo no coincide con el catálogo; no se entrega.")
    recent.append(now)
    log.info("waves download id=%s who=%s bytes=%d", record_id, who, len(data))
    filename = re.sub(r"[^A-Za-z0-9._-]", "_", Path(match["name"]).name)
    return Response(content=data, media_type="application/vnd.fdsn.mseed", headers={
        "Content-Disposition": f'attachment; filename="{filename}"', "X-Waves-SHA256": match["sha256"], "Content-Length": str(len(data))})


@app.get("/")
def home():
    return FileResponse(ROOT / "static/index.html")


@app.exception_handler(404)
async def not_found(request: Request, exc):
    if request.url.path.startswith("/v1/"):
        return JSONResponse({"detail": "Ruta no encontrada."}, status_code=404)
    return FileResponse(ROOT / "static/404.html", status_code=404)


app.mount("/assets", StaticFiles(directory=ROOT / "static"), name="assets")
