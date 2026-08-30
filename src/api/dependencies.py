from __future__ import annotations

import hmac
import hashlib

from fastapi import Header, HTTPException, Request, status
from redis.asyncio import Redis

from api.bus import RedisEventBus
from api.config import AppSettings
from api.devices_store import DeviceRepository
from api.integrity import DeviceIntegrityVerifier


def get_app_settings(request: Request) -> AppSettings:
    return request.app.state.settings


def get_bus(request: Request) -> RedisEventBus:
    return request.app.state.bus


def get_devices(request: Request) -> DeviceRepository:
    return request.app.state.devices


def get_integrity_verifier(request: Request) -> DeviceIntegrityVerifier:
    return request.app.state.integrity_verifier


def get_redis(request: Request) -> Redis:
    return request.app.state.redis


def require_device_api_key(
    request: Request,
    x_device_api_key: str | None = Header(default=None, alias="X-Seismik-Device-Key"),
) -> None:
    expected = request.app.state.settings.device_api_key.get_secret_value()
    if not x_device_api_key or not hmac.compare_digest(x_device_api_key, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid device API key")


async def require_consumer_api_key(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-Seismik-API-Key"),
    x_device_api_key: str | None = Header(default=None, alias="X-Seismik-Device-Key"),
) -> None:
    """Protect data exports while retaining the mobile device-key path."""
    settings = request.app.state.settings
    expected = settings.consumer_api_key.get_secret_value()
    if not expected:
        return
    if (x_api_key and hmac.compare_digest(x_api_key, expected)) or (
        x_device_api_key
        and hmac.compare_digest(x_device_api_key, settings.device_api_key.get_secret_value())
    ):
        return
    if x_api_key and x_api_key.startswith("sk_live_"):
        digest = hashlib.sha256(x_api_key.encode()).hexdigest()
        if await request.app.state.redis.exists(f"seismik:developer-key:{digest}"):
            return
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or invalid Seismik API key")
