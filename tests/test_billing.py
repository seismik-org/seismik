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


@pytest.mark.asyncio
async def test_monthly_reservation_is_atomic_across_concurrent_keys() -> None:
    import asyncio

    from fastapi import HTTPException

    from api.billing import record_usage, summary

    redis = FakeRedis(decode_responses=True)
    results = await asyncio.gather(*(
        record_usage(redis, "dev", "events:read", f"key-{index}", monthly_limit=3)
        for index in range(20)
    ), return_exceptions=True)
    assert sum(result is None for result in results) == 3
    failures = [result for result in results if result is not None]
    assert all(isinstance(result, HTTPException) and result.status_code == 429 for result in failures)
    usage = await summary(redis, "dev")
    assert usage["requests"] == usage["events_read"] == 3
    assert usage["credit_balance_microunits"] == 0


@pytest.mark.asyncio
async def test_monthly_quota_renews_in_new_utc_period(monkeypatch) -> None:
    from api import billing

    redis = FakeRedis(decode_responses=True)
    monkeypatch.setattr(billing, "period_for", lambda: "202610")
    await billing.record_usage(redis, "dev", "stations:read", "key", monthly_limit=1)
    monkeypatch.setattr(billing, "period_for", lambda: "202611")
    await billing.record_usage(redis, "dev", "events:read", "key", monthly_limit=1)
    assert (await billing.summary(redis, "dev"))["requests"] == 1
    assert await redis.hget("seismik:billing:meter:dev:202610", "requests") == "1"
