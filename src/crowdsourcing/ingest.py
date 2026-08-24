from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import ValidationError

from api.config import AppSettings
from api.dependencies import get_app_settings, get_devices
from api.devices_store import DeviceRepository
from api.schemas import ShakeAccepted, ShakePing
from api.security import derive_crowd_token, verify_signature
from crowdsourcing.cluster import CrowdClusterEngine

router = APIRouter(prefix="/v1/crowd", tags=["crowdsourcing"])


@router.post(
    "/shake",
    response_model=ShakeAccepted,
    status_code=status.HTTP_202_ACCEPTED,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": ShakePing.model_json_schema()}},
        }
    },
)
async def ingest_shake(
    request: Request,
    x_device_timestamp: str | None = Header(default=None, alias="X-Seismik-Timestamp"),
    x_device_signature: str | None = Header(default=None, alias="X-Seismik-Signature"),
    settings: AppSettings = Depends(get_app_settings),
    devices: DeviceRepository = Depends(get_devices),
) -> ShakeAccepted:
    body = await request.body()
    try:
        ping = ShakePing.model_validate_json(body)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    if not await devices.exists(ping.device_id):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown device")
    crowd_token = derive_crowd_token(
        settings.crowd_master_secret.get_secret_value(), ping.device_id
    )
    verify_signature(
        secret=crowd_token,
        timestamp=x_device_timestamp,
        signature=x_device_signature,
        body=body,
        max_skew_seconds=settings.crowd_max_clock_skew_seconds,
    )
    now = time.time()
    if abs(now - ping.timestamp_seconds) > settings.crowd_max_clock_skew_seconds:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Stale acceleration ping")

    rate_key = f"seismik:crowd:rate:{ping.device_id}:{int(now)}"
    pipe = request.app.state.redis.pipeline(transaction=True)
    pipe.incr(rate_key)
    pipe.expire(rate_key, 2)
    count, _ = await pipe.execute()
    if int(count) > settings.crowd_rate_limit_per_second:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Ping rate exceeded")

    if ping.pga <= settings.crowd_pga_threshold_g:
        return ShakeAccepted(above_threshold=False)
    engine: CrowdClusterEngine = request.app.state.crowd_cluster
    result = await engine.add(ping)
    return ShakeAccepted(
        above_threshold=True,
        cell_id=result.cell_id,
        independent_devices=result.device_count,
        triggered=result.triggered,
    )
