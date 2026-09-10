from __future__ import annotations

import pytest
from fakeredis.aioredis import FakeRedis

from api.config import AppSettings
from api.devices_store import DeviceRepository
from api.schemas import DeviceRegistration, ShakePing
from crowdsourcing.cluster import CrowdClusterEngine


@pytest.mark.asyncio
async def test_device_registration_and_spatial_selection() -> None:
    redis = FakeRedis(decode_responses=True)
    repository = DeviceRepository(redis)
    await repository.register(DeviceRegistration(
        device_id="device-0001", platform="android", fcm_token="f" * 64,
        zone_id="andes", latitude=4.65, longitude=-74.05,
        play_integrity_token="integrity-token-android",
    ))
    targets = await repository.recipients(
        zone_id="andes", latitude=4.66, longitude=-74.04, radius_km=10,
    )
    assert len(targets) == 1
    assert targets[0].device_id == "device-0001"
    assert await repository.unregister("device-0001")
    assert not await repository.exists("device-0001")


class FakeClusterRedis:
    def __init__(self, result: list) -> None:
        self.result = result
        self.args = None

    async def eval(self, *args):
        self.args = args
        return self.result


@pytest.mark.asyncio
async def test_crowd_cluster_uses_atomic_unique_device_window() -> None:
    redis = FakeClusterRedis([10, 1, "100-0"])
    settings = AppSettings(crowd_min_devices=10, crowd_h3_resolution=7)
    engine = CrowdClusterEngine(redis, settings)  # type: ignore[arg-type]
    result = await engine.add(ShakePing(
        device_id="device-0001", lat=4.65, lon=-74.05, pga=0.08,
        timestamp=1_723_860_604.12,
    ))
    assert result.device_count == 10
    assert result.triggered
    assert result.stream_id == "100-0"
    assert result.cell_id == "8766e42d2ffffff"
    neighborhood = engine.neighborhood_for(4.65, -74.05)
    assert neighborhood.primary in neighborhood.cells
    assert len(neighborhood.cells) == 7
    assert redis.args is not None
    assert redis.args[1] == 15


@pytest.mark.asyncio
async def test_device_registration_records_integrity_verified() -> None:
    redis = FakeRedis(decode_responses=True)
    repository = DeviceRepository(redis)
    registration = DeviceRegistration(
        device_id="device-unverified",
        platform="android",
        fcm_token="u" * 64,
        zone_id="andes",
        play_integrity_token="test-token-16chars",
    )
    await repository.register(registration, integrity_verified=False)
    assert not await repository.is_integrity_verified("device-unverified")

    await repository.register(registration, integrity_verified=True)
    assert await repository.is_integrity_verified("device-unverified")


@pytest.mark.asyncio
async def test_unverified_device_blocked_from_crowdsourcing_when_integrity_enabled() -> None:
    from unittest.mock import AsyncMock, MagicMock

    from fastapi import HTTPException, Request

    from crowdsourcing.ingest import ingest_shake

    redis = FakeRedis(decode_responses=True)
    repository = DeviceRepository(redis)
    registration = DeviceRegistration(
        device_id="device-unverified",
        platform="android",
        fcm_token="u" * 64,
        zone_id="andes",
        play_integrity_token="test-token-16chars",
    )
    await repository.register(registration, integrity_verified=False)

    settings = AppSettings(
        integrity_verification_enabled=True,
        crowd_master_secret="master-secret-at-least-32-bytes-long",
    )
    request = MagicMock(spec=Request)
    request.body = AsyncMock(
        return_value=b'{"device_id":"device-unverified","lat":4.65,"lon":-74.05,"pga":0.08,"timestamp":1723860604.12}'
    )

    with pytest.raises(HTTPException) as exc:
        await ingest_shake(
            request,
            settings=settings,
            devices=repository,
        )
    assert exc.value.status_code == 403
    assert "verified device integrity" in exc.value.detail


