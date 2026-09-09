from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
from datetime import datetime, timezone
from typing import Any, Literal, cast

import firebase_admin
from fastapi import APIRouter, Cookie, Header, HTTPException, Request, status
from firebase_admin import App, auth, credentials
from pydantic import BaseModel, Field, field_validator

router = APIRouter(prefix="/v1/developer", tags=["developer-platform"])

# La gestión de webhooks exige iniciar sesión en el portal; no se concede con
# una API key filtrada. Los scopes siguen siendo sólo de lectura de datos.
ALLOWED_SCOPES = frozenset({"events:read", "stations:read"})


class FirebaseWebConfig(BaseModel):
    api_key: str
    auth_domain: str
    project_id: str
    app_id: str


class PortalConfigResponse(BaseModel):
    firebase_enabled: bool
    firebase: FirebaseWebConfig | None
    terms_version: str
    plans: list[dict[str, Any]]
    products: list[dict[str, Any]]


class KeyCreateRequest(BaseModel):
    name: str = Field(min_length=3, max_length=60)
    scopes: set[str] = Field(default_factory=lambda: set(ALLOWED_SCOPES))
    accepted_terms_version: str

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if len(cleaned) < 3:
            raise ValueError("Key name must contain at least three visible characters")
        return cleaned

    @field_validator("scopes")
    @classmethod
    def validate_scopes(cls, value: set[str]) -> set[str]:
        if not value or not value.issubset(ALLOWED_SCOPES):
            raise ValueError("Unsupported or empty API scope set")
        return value


class KeySummary(BaseModel):
    key_id: str
    name: str
    prefix: str
    plan: Literal["free"] = "free"
    scopes: list[str]
    status: Literal["active", "revoked"]
    created_at: str
    last_used_at: str | None = None
    revoked_at: str | None = None
    requests_today: int = 0


class KeySecretResponse(KeySummary):
    key: str
    warning: str = "Guárdala ahora: no volverá a mostrarse."


class KeyListResponse(BaseModel):
    keys: list[KeySummary]
    active_count: int
    active_limit: int


def _firebase_app(request: Request) -> App:
    try:
        return firebase_admin.get_app("seismik-developers")
    except ValueError:
        path = request.app.state.settings.firebase_credentials_path
        if not path:
            raise HTTPException(status_code=503, detail="Developer login is not configured")
        return firebase_admin.initialize_app(
            credentials.Certificate(path),
            name="seismik-developers",
        )


async def _identity(
    request: Request,
    authorization: str | None,
    seismik_session: str | None = None,
) -> dict[str, Any]:
    if seismik_session:
        raw = await request.app.state.redis.get(f"seismik:oauth:session:{seismik_session}")
        if raw:
            session = json.loads(raw)
            session["uid"] = session.get("uid") or session.get("email", "")
            return session
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google/Firebase login required",
        )
    token = authorization.split(" ", 1)[1]
    try:
        identity = await asyncio.to_thread(
            auth.verify_id_token,
            token,
            app=_firebase_app(request),
        )
    except HTTPException:
        raise
    except Exception as exc:  # provider-specific errors are intentionally hidden
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid identity token",
        ) from exc
    if not identity.get("email_verified", False):
        raise HTTPException(status_code=403, detail="A verified email address is required")
    return identity


async def _request_identity(
    request: Request,
    authorization: str | None,
    seismik_session: str | None,
) -> dict[str, Any]:
    if seismik_session:
        return await _identity(request, authorization, seismik_session)
    return await _identity(request, authorization)


async def get_developer_identity(
    request: Request,
    authorization: str | None = None,
    seismik_session: str | None = None,
) -> dict[str, Any]:
    """Dependencia pública para recursos que sólo administra su propietario.

    Una clave de consumo nunca puede crear ni redirigir webhooks de otra
    organización: la operación requiere una sesión OAuth del portal.
    """

    return await _request_identity(request, authorization, seismik_session)


def _record_to_summary(record: dict[str, str], requests_today: int = 0) -> KeySummary:
    return KeySummary(
        key_id=record["key_id"],
        name=record["name"],
        prefix=record["prefix"],
        scopes=sorted(filter(None, record.get("scopes", "").split(","))),
        status=cast(Literal["active", "revoked"], record.get("status", "active")),
        created_at=record["created_at"],
        last_used_at=record.get("last_used_at") or None,
        revoked_at=record.get("revoked_at") or None,
        requests_today=requests_today,
    )


async def _audit(request: Request, action: str, uid: str, **fields: str) -> None:
    payload = {
        "action": action,
        "uid": uid,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **fields,
    }
    await request.app.state.redis.xadd(
        request.app.state.settings.developer_audit_stream,
        {"payload": json.dumps(payload, separators=(",", ":"))},
        maxlen=10_000,
        approximate=True,
    )


async def _records_for_uid(request: Request, uid: str) -> list[tuple[str, dict[str, str]]]:
    redis = request.app.state.redis
    key_ids = sorted(await redis.smembers(f"seismik:developer-keys:{uid}"))
    records: list[tuple[str, dict[str, str]]] = []
    for key_id in key_ids:
        digest = await redis.get(f"seismik:developer-key-id:{key_id}")
        if digest:
            record = await redis.hgetall(f"seismik:developer-key:{digest}")
            if record:
                records.append((digest, record))
            continue
        # Compatibility with the first beta, where the set contained the digest.
        legacy = await redis.hgetall(f"seismik:developer-key:{key_id}")
        if legacy:
            legacy.setdefault("key_id", key_id)
            legacy.setdefault("name", "Clave beta")
            legacy.setdefault("prefix", "sk_live_…")
            legacy.setdefault("scopes", "events:read,stations:read")
            legacy.setdefault("status", "active")
            records.append((key_id, legacy))
    return records


async def _enforce_creation_rate(request: Request, uid: str) -> None:
    """Acota cuántas claves puede emitir una cuenta por hora.

    El máximo de claves activas no basta: revocar libera un hueco, así que un
    bucle de crear y revocar produce claves sin fin, infla la bitácora de
    auditoría y deja rastros de secretos por todas partes. Se cuentan los
    intentos, no los aciertos, porque el bucle es el abuso.

    La ventana es un contador por hora en Redis, no un algoritmo deslizante: en
    el peor caso alguien aprovecha el cambio de hora para el doble del límite,
    y para lo que se busca aquí eso es irrelevante.
    """

    settings = request.app.state.settings
    limit = settings.developer_key_creations_per_hour
    window = datetime.now(timezone.utc).strftime("%Y%m%d%H")
    counter = f"seismik:developer-key-creations:{uid}:{window}"

    pipe = request.app.state.redis.pipeline(transaction=True)
    pipe.incr(counter)
    pipe.expire(counter, 7_200)
    attempts, _ = await pipe.execute()
    if int(attempts) > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many API keys created recently; try again later",
            headers={"Retry-After": "3600"},
        )


async def _create_key_record(
    request: Request,
    uid: str,
    payload: KeyCreateRequest,
) -> KeySecretResponse:
    settings = request.app.state.settings
    if payload.accepted_terms_version != settings.developer_terms_version:
        raise HTTPException(status_code=409, detail="The current API terms must be accepted")

    await _enforce_creation_rate(request, uid)

    records = await _records_for_uid(request, uid)
    active_count = sum(record.get("status", "active") == "active" for _, record in records)
    if active_count >= settings.developer_max_active_keys:
        raise HTTPException(status_code=409, detail="Active API key limit reached")

    prefix = "sk_live_" if settings.environment.lower() == "production" else "sk_test_"
    key = prefix + secrets.token_urlsafe(32)
    digest = hashlib.sha256(key.encode()).hexdigest()
    key_id = "key_" + secrets.token_hex(8)
    now = datetime.now(timezone.utc).isoformat()
    record = {
        "uid": uid,
        "key_id": key_id,
        "name": payload.name,
        "prefix": key[:16] + "…",
        "created_at": now,
        "last_used_at": "",
        "revoked_at": "",
        "plan": "free",
        "status": "active",
        "scopes": ",".join(sorted(payload.scopes)),
        "terms_version": settings.developer_terms_version,
    }
    pipe = request.app.state.redis.pipeline(transaction=True)
    pipe.hset(f"seismik:developer-key:{digest}", mapping=record)
    pipe.set(f"seismik:developer-key-id:{key_id}", digest)
    pipe.sadd(f"seismik:developer-keys:{uid}", key_id)
    pipe.hset(
        f"seismik:developer-profile:{uid}",
        mapping={"terms_version": settings.developer_terms_version, "terms_accepted_at": now},
    )
    await pipe.execute()
    await _audit(request, "key.created", uid, key_id=key_id, name=payload.name)
    return KeySecretResponse(**_record_to_summary(record).model_dump(), key=key)


@router.get("/config", response_model=PortalConfigResponse)
async def portal_config(request: Request) -> PortalConfigResponse:
    settings = request.app.state.settings
    values = (
        settings.firebase_web_api_key,
        settings.firebase_web_auth_domain,
        settings.firebase_web_project_id,
        settings.firebase_web_app_id,
    )
    firebase = None
    if all(values):
        firebase = FirebaseWebConfig(
            api_key=values[0],
            auth_domain=values[1],
            project_id=values[2],
            app_id=values[3],
        )
    return PortalConfigResponse(
        firebase_enabled=firebase is not None,
        firebase=firebase,
        terms_version=settings.developer_terms_version,
        plans=[
            {
                "id": "free",
                "name": "Free",
                "requests_per_minute": settings.developer_free_requests_per_minute,
                "requests_per_day": settings.developer_free_requests_per_day,
                "max_active_keys": settings.developer_max_active_keys,
            }
        ],
        products=[
            {
                "id": "events",
                "name": "Eventos sísmicos",
                "scope": "events:read",
                "endpoints": ["/v1/events/history", "/v1/events/recent"],
            },
            {
                "id": "stations",
                "name": "Red de estaciones",
                "scope": "stations:read",
                "endpoints": ["/v1/network/stations"],
            },
        ],
    )


@router.get("/keys", response_model=KeyListResponse)
async def list_keys(
    request: Request,
    authorization: str | None = Header(default=None),
    seismik_session: str | None = Cookie(default=None),
) -> KeyListResponse:
    identity = await _request_identity(request, authorization, seismik_session)
    uid = str(identity["uid"])
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    summaries: list[KeySummary] = []
    for digest, record in await _records_for_uid(request, uid):
        # Keep revoked credentials for authorization/audit evidence, but do not
        # expose them in the person's current portal inventory.
        if record.get("status", "active") != "active":
            continue
        usage = int(
            await request.app.state.redis.get(
                f"seismik:developer-usage:day:{digest}:{today}"
            )
            or 0
        )
        summaries.append(_record_to_summary(record, usage))
    summaries.sort(key=lambda item: item.created_at, reverse=True)
    return KeyListResponse(
        keys=summaries,
        active_count=len(summaries),
        active_limit=request.app.state.settings.developer_max_active_keys,
    )


@router.post("/keys", response_model=KeySecretResponse, status_code=status.HTTP_201_CREATED)
async def create_key(
    payload: KeyCreateRequest,
    request: Request,
    authorization: str | None = Header(default=None),
    seismik_session: str | None = Cookie(default=None),
) -> KeySecretResponse:
    identity = await _request_identity(request, authorization, seismik_session)
    return await _create_key_record(request, str(identity["uid"]), payload)


@router.post("/keys/{key_id}/rotate", response_model=KeySecretResponse)
async def rotate_key(
    key_id: str,
    payload: KeyCreateRequest,
    request: Request,
    authorization: str | None = Header(default=None),
    seismik_session: str | None = Cookie(default=None),
) -> KeySecretResponse:
    identity = await _request_identity(request, authorization, seismik_session)
    uid = str(identity["uid"])
    digest = await request.app.state.redis.get(f"seismik:developer-key-id:{key_id}")
    record = (
        await request.app.state.redis.hgetall(f"seismik:developer-key:{digest}")
        if digest
        else {}
    )
    if not record or record.get("uid") != uid or record.get("status") != "active":
        raise HTTPException(status_code=404, detail="Key not found")
    now = datetime.now(timezone.utc).isoformat()
    await request.app.state.redis.hset(
        f"seismik:developer-key:{digest}",
        mapping={"status": "revoked", "revoked_at": now},
    )
    replacement = await _create_key_record(request, uid, payload)
    await _audit(request, "key.rotated", uid, key_id=key_id, replacement=replacement.key_id)
    return replacement


@router.delete("/keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_key(
    request: Request,
    key_id: str,
    authorization: str | None = Header(default=None),
    seismik_session: str | None = Cookie(default=None),
) -> None:
    identity = await _request_identity(request, authorization, seismik_session)
    uid = str(identity["uid"])
    digest = await request.app.state.redis.get(f"seismik:developer-key-id:{key_id}")
    record = (
        await request.app.state.redis.hgetall(f"seismik:developer-key:{digest}")
        if digest
        else {}
    )
    if not record or record.get("uid") != uid:
        raise HTTPException(status_code=404, detail="Key not found")
    if record.get("status") == "active":
        now = datetime.now(timezone.utc).isoformat()
        await request.app.state.redis.hset(
            f"seismik:developer-key:{digest}",
            mapping={"status": "revoked", "revoked_at": now},
        )
        await _audit(request, "key.revoked", uid, key_id=key_id)
