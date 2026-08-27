from __future__ import annotations

import pytest
from fakeredis.aioredis import FakeRedis

from api.bus import RedisEventBus


@pytest.mark.asyncio
async def test_event_bus_is_idempotent_and_namespaces_event_types() -> None:
    redis = FakeRedis(decode_responses=True)
    bus = RedisEventBus(redis, stream_maxlen=1_000, idempotency_seconds=600)
    candidate = {"event_id": "same-id", "type": "earthquake_candidate"}
    official = {"event_id": "same-id", "type": "official_report_update"}

    first = await bus.publish_once("stream:seismik:candidates", candidate)
    duplicate = await bus.publish_once("stream:seismik:candidates", candidate)
    other_type = await bus.publish_once("stream:seismik:official", official)

    assert first.accepted and first.stream_id
    assert not duplicate.accepted and duplicate.stream_id is None
    assert other_type.accepted and other_type.stream_id
    assert await redis.xlen("stream:seismik:candidates") == 1
    assert await redis.xlen("stream:seismik:official") == 1
