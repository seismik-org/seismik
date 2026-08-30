from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException, Request, status
import firebase_admin
from firebase_admin import auth, credentials
from pydantic import BaseModel, Field

router = APIRouter(prefix="/v1/developer", tags=["developer"])


class KeyResponse(BaseModel):
    key: str
    plan: str = "free"
    warning: str = "Guárdala ahora: no volverá a mostrarse."


async def _identity(request: Request, authorization: str | None) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Google/Firebase login required")
    try:
        try:
            firebase_admin.get_app("seismik-developers")
        except ValueError:
            path = request.app.state.settings.firebase_credentials_path
            if not path:
                raise HTTPException(status_code=503, detail="Developer login is not configured")
            firebase_admin.initialize_app(credentials.Certificate(path), name="seismik-developers")
        return auth.verify_id_token(authorization.split(" ", 1)[1])
    except Exception as exc:  # provider-specific errors are intentionally not exposed
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid identity token") from exc


@router.post("/keys", response_model=KeyResponse, status_code=status.HTTP_201_CREATED)
async def create_key(
    request: Request,
    authorization: str | None = Header(default=None),
) -> KeyResponse:
    identity = await _identity(request, authorization)
    uid = str(identity["uid"])
    key = "sk_live_" + secrets.token_urlsafe(32)
    digest = hashlib.sha256(key.encode()).hexdigest()
    now = datetime.now(timezone.utc).isoformat()
    pipe = request.app.state.redis.pipeline(transaction=True)
    pipe.hset(f"seismik:developer-key:{digest}", mapping={"uid": uid, "created_at": now, "plan": "free"})
    pipe.sadd(f"seismik:developer-keys:{uid}", digest)
    await pipe.execute()
    return KeyResponse(key=key)


@router.delete("/keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_key(request: Request, key_id: str, authorization: str | None = Header(default=None)) -> None:
    identity = await _identity(request, authorization)
    uid = str(identity["uid"])
    if len(key_id) != 64 or any(c not in "0123456789abcdef" for c in key_id):
        raise HTTPException(status_code=404, detail="Key not found")
    record = await request.app.state.redis.hgetall(f"seismik:developer-key:{key_id}")
    if not record or record.get("uid") != uid:
        raise HTTPException(status_code=404, detail="Key not found")
    await request.app.state.redis.delete(f"seismik:developer-key:{key_id}")
    await request.app.state.redis.srem(f"seismik:developer-keys:{uid}", key_id)
