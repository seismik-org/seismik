from __future__ import annotations

import pytest
from fakeredis.aioredis import FakeRedis

from api.billing import apply_credit_entry


@pytest.mark.asyncio
async def test_credit_entry_is_idempotent_and_keeps_an_audit_stream() -> None:
    redis = FakeRedis(decode_responses=True)
    first = await apply_credit_entry(redis, "dev-1", "payment-123", 250_000, "test")
    duplicate = await apply_credit_entry(redis, "dev-1", "payment-123", 250_000, "test")

    assert first == 250_000
    assert duplicate == 250_000
    entries = await redis.xrange("seismik:billing:ledger:dev-1")
    assert len(entries) == 1
    assert entries[0][1]["source"] == "test"
