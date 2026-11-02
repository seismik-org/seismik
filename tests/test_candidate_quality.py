from datetime import datetime, timedelta, timezone

import pytest
from fakeredis.aioredis import FakeRedis
from safety_fixtures import eligible_candidate

from api.config import AppSettings
from dispatcher.candidate_quality import candidate_alarm_reason
from dispatcher.consumer import StreamConsumer
from dispatcher.policy import AlertPolicy


def test_complete_synthetic_gate_input_is_eligible():
    assert candidate_alarm_reason(eligible_candidate()) == "eligible"


@pytest.mark.parametrize("change,reason", [
    ({"validation_status": "beta_unvalidated"}, "association_not_validated"),
    ({"used_station_ids": ["XX.A"] * 4}, "insufficient_independent_stations"),
    ({"origin_time": (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()},
     "source_solution_not_fresh"),
])
def test_unvalidated_duplicate_or_stale_evidence_cannot_raise_public_alarm(change, reason):
    event = eligible_candidate()
    event["association_quality"].update(change)
    assert candidate_alarm_reason(event) == reason


def test_seedlink_without_a_source_model_has_no_critical_fallback():
    policy = AlertPolicy(FakeRedis(decode_responses=True), AppSettings())
    from api.schemas import DeviceTarget
    target = DeviceTarget(device_id="device-safe", platform="android", token="x" * 64)
    assert policy.filter_critical([target], latitude=None, longitude=None) == []


@pytest.mark.asyncio
async def test_unvalidated_seedlink_leaves_no_public_output_without_diagnostic_allowlist():
    redis = FakeRedis(decode_responses=True)
    settings = AppSettings()
    class UnexpectedIO:
        def __getattr__(self, name):
            raise AssertionError("Unvalidated candidate reached public delivery: " + name)
    worker = StreamConsumer(redis, settings, UnexpectedIO(), UnexpectedIO())
    await worker._handle_candidate({"event_id": "unvalidated-case", "type": "earthquake_candidate",
                                    "zone_id": "CO"})
    assert await redis.xlen(settings.alert_ledger_stream) == 0
    assert await redis.xlen(settings.integration_stream) == 0
    assert await redis.xlen(settings.push_audit_stream) == 0
