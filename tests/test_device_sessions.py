from __future__ import annotations

import pytest
from fakeredis.aioredis import FakeRedis

from api.config import AppSettings
from api.device_sessions import DeviceSessionRepository


@pytest.mark.asyncio
async def test_session_is_rotated_and_old_token_is_revoked() -> None:
    redis = FakeRedis(decode_responses=True)
    sessions = DeviceSessionRepository(redis, ttl_seconds=3_600)

    first = await sessions.issue("device-0001")
    second = await sessions.issue("device-0001")

    assert first != second
    assert await sessions.resolve(first) is None
    assert await sessions.resolve(second) == "device-0001"


@pytest.mark.asyncio
async def test_session_revoke_removes_the_installation_capability() -> None:
    redis = FakeRedis(decode_responses=True)
    sessions = DeviceSessionRepository(redis, ttl_seconds=AppSettings().device_session_ttl_seconds)
    token = await sessions.issue("device-0001")

    await sessions.revoke("device-0001")

    assert await sessions.resolve(token) is None
