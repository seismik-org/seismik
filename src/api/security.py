from __future__ import annotations

import hashlib
import hmac
import time

from fastapi import HTTPException, status


def signed_message(timestamp: str, body: bytes) -> bytes:
    return timestamp.encode("ascii") + b"." + body


def create_signature(secret: str, timestamp: str, body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), signed_message(timestamp, body), hashlib.sha256).hexdigest()


def verify_signature(
    *,
    secret: str,
    timestamp: str | None,
    signature: str | None,
    body: bytes,
    max_skew_seconds: float,
    now: float | None = None,
) -> None:
    if not timestamp or not signature:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing signature headers")
    try:
        sent_at = float(timestamp)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid timestamp") from exc
    current = time.time() if now is None else now
    if abs(current - sent_at) > max_skew_seconds:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Expired webhook timestamp")
    supplied = signature.removeprefix("sha256=").lower()
    expected = create_signature(secret, timestamp, body)
    if len(supplied) != 64 or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")


def derive_crowd_token(master_secret: str, device_id: str) -> str:
    return hmac.new(master_secret.encode(), device_id.encode(), hashlib.sha256).hexdigest()
