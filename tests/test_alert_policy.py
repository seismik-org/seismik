"""Pruebas unitarias de la política de alertas: dedup, cooldown y umbrales."""
from __future__ import annotations

import pytest
from fakeredis.aioredis import FakeRedis

from api.config import AppSettings
from api.schemas import DeviceTarget
from dispatcher.policy import (
    DUPLICATE,
    ZONE_COOLDOWN,
    AlertPolicy,
    haversine_km,
)


def candidate(event_id: str = "candidate-1", zone_id: str = "andes") -> dict:
    return {
        "event_id": event_id,
        "type": "earthquake_candidate",
        "zone_id": zone_id,
        "estimated_latitude": 4.65,
        "estimated_longitude": -74.05,
    }


def device(
    device_id: str = "device-0001",
    *,
    radius_km: float = 250.0,
    magnitude: float = 4.0,
    latitude: float | None = 4.65,
    longitude: float | None = -74.05,
    early: bool = True,
    official: bool = True,
) -> DeviceTarget:
    return DeviceTarget(
        device_id=device_id,
        platform="android",
        token="f" * 64,
        receive_early_alerts=early,
        receive_official_updates=official,
        minimum_notification_magnitude=magnitude,
        alert_radius_km=radius_km,
        latitude=latitude,
        longitude=longitude,
    )


@pytest.mark.asyncio
async def test_same_event_is_claimed_once_even_after_redelivery() -> None:
    policy = AlertPolicy(FakeRedis(decode_responses=True), AppSettings())
    first = await policy.claim_candidate(candidate())
    second = await policy.claim_candidate(candidate())
    assert first.allowed
    assert second.suppressed
    assert second.reason == DUPLICATE


@pytest.mark.asyncio
async def test_second_event_in_same_zone_waits_for_cooldown() -> None:
    policy = AlertPolicy(FakeRedis(decode_responses=True), AppSettings(alert_cooldown_seconds=60))
    assert (await policy.claim_candidate(candidate("candidate-1"))).allowed
    blocked = await policy.claim_candidate(candidate("candidate-2"))
    assert blocked.suppressed
    assert blocked.reason == ZONE_COOLDOWN


@pytest.mark.asyncio
async def test_other_zone_alerts_while_the_first_zone_cools_down() -> None:
    policy = AlertPolicy(FakeRedis(decode_responses=True), AppSettings())
    assert (await policy.claim_candidate(candidate("candidate-1", "andes"))).allowed
    assert (await policy.claim_candidate(candidate("candidate-2", "caribe"))).allowed


@pytest.mark.asyncio
async def test_release_lets_the_stream_retry_after_a_failed_push() -> None:
    policy = AlertPolicy(FakeRedis(decode_responses=True), AppSettings())
    decision = await policy.claim_candidate(candidate())
    await policy.release(decision)
    retry = await policy.claim_candidate(candidate())
    assert retry.allowed


@pytest.mark.asyncio
async def test_official_updates_are_deduplicated_without_zone_cooldown() -> None:
    policy = AlertPolicy(FakeRedis(decode_responses=True), AppSettings())
    event = {"event_id": "official-1", "type": "official_report_update"}
    assert (await policy.claim_official(event)).allowed
    assert (await policy.claim_official(event)).suppressed
    assert (await policy.claim_official({**event, "event_id": "official-2"})).allowed


def test_critical_filter_respects_subscription_and_chosen_radius() -> None:
    policy = AlertPolicy(FakeRedis(decode_responses=True), AppSettings())
    near = device("device-near", radius_km=250, latitude=4.70, longitude=-74.00)
    far = device("device-far", radius_km=50, latitude=6.25, longitude=-75.57)
    muted = device("device-muted", early=False)
    selected = policy.filter_critical(
        [near, far, muted], latitude=4.65, longitude=-74.05
    )
    assert [target.device_id for target in selected] == ["device-near"]


def test_official_filter_applies_the_minimum_magnitude_of_each_device() -> None:
    policy = AlertPolicy(FakeRedis(decode_responses=True), AppSettings())
    sensitive = device("device-sensitive", magnitude=2.0)
    conservative = device("device-conservative", magnitude=6.0)
    selected = policy.filter_official(
        [sensitive, conservative], magnitude=4.5, latitude=4.65, longitude=-74.05
    )
    assert [target.device_id for target in selected] == ["device-sensitive"]


def test_devices_without_coordinates_are_not_excluded_by_distance() -> None:
    policy = AlertPolicy(FakeRedis(decode_responses=True), AppSettings())
    unlocated = device("device-zone-only", latitude=None, longitude=None, radius_km=10)
    assert policy.filter_critical([unlocated], latitude=4.65, longitude=-74.05)


def test_unlocated_candidate_reaches_every_subscribed_device() -> None:
    policy = AlertPolicy(FakeRedis(decode_responses=True), AppSettings())
    target = device(radius_km=10, latitude=-33.4, longitude=-70.6)
    assert policy.filter_critical([target], latitude=None, longitude=None)


def test_device_radius_never_exceeds_the_platform_geofence() -> None:
    policy = AlertPolicy(FakeRedis(decode_responses=True), AppSettings(geofence_radius_km=100))
    greedy = device("device-greedy", radius_km=2_000, latitude=8.0, longitude=-74.05)
    assert not policy.filter_critical([greedy], latitude=4.65, longitude=-74.05)


def test_preliminary_wave_reaches_a_person_beyond_their_fixed_radius() -> None:
    policy = AlertPolicy(FakeRedis(decode_responses=True), AppSettings())
    # ~390 km desde Bogotá: fuera de sus 50 km, pero dentro de la zona de
    # sacudida perceptible que estima una M7 preliminar.
    target = device("wave-target", radius_km=50, latitude=7.0, longitude=-75.0)
    assert policy.filter_critical(
        [target], latitude=4.65, longitude=-74.05, magnitude=7.0
    ) == [target]


def test_preliminary_wave_does_not_promote_a_small_event_at_long_distance() -> None:
    policy = AlertPolicy(FakeRedis(decode_responses=True), AppSettings())
    target = device("far-target", radius_km=2_000, latitude=7.0, longitude=-75.0)
    assert not policy.filter_critical(
        [target], latitude=4.65, longitude=-74.05, magnitude=4.0
    )


def test_haversine_matches_a_known_bogota_medellin_distance() -> None:
    distance = haversine_km(4.711, -74.072, 6.244, -75.581)
    assert 230 < distance < 250
