"""Authenticated experimental phone network. Never publishes to an alert stream.

Quality fields are client observations, not trusted proof of shaking. HMAC and
Play Integrity do not solve Sybil/location spoofing. No magnitude is inferred.
Redis standalone/Sentinel is required, as with the legacy cross-cell script.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Literal, cast

import h3  # type: ignore[import-untyped]
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import Field, ValidationError
from redis.asyncio import Redis

from api.config import AppSettings
from api.dependencies import get_app_settings, get_devices
from api.devices_store import DeviceRepository
from api.schemas import Latitude, Longitude, StrictModel
from api.security import derive_crowd_token, verify_signature

router = APIRouter(prefix="/v1/crowd/v2", tags=["crowd-shadow"])


class Presence(StrictModel):
    device_id: str = Field(min_length=8, max_length=128)
    lat: Latitude
    lon: Longitude
    timestamp: float = Field(gt=0, allow_inf_nan=False)
    location_accuracy_m: float = Field(ge=0, le=500, allow_inf_nan=False)
    stationary_seconds: float = Field(ge=0, le=86400, allow_inf_nan=False)
    sampling_hz: float = Field(gt=0, le=1000, allow_inf_nan=False)
    max_gap_ms: float = Field(ge=0, allow_inf_nan=False)


class Observation(Presence):
    report_id: uuid.UUID
    peak_g: float = Field(gt=0, le=5, allow_inf_nan=False,
                          description="Phone acceleration peak, NOT calibrated ground PGA")
    rms_g: float = Field(gt=0, le=5, allow_inf_nan=False)
    duration_ms: float = Field(gt=0, le=2000, allow_inf_nan=False)
    samples: int = Field(ge=1, le=2000)
    threshold_samples: int = Field(ge=1, le=2000)


class ShadowAccepted(StrictModel):
    accepted: bool = True
    mode: Literal["shadow_only"] = "shadow_only"
    alert_eligible: Literal[False] = False
    reason: str
    available_devices: int = 0
    signal_devices: int = 0
    spatial_cells: int = 0
    candidate: bool = False


def quality_reason(value: Presence) -> str | None:
    if value.location_accuracy_m > 100:
        return "imprecise_location"
    if value.stationary_seconds < 30:
        return "insufficient_stationary_baseline"
    if not 20 <= value.sampling_hz <= 250 or value.max_gap_ms > 100:
        return "sampling_quality"
    if isinstance(value, Observation):
        if (value.duration_ms < 200 or value.samples < 5 or value.threshold_samples < 3
                or value.threshold_samples > value.samples or value.rms_g > value.peak_g
                or abs(value.samples / (value.duration_ms / 1000) - value.sampling_hz)
                > max(5, value.sampling_hz * .3)):
            return "impulse_or_inconsistent_summary"
    return None


SHADOW_LUA = """
local n = tonumber(ARGV[1])
local now = tonumber(ARGV[2])
local device = ARGV[3]
local available = {}
local signals = {}
local buckets = {}
for i = 1, n do
  redis.call('ZREMRANGEBYSCORE', KEYS[i], '-inf', now - tonumber(ARGV[4]))
  for _, id in ipairs(redis.call('ZRANGEBYSCORE', KEYS[n+i], '-inf', now - tonumber(ARGV[5]))) do
    redis.call('HDEL', KEYS[2*n+i], id)
  end
  redis.call('ZREMRANGEBYSCORE', KEYS[n+i], '-inf', now - tonumber(ARGV[5]))
end
if ARGV[6] == 'presence' then
  redis.call('ZADD', KEYS[1], now, device)
  redis.call('EXPIRE', KEYS[1], ARGV[4])
  return {0, 0, 0, 0}
end
redis.call('ZADD', KEYS[n+1], now, device)
redis.call('EXPIRE', KEYS[n+1], ARGV[4])
redis.call('HSET', KEYS[2*n+1], device, ARGV[7])
redis.call('EXPIRE', KEYS[2*n+1], ARGV[4])
for i = 1, n do
  for _, id in ipairs(redis.call('ZRANGE', KEYS[i], 0, -1)) do available[id] = true end
end
local active_count = 0
for _ in pairs(available) do active_count = active_count + 1 end
for i = 1, n do
  for _, id in ipairs(redis.call('ZRANGE', KEYS[n+i], 0, -1)) do
    if available[id] and not signals[id] then
      signals[id] = true
      local bucket = redis.call('HGET', KEYS[2*n+i], id)
      if bucket then buckets[bucket] = true end
    end
  end
end
local signal_count = 0
local bucket_count = 0
for _ in pairs(signals) do signal_count = signal_count + 1 end
for _ in pairs(buckets) do bucket_count = bucket_count + 1 end
local required = math.max(tonumber(ARGV[8]), math.ceil(active_count * tonumber(ARGV[9])))
local fired = 0
if active_count >= tonumber(ARGV[8]) and signal_count >= required and bucket_count >= tonumber(ARGV[10]) then
  local blocked = false
  for i = 1, n do if redis.call('EXISTS', KEYS[3*n+i]) == 1 then blocked = true end end
  if not blocked then
    for i = 1, n do redis.call('SET', KEYS[3*n+i], '1', 'EX', ARGV[11]) end
    local payload = cjson.decode(ARGV[12])
    payload.available_devices = active_count
    payload.signal_devices = signal_count
    payload.spatial_cells = bucket_count
    payload.required_devices = required
    redis.call('XADD', KEYS[4*n+1], 'MAXLEN', '~', ARGV[13], '*', 'payload', cjson.encode(payload))
    fired = 1
  end
end
return {active_count, signal_count, bucket_count, fired}
"""


class CrowdShadowEngine:
    def __init__(self, redis: Redis, settings: AppSettings):
        # A hard namespace boundary, not merely a default setting.
        if (not settings.crowd_v2_stream.startswith("seismik:crowd:shadow:")
                or settings.crowd_v2_stream in {settings.candidate_stream, settings.official_stream,
                                               settings.magnitude_stream}):
            raise ValueError("Crowd v2 must use an isolated shadow stream")
        self.redis, self.settings = redis, settings

    async def add(self, value: Presence, now: float) -> ShadowAccepted:
        reason = quality_reason(value)
        if reason:
            return ShadowAccepted(reason=reason)
        observation = isinstance(value, Observation)
        if isinstance(value, Observation) and value.peak_g <= self.settings.crowd_pga_threshold_g:
            return ShadowAccepted(reason="below_threshold")
        cell = h3.latlng_to_cell(value.lat, value.lon, self.settings.crowd_h3_resolution)
        cells = (cell, *sorted(c for c in h3.grid_disk(cell, 1) if c != cell))
        keys = [f"seismik:crowd:v2:{kind}:{c}"
                for kind in ("presence", "signals", "buckets", "cooldown") for c in cells]
        payload = {"event_id": str(uuid.uuid4()), "type": "crowd_shadow_candidate",
                   "status": "experimental_unvalidated", "alert_eligible": False,
                   "detected_at": now, "observed_cell": cell,
                   "magnitude": None, "epicenter": None,
                   "source": "mobile_accelerometer_v2_shadow"}
        result = await self.redis.eval(
            SHADOW_LUA, len(keys) + 1, *keys, self.settings.crowd_v2_stream,
            len(cells), now, value.device_id, self.settings.crowd_v2_presence_seconds,
            self.settings.crowd_window_seconds, "observation" if observation else "presence",
            h3.latlng_to_cell(value.lat, value.lon, 10), self.settings.crowd_min_devices,
            self.settings.crowd_v2_min_fraction, self.settings.crowd_v2_min_spatial_cells,
            self.settings.crowd_trigger_cooldown_seconds, json.dumps(payload),
            self.settings.stream_maxlen,
        )
        return ShadowAccepted(reason="shadow_candidate" if result[3] else "observed" if observation
                              else "presence_recorded", available_devices=int(result[0]),
                              signal_devices=int(result[1]), spatial_cells=int(result[2]),
                              candidate=bool(result[3]))


async def _ingest(request: Request, kind: Literal["presence", "observation"],
                  stamp: str | None, signature: str | None, settings: AppSettings,
                  devices: DeviceRepository) -> ShadowAccepted:
    if not settings.crowd_v2_enabled:
        raise HTTPException(status_code=503, detail="Experimental crowd network disabled")
    body = await request.body()
    if len(body) > 4096:
        raise HTTPException(status_code=413, detail="Summary too large")
    try:
        value = Observation.model_validate_json(body) if kind == "observation" else Presence.model_validate_json(body)
    except ValidationError:
        raise HTTPException(status_code=422, detail="Invalid motion summary") from None
    if not await devices.exists(value.device_id) or not await devices.is_integrity_verified(value.device_id):
        raise HTTPException(status_code=403, detail="Verified registered device required")
    if value.device_id not in settings.crowd_v2_device_allowlist:
        raise HTTPException(status_code=403, detail="Device is not enrolled in the experimental pilot")
    verify_signature(secret=derive_crowd_token(settings.crowd_master_secret.get_secret_value(), value.device_id),
                     timestamp=stamp, signature=signature, body=body,
                     max_skew_seconds=settings.crowd_max_clock_skew_seconds)
    now = time.time()
    # Epoch seconds in v2; receipt time is the clustering clock. No future votes.
    if abs(now - value.timestamp) > settings.crowd_max_clock_skew_seconds:
        raise HTTPException(status_code=401, detail="Stale motion summary")
    redis = cast(Redis, request.app.state.redis)
    key = f"seismik:crowd:v2:rate:{value.device_id}:{int(now // 60)}"
    pipe = redis.pipeline(transaction=True)
    pipe.incr(key)
    pipe.expire(key, 120)
    count, _ = await pipe.execute()
    if int(count) > 30:
        raise HTTPException(status_code=429, detail="Summary rate exceeded")
    if isinstance(value, Observation):
        if not await redis.set(f"seismik:crowd:v2:report:{value.device_id}:{value.report_id}",
                               "1", nx=True, ex=120):
            return ShadowAccepted(reason="duplicate_report")
    engine = cast(CrowdShadowEngine, request.app.state.crowd_shadow)
    result = await engine.add(value, now)
    # Aggregate counters only: no device IDs, exact coordinates or raw waveforms.
    metrics = f"seismik:crowd:v2:metrics:{int(now // 86400)}"
    pipe = redis.pipeline(transaction=True)
    pipe.hincrby(metrics, result.reason, 1)
    pipe.expire(metrics, 35 * 86400)
    await pipe.execute()
    return result


@router.post("/presence", response_model=ShadowAccepted, status_code=202)
async def ingest_presence(request: Request,
                          x_device_timestamp: str | None = Header(default=None, alias="X-Seismik-Timestamp"),
                          x_device_signature: str | None = Header(default=None, alias="X-Seismik-Signature"),
                          settings: AppSettings = Depends(get_app_settings),
                          devices: DeviceRepository = Depends(get_devices)) -> ShadowAccepted:
    return await _ingest(request, "presence", x_device_timestamp, x_device_signature, settings, devices)


@router.post("/observation", response_model=ShadowAccepted, status_code=202)
async def ingest_observation(request: Request,
                             x_device_timestamp: str | None = Header(default=None, alias="X-Seismik-Timestamp"),
                             x_device_signature: str | None = Header(default=None, alias="X-Seismik-Signature"),
                             settings: AppSettings = Depends(get_app_settings),
                             devices: DeviceRepository = Depends(get_devices)) -> ShadowAccepted:
    return await _ingest(request, "observation", x_device_timestamp, x_device_signature, settings, devices)
