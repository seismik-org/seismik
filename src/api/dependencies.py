from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Awaitable, Callable, cast

from fastapi import Depends, Header, HTTPException, Request, status
from redis.asyncio import Redis

from api.billing import record_usage
from api.bus import RedisEventBus
from api.config import AppSettings
from api.device_sessions import DeviceSessionRepository
from api.devices_store import DeviceRepository
from api.integrity import DeviceIntegrityVerifier


@dataclass(frozen=True)
class ApiPrincipal:
    subject: str
    plan: str
    scopes: frozenset[str]
    key_id: str | None = None


@dataclass(frozen=True)
class DevicePrincipal:
    device_id: str


UNLIMITED_PRINCIPAL = ApiPrincipal(
    subject="seismik-internal",
    plan="internal",
    scopes=frozenset({"*"}),
)
MOBILE_PRINCIPAL = ApiPrincipal(
    subject="verified-mobile-installation", plan="mobile", scopes=frozenset({"*"})
)


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


async def require_device_session(
    request: Request,
    x_device_session: str | None = Header(default=None, alias="X-Seismik-Device-Session"),
) -> DevicePrincipal:
    if not x_device_session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing device session")
    settings = request.app.state.settings
    sessions = DeviceSessionRepository(
        request.app.state.redis, ttl_seconds=settings.device_session_ttl_seconds
    )
    device_id = await sessions.resolve(x_device_session)
    if not device_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid device session")
    return DevicePrincipal(device_id=device_id)


async def require_consumer_api_key(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-Seismik-API-Key"),
) -> ApiPrincipal:
    """Protect human-facing data exports with a Seismik API key."""
    settings = request.app.state.settings
    expected = settings.consumer_api_key.get_secret_value()
    if expected and x_api_key and hmac.compare_digest(x_api_key, expected):
        return UNLIMITED_PRINCIPAL
    if x_api_key and x_api_key.startswith("sk_live_"):
        return await _authorize_developer_key(request, x_api_key)
    if x_api_key and x_api_key.startswith("sk_test_"):
        return await _authorize_developer_key(request, x_api_key)
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or invalid Seismik API key")


async def _authorize_developer_key(
    request: Request,
    api_key: str,
    required_scope: str | None = None,
    settings: AppSettings | None = None,
    redis: Redis | None = None,
) -> ApiPrincipal:
    digest = hashlib.sha256(api_key.encode()).hexdigest()
    resolved_redis = redis or request.app.state.redis
    record = cast(
        dict[str, str],
        await resolved_redis.hgetall(f"seismik:developer-key:{digest}"),
    )
    if not record or record.get("status", "active") != "active":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Seismik API key")

    scopes = frozenset(filter(None, record.get("scopes", "events:read,stations:read").split(",")))
    if required_scope and required_scope not in scopes and "*" not in scopes:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="API key scope is insufficient")

    resolved_settings = settings or request.app.state.settings
    now = datetime.now(timezone.utc)
    minute_key = f"seismik:developer-usage:minute:{digest}:{now:%Y%m%d%H%M}"
    day_key = f"seismik:developer-usage:day:{digest}:{now:%Y%m%d}"
    pipe = resolved_redis.pipeline(transaction=True)
    pipe.incr(minute_key)
    pipe.expire(minute_key, 120)
    pipe.incr(day_key)
    pipe.expire(day_key, 172_800)
    pipe.hset(f"seismik:developer-key:{digest}", mapping={"last_used_at": now.isoformat()})
    results = await pipe.execute()
    minute_count = int(results[0])
    day_count = int(results[2])
    if minute_count > resolved_settings.developer_free_requests_per_minute:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Per-minute API quota exceeded",
            headers={"Retry-After": "60"},
        )
    if day_count > resolved_settings.developer_free_requests_per_day:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Daily API quota exceeded",
            headers={"Retry-After": "86400"},
        )
    await record_usage(resolved_redis, record["uid"], required_scope or "unscoped", record.get("key_id"))
    return ApiPrincipal(
        subject=record["uid"],
        key_id=record.get("key_id"),
        plan=record.get("plan", "free"),
        scopes=scopes,
    )


def require_api_scope(scope: str) -> Callable[..., Awaitable[ApiPrincipal]]:
    async def dependency(
        request: Request,
        x_api_key: str | None = Header(default=None, alias="X-Seismik-API-Key"),
        settings: AppSettings = Depends(get_app_settings),
        redis: Redis = Depends(get_redis),
    ) -> ApiPrincipal:
        expected = settings.consumer_api_key.get_secret_value()
        if expected and x_api_key and hmac.compare_digest(x_api_key, expected):
            return UNLIMITED_PRINCIPAL
        if x_api_key and x_api_key.startswith(("sk_live_", "sk_test_")):
            return await _authorize_developer_key(request, x_api_key, scope, settings, redis)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Seismik API key",
        )

    return dependency


def require_mobile_or_api_scope(scope: str) -> Callable[..., Awaitable[ApiPrincipal]]:
    """Autoriza exportaciones para una instalación verificada o una API key.

    La app no lleva una API key de empresa en el binario; los consumidores
    externos siguen sujetos a scopes y cuotas mediante ``X-Seismik-API-Key``.
    """

    api_dependency = require_api_scope(scope)

    async def dependency(
        request: Request,
        x_device_session: str | None = Header(default=None, alias="X-Seismik-Device-Session"),
        x_api_key: str | None = Header(default=None, alias="X-Seismik-API-Key"),
        settings: AppSettings = Depends(get_app_settings),
        redis: Redis = Depends(get_redis),
    ) -> ApiPrincipal:
        if x_device_session:
            device_id = await DeviceSessionRepository(
                redis, ttl_seconds=settings.device_session_ttl_seconds
            ).resolve(x_device_session)
            if device_id:
                return MOBILE_PRINCIPAL
        return await api_dependency(
            request=request, x_api_key=x_api_key, settings=settings, redis=redis
        )

    return dependency


require_events_read = require_api_scope("events:read")
require_stations_read = require_api_scope("stations:read")
require_mobile_events_read = require_mobile_or_api_scope("events:read")
require_mobile_stations_read = require_mobile_or_api_scope("stations:read")
