"""Pruebas unitarias de la política de alertas: dedup, cooldown y umbrales."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fakeredis.aioredis import FakeRedis

from api.config import AppSettings
from api.felt_area import FELT
from api.schemas import DeviceTarget
from dispatcher.policy import (
    ALARM,
    DUPLICATE,
    DUPLICATE_QUAKE,
    NOTICE,
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


def test_the_perimeter_replaces_the_minimum_magnitude_of_each_device() -> None:
    policy = AlertPolicy(FakeRedis(decode_responses=True), AppSettings())
    sensitive = device("device-sensitive", magnitude=2.0)
    conservative = device("device-conservative", magnitude=6.0)
    # Un M4.5 bajo sus pies se siente (MMI ~V), elija cada uno lo que elija.
    selected = policy.filter_official(
        [sensitive, conservative], magnitude=4.5, latitude=4.65, longitude=-74.05
    )
    assert [target.device_id for target in selected] == ["device-sensitive", "device-conservative"]


def test_without_a_perimeter_the_minimum_magnitude_still_applies() -> None:
    policy = AlertPolicy(FakeRedis(decode_responses=True), AppSettings())
    sensitive = device("device-sensitive", magnitude=2.0, latitude=None, longitude=None)
    conservative = device("device-conservative", magnitude=6.0, latitude=None, longitude=None)
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


NOW = datetime(2026, 9, 13, 18, 0, tzinfo=timezone.utc)


def test_strong_shaking_rings_the_alarm_whatever_the_settings() -> None:
    policy = AlertPolicy(FakeRedis(decode_responses=True), AppSettings())
    # Todo apagado, magnitud mínima 9 y 10 km de radio; un M6.5 a 20 km la sacude fuerte.
    muted = device(
        "device-muted", early=False, official=False, magnitude=9.0, radius_km=10,
        latitude=4.83, longitude=-74.05,
    )
    assert policy.classify_official(
        muted, magnitude=6.5, latitude=4.65, longitude=-74.05, depth_km=15,
        origin_time="2026-09-13T17:55:00Z", now=NOW,
    ) == ALARM
    assert policy.filter_critical(
        [muted], latitude=4.65, longitude=-74.05, magnitude=6.5, depth_km=15
    ) == [muted]


def test_an_old_report_of_strong_shaking_arrives_as_a_notice() -> None:
    policy = AlertPolicy(FakeRedis(decode_responses=True), AppSettings())
    assert policy.classify_official(
        device(), magnitude=6.5, latitude=4.65, longitude=-74.05, depth_km=15,
        origin_time="2026-09-13T16:00:00Z", now=NOW,
    ) == NOTICE


def test_felt_shaking_notifies_only_official_subscribers() -> None:
    policy = AlertPolicy(FakeRedis(decode_responses=True), AppSettings())
    # Un M5 a 50 km se siente (MMI ~IV) pero no es fuerte.
    subscriber = device("device-subscriber", latitude=5.10, longitude=-74.05)
    muted = device("device-muted", official=False, latitude=5.10, longitude=-74.05)
    for target, expected in ((subscriber, NOTICE), (muted, None)):
        assert policy.classify_official(
            target, magnitude=5.0, latitude=4.65, longitude=-74.05, depth_km=10, now=NOW
        ) == expected


def test_a_quake_nobody_felt_there_is_silent_even_with_generous_settings() -> None:
    policy = AlertPolicy(FakeRedis(decode_responses=True), AppSettings())
    generous = device("device-generous", magnitude=0.0, radius_km=2_000, latitude=6.25, longitude=-75.57)
    assert policy.classify_official(
        generous, magnitude=4.5, latitude=4.65, longitude=-74.05, depth_km=10, now=NOW
    ) is None


def test_early_alarm_starts_at_light_shaking_for_subscribers() -> None:
    policy = AlertPolicy(FakeRedis(decode_responses=True), AppSettings())
    # Un M5 a 30 km: sacudida ligera (IV), fuera de los 10 km elegidos.
    subscriber = device("device-early", radius_km=10, latitude=4.92, longitude=-74.05)
    muted = device("device-muted", early=False, latitude=4.92, longitude=-74.05)
    assert policy.filter_critical(
        [subscriber, muted], latitude=4.65, longitude=-74.05, magnitude=5.0
    ) == [subscriber]


def official_report(event_id: str, *, second: int, magnitude: float, longitude: float) -> dict:
    return {
        "event_id": event_id,
        "type": "official_report_update",
        "preferred_report": {
            "origin_time": f"2026-09-13T17:55:{second:02d}Z",
            "latitude": 6.80,
            "longitude": longitude,
            "magnitude": magnitude,
        },
    }


@pytest.mark.asyncio
async def test_the_same_quake_from_another_agency_is_announced_once() -> None:
    policy = AlertPolicy(FakeRedis(decode_responses=True), AppSettings())
    sgc = official_report("catalog:sgc:1", second=25, magnitude=4.0, longitude=-73.10)
    assert (await policy.claim_official(sgc)).allowed
    await policy.remember_official_quake(sgc["preferred_report"])

    usgs = official_report("catalog:usgs:1", second=40, magnitude=4.3, longitude=-73.20)
    duplicate = await policy.claim_official(usgs)
    assert duplicate.suppressed
    assert duplicate.reason == DUPLICATE_QUAKE

    revised = official_report("catalog:usgs:1:m48", second=40, magnitude=4.8, longitude=-73.20)
    assert (await policy.claim_official(revised)).allowed


def test_the_search_covers_a_perimeter_larger_than_the_geofence() -> None:
    settings = AppSettings()
    policy = AlertPolicy(FakeRedis(decode_responses=True), settings)
    assert policy.perimeter_search_radius_km(7.0, 10.0, FELT) > 700
    assert policy.perimeter_search_radius_km(3.0, 10.0, FELT) == settings.geofence_radius_km
    assert policy.perimeter_search_radius_km(None, None, FELT) == settings.geofence_radius_km
