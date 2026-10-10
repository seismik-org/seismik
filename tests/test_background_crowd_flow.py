"""Background summaries use the existing authenticated API, not a new service."""
from __future__ import annotations

import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fakeredis.aioredis import FakeRedis
from fastapi import HTTPException

from api.config import AppSettings
from api.devices_store import DeviceRepository
from api.schemas import DeviceRegistration
from api.security import create_signature, derive_crowd_token
from crowdsourcing.cluster import ClusterResult
from crowdsourcing.ingest import ingest_shake


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["valid", "bad_signature", "stale", "below_threshold", "unknown"])
async def test_background_summary_contract(case: str) -> None:
    redis = FakeRedis(decode_responses=True)
    devices = DeviceRepository(redis)
    settings = AppSettings(integrity_verification_enabled=True,
                           crowd_master_secret="only-a-test-secret-not-a-production-key")
    device_id = "background-device-0001"
    if case != "unknown":
        await devices.register(DeviceRegistration(
            device_id=device_id, platform="android", latitude=4.65, longitude=-74.05,
            play_integrity_token="test-integrity-token-16chars",
        ), integrity_verified=True)
    now = time.time()
    body = json.dumps({"device_id": device_id, "lat": 4.65, "lon": -74.05,
                       "pga": 0.001 if case == "below_threshold" else 0.08,
                       "timestamp": (now - 3600 if case == "stale" else now) * 1000},
                      separators=(",", ":")).encode()
    stamp = str(now)
    token = derive_crowd_token(settings.crowd_master_secret.get_secret_value(), device_id)
    signature = "0" * 64 if case == "bad_signature" else create_signature(token, stamp, body)
    engine = SimpleNamespace(add=AsyncMock(return_value=ClusterResult("test-cell", 1, False, None)))
    request = SimpleNamespace(body=AsyncMock(return_value=body),
                              app=SimpleNamespace(state=SimpleNamespace(redis=redis, crowd_cluster=engine)))
    if case in {"bad_signature", "stale", "unknown"}:
        with pytest.raises(HTTPException) as error:
            await ingest_shake(request, stamp, signature, settings, devices)
        assert error.value.status_code == 401
        engine.add.assert_not_awaited()
    else:
        result = await ingest_shake(request, stamp, signature, settings, devices)
        assert result.accepted and not result.triggered
        if case == "valid":
            assert result.above_threshold and result.independent_devices == 1
            ping = engine.add.await_args.args[0]
            assert abs(ping.timestamp_seconds - now) < 0.001
        else:
            assert not result.above_threshold
            engine.add.assert_not_awaited()
    await redis.aclose()
