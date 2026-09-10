from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis

from api.config import AppSettings
from api.dependencies import (
    DevicePrincipal,
    get_app_settings,
    get_devices,
    get_integrity_verifier,
    get_redis,
    require_device_session,
)
from api.device_sessions import DeviceSessionRepository
from api.devices_store import DeviceRepository
from api.integrity import DeviceIntegrityVerifier
from api.schemas import (
    DeviceRegistration,
    DeviceRegistrationResponse,
    DeviceUnregister,
)
from api.security import derive_crowd_token

router = APIRouter(
    prefix="/v1/devices",
    tags=["devices"],
)


@router.post("/register", response_model=DeviceRegistrationResponse)
async def register_device(
    registration: DeviceRegistration,
    devices: DeviceRepository = Depends(get_devices),
    settings: AppSettings = Depends(get_app_settings),
    integrity: DeviceIntegrityVerifier = Depends(get_integrity_verifier),
    redis: Redis = Depends(get_redis),
) -> DeviceRegistrationResponse:
    verdict = await integrity.verify(registration)
    if settings.integrity_verification_enabled and not verdict.verified:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Device integrity verification failed",
        )
    if verdict.verified:
        binding_key = f"seismik:integrity:registration:{verdict.token_fingerprint}"
        ttl = max(60, (verdict.expires_at or int(time.time()) + 3600) - int(time.time()))
        created = await redis.set(binding_key, registration.device_id, ex=ttl, nx=True)
        if not created and await redis.get(binding_key) != registration.device_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Integrity token is already bound to another device",
            )
    await devices.register(registration, integrity_verified=verdict.verified)
    crowd_token = (
        derive_crowd_token(
            settings.crowd_master_secret.get_secret_value(), registration.device_id
        )
        if (verdict.verified or settings.environment == "development")
        else ""
    )
    return DeviceRegistrationResponse(
        device_id=registration.device_id,
        registered=True,
        crowd_token=crowd_token,
        device_session_token=await DeviceSessionRepository(
            redis, ttl_seconds=settings.device_session_ttl_seconds
        ).issue(registration.device_id),
    )


@router.post("/unregister")
async def unregister_device(
    unregister: DeviceUnregister,
    devices: DeviceRepository = Depends(get_devices),
    settings: AppSettings = Depends(get_app_settings),
    redis: Redis = Depends(get_redis),
    principal: DevicePrincipal = Depends(require_device_session),
) -> dict[str, bool]:
    if principal.device_id != unregister.device_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Device session mismatch")
    removed = await devices.unregister(unregister.device_id)
    await DeviceSessionRepository(redis, ttl_seconds=settings.device_session_ttl_seconds).revoke(
        unregister.device_id
    )
    return {"unregistered": removed}
