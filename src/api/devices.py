from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis

from api.config import AppSettings
from api.dependencies import (
    get_app_settings,
    get_devices,
    get_integrity_verifier,
    get_redis,
    require_device_api_key,
)
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
    dependencies=[Depends(require_device_api_key)],
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
    if verdict.verified:
        binding_key = f"seismik:integrity:registration:{verdict.token_fingerprint}"
        ttl = max(60, (verdict.expires_at or int(time.time()) + 3600) - int(time.time()))
        created = await redis.set(binding_key, registration.device_id, ex=ttl, nx=True)
        if not created and await redis.get(binding_key) != registration.device_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Integrity token is already bound to another device",
            )
    await devices.register(registration)
    crowd_token = derive_crowd_token(
        settings.crowd_master_secret.get_secret_value(), registration.device_id
    )
    return DeviceRegistrationResponse(
        device_id=registration.device_id,
        registered=True,
        crowd_token=crowd_token,
    )


@router.post("/unregister")
async def unregister_device(
    unregister: DeviceUnregister,
    devices: DeviceRepository = Depends(get_devices),
) -> dict[str, bool]:
    removed = await devices.unregister(unregister.device_id)
    return {"unregistered": removed}
