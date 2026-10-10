from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fakeredis.aioredis import FakeRedis
from fastapi import HTTPException
from pydantic import ValidationError

from api.config import AppSettings
from api.devices_store import DeviceRepository
from api.schemas import DeviceRegistration
from api.security import create_signature, derive_crowd_token
from crowdsourcing.shadow import (
    CrowdShadowEngine,
    Observation,
    Presence,
    ingest_observation,
    quality_reason,
)


def presence(i=0, **changes):
    return Presence(device_id=f"shadow-device-{i:04d}", lat=4.65 + (i % 2) * .003,
                    lon=-74.05, timestamp=1000, location_accuracy_m=10,
                    stationary_seconds=30, sampling_hz=50, max_gap_ms=20, **changes)


def observation(i=0):
    return Observation(**presence(i).model_dump(), report_id=uuid4(), peak_g=.08,
                       rms_g=.05, duration_ms=200, samples=11, threshold_samples=5)


@pytest.mark.asyncio
async def test_real_lua_requires_availability_unique_devices_and_spatial_diversity():
    redis = FakeRedis(decode_responses=True)
    settings = AppSettings(crowd_min_devices=10)
    engine = CrowdShadowEngine(redis, settings)
    for i in range(10):
        await engine.add(presence(i), 1000)
    for i in range(9):
        result = await engine.add(observation(i), 1001)
        assert not result.candidate
    repeated = await engine.add(observation(0), 1001)
    assert repeated.signal_devices == 9
    result = await engine.add(observation(9), 1001)
    assert result.candidate and result.available_devices == result.signal_devices == 10
    assert result.spatial_cells == 2 and result.alert_eligible is False
    assert await redis.xlen(settings.candidate_stream) == 0
    messages = await redis.xrange(settings.crowd_v2_stream)
    assert len(messages) == 1
    event = json.loads(messages[0][1]["payload"])
    assert event["type"] == "crowd_shadow_candidate"
    assert event["epicenter"] is None and event["magnitude"] is None
    assert "device_id" not in messages[0][1]["payload"]
    await engine.add(observation(8), 1001.1)
    assert await redis.xlen(settings.crowd_v2_stream) == 1
    await redis.aclose()


@pytest.mark.asyncio
async def test_one_building_and_stale_presence_do_not_pass():
    redis = FakeRedis(decode_responses=True)
    engine = CrowdShadowEngine(redis, AppSettings())
    for i in range(10):
        p = presence(i).model_copy(update={"lat": 4.65})
        await engine.add(p, 1000)
        o = observation(i).model_copy(update={"lat": 4.65})
        result = await engine.add(o, 1001)
    assert result.signal_devices == 10 and result.spatial_cells == 1 and not result.candidate
    late = await engine.add(observation(0), 1200)
    assert late.available_devices == late.signal_devices == 0 and not late.candidate
    await redis.aclose()


@pytest.mark.asyncio
async def test_no_presence_cannot_vote_and_expired_signals_are_removed():
    redis = FakeRedis(decode_responses=True)
    engine = CrowdShadowEngine(redis, AppSettings())
    for i in range(10):
        assert not (await engine.add(observation(i), 1000)).candidate
    for i in range(10):
        await engine.add(presence(i), 1001)
    result = await engine.add(observation(0), 1004)
    assert result.signal_devices == 1 and not result.candidate
    await redis.aclose()


@pytest.mark.asyncio
async def test_fraction_scales_with_available_network():
    redis = FakeRedis(decode_responses=True)
    settings = AppSettings(crowd_v2_min_fraction=.5)
    engine = CrowdShadowEngine(redis, settings)
    for i in range(30):
        await engine.add(presence(i), 1000)
    for i in range(14):
        assert not (await engine.add(observation(i), 1001)).candidate
    assert (await engine.add(observation(14), 1001)).candidate
    await redis.aclose()


@pytest.mark.asyncio
async def test_concurrent_votes_emit_only_one_shadow_candidate():
    redis = FakeRedis(decode_responses=True)
    engine = CrowdShadowEngine(redis, AppSettings())
    for i in range(20):
        await engine.add(presence(i), 1000)
    await asyncio.gather(*(engine.add(observation(i), 1001) for i in range(20)))
    assert await redis.xlen(engine.settings.crowd_v2_stream) == 1
    await redis.aclose()


@pytest.mark.parametrize("changes,reason", [
    ({"stationary_seconds": 29}, "insufficient_stationary_baseline"),
    ({"sampling_hz": 10}, "sampling_quality"),
    ({"max_gap_ms": 101}, "sampling_quality"),
    ({"location_accuracy_m": 101}, "imprecise_location"),
    ({"duration_ms": 100}, "impulse_or_inconsistent_summary"),
    ({"threshold_samples": 1}, "impulse_or_inconsistent_summary"),
    ({"rms_g": .2}, "impulse_or_inconsistent_summary"),
    ({"samples": 100}, "impulse_or_inconsistent_summary"),
])
def test_quality_gates(changes, reason):
    assert quality_reason(observation().model_copy(update=changes)) == reason


def test_numeric_and_stream_safety():
    with pytest.raises(ValidationError):
        Observation.model_validate({**observation().model_dump(), "peak_g": float("nan")})
    for stream in ("seismik:events:candidates", "seismik:crowd:shadow:v2"):
        settings = AppSettings(crowd_v2_stream=stream, candidate_stream=stream)
        with pytest.raises(ValueError, match="isolated"):
            CrowdShadowEngine(FakeRedis(), settings)


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["valid", "disabled", "unverified", "outside_pilot", "stale", "future", "bad_signature", "duplicate"])
async def test_authenticated_v2_contract(monkeypatch, case):
    now = 2000.0
    monkeypatch.setattr("crowdsourcing.shadow.time.time", lambda: now)
    redis = FakeRedis(decode_responses=True)
    settings = AppSettings(crowd_v2_enabled=case != "disabled",
                           crowd_v2_device_allowlist=() if case == "outside_pilot" else ("shadow-device-0000",),
                           crowd_master_secret="test-only-shadow-secret")
    devices = DeviceRepository(redis)
    ping = observation().model_copy(update={"timestamp": now + (20 if case == "future" else -20 if case == "stale" else 0)})
    await devices.register(DeviceRegistration(device_id=ping.device_id, platform="android",
                           latitude=4.65, longitude=-74.05,
                           play_integrity_token="test-only-integrity-token"),
                           integrity_verified=case != "unverified")
    body = ping.model_dump_json().encode()
    stamp = str(now)
    signature = create_signature(derive_crowd_token("test-only-shadow-secret", ping.device_id), stamp, body)
    if case == "bad_signature":
        signature = "0" * 64
    request = SimpleNamespace(body=AsyncMock(return_value=body), app=SimpleNamespace(state=SimpleNamespace(
        redis=redis, crowd_shadow=CrowdShadowEngine(redis, settings))))
    if case in {"valid", "duplicate"}:
        result = await ingest_observation(request, stamp, signature, settings, devices)
        assert not result.candidate and not result.alert_eligible
        if case == "duplicate":
            result = await ingest_observation(request, stamp, signature, settings, devices)
            assert result.reason == "duplicate_report"
    else:
        with pytest.raises(HTTPException) as error:
            await ingest_observation(request, stamp, signature, settings, devices)
        assert error.value.status_code == (503 if case == "disabled" else 403 if case in {"unverified", "outside_pilot"} else 401)
    await redis.aclose()
