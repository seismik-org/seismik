"""Los sismos de los catálogos oficiales llegan a quien los sintió."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from fakeredis.aioredis import FakeRedis

from api.config import AppSettings
from api.devices_store import DeviceRepository
from api.schemas import DeviceRegistration, DeviceTarget
from dispatcher.consumer import StreamConsumer
from dispatcher.policy import CATALOG_ORIGIN, AlertPolicy
from dispatcher.push import PushResult
from eew.models import OfficialReport
from eew.official import OfficialSource
from eew.simulation import DRILL_PREFIX
from integrations.catalog_alerts import CatalogAlertFeed, alertable

NOW = datetime.now(timezone.utc).replace(microsecond=0)
START = NOW - timedelta(minutes=60)

SGC = OfficialSource(
    id="sgc_colombia", agency="SGC", jurisdiction="Colombia", countries=("CO",),
    adapter="sgc_geojson", endpoint="https://example.test",
    official_site="https://www.sgc.gov.co/sismos", priority=100,
)
USGS = OfficialSource(
    id="usgs_global", agency="USGS", jurisdiction="Global", countries=("US",),
    adapter="fdsn_geojson", endpoint="https://example.test",
    official_site="https://earthquake.usgs.gov/earthquakes/", priority=10, global_fallback=True,
)


def report(
    event_id: str = "SGC2026abc",
    *,
    source_id: str = "sgc_colombia",
    minutes_ago: float = 3.0,
    magnitude: float | None = 6.4,
    depth_km: float | None = 20.0,
    latitude: float = 4.65,
    longitude: float = -74.05,
    review_status: str = "reviewed",
) -> OfficialReport:
    origin = NOW - timedelta(minutes=minutes_ago)
    return OfficialReport(
        source_id=source_id,
        agency="SGC" if source_id == "sgc_colombia" else "USGS",
        jurisdiction="Colombia",
        official_event_id=event_id,
        origin_time=origin.isoformat().replace("+00:00", "Z"),
        updated_at=None,
        latitude=latitude,
        longitude=longitude,
        depth_km=depth_km,
        magnitude=magnitude,
        magnitude_type="Mw",
        place="Sabana de Bogotá, Colombia",
        review_status=review_status,
        official_url=f"https://example.test/{event_id}",
    )


class RecordingPush:
    def __init__(self) -> None:
        self.calls: list[tuple[dict, list[DeviceTarget], bool]] = []

    async def send(self, event, targets, *, critical):
        target_list = list(targets)
        self.calls.append((event, target_list, critical))
        return PushResult(attempted=len(target_list), succeeded=len(target_list))


def feed_with(redis: FakeRedis, catalogs: dict[str, list[OfficialReport] | Exception]) -> CatalogAlertFeed:
    def fetch(source, _start, _end, _timeout):
        result = catalogs[source.id]
        if isinstance(result, Exception):
            raise result
        return result

    return CatalogAlertFeed(redis, AppSettings(), fetch=fetch)


async def register(
    redis: FakeRedis,
    device_id: str,
    *,
    latitude: float,
    longitude: float,
    early: bool = True,
    official: bool = True,
    minimum_magnitude: float = 4.0,
    radius_km: float = 250.0,
) -> None:
    await DeviceRepository(redis).register(
        DeviceRegistration(
            device_id=device_id,
            platform="android",
            fcm_token=device_id.ljust(64, "f")[:64],
            latitude=latitude,
            longitude=longitude,
            receive_early_alerts=early,
            receive_official_updates=official,
            minimum_notification_magnitude=minimum_magnitude,
            alert_radius_km=radius_km,
            play_integrity_token="integrity-token-android",
        )
    )


async def dispatch_stream(redis: FakeRedis, settings: AppSettings) -> RecordingPush:
    push = RecordingPush()
    consumer = StreamConsumer(redis, settings, DeviceRepository(redis), push, AlertPolicy(redis, settings))
    for _stream_id, fields in await redis.xrange(settings.official_stream):
        await consumer._handle_official(json.loads(fields["payload"]))
    return push


def test_only_recent_real_quakes_that_someone_felt_are_alertable() -> None:
    assert alertable(report(), START, NOW)
    assert alertable(report(magnitude=4.0, depth_km=150.0), START, NOW)  # Nido de Bucaramanga
    assert not alertable(report(minutes_ago=90), START, NOW)
    assert not alertable(report(magnitude=None), START, NOW)
    assert not alertable(report(f"{DRILL_PREFIX}bogota"), START, NOW)
    assert not alertable(report(review_status="deleted"), START, NOW)
    assert not alertable(report(magnitude=2.5, depth_km=10.0), START, NOW)
    assert not alertable(report(magnitude=3.5, depth_km=10.0), START, NOW, minimum_intensity=4)
    assert alertable(report(magnitude=4.0, depth_km=10.0), START, NOW, minimum_intensity=4)


@pytest.mark.asyncio
async def test_each_quake_reaches_the_official_stream_once() -> None:
    redis = FakeRedis(decode_responses=True)
    feed = feed_with(redis, {"sgc_colombia": [report()], "usgs_global": []})

    assert await feed.poll((SGC, USGS), NOW) == 1
    assert await feed.poll((SGC, USGS), NOW + timedelta(minutes=1)) == 0

    entries = await redis.xrange(AppSettings().official_stream)
    assert len(entries) == 1
    event = json.loads(entries[0][1]["payload"])
    assert event["origin"] == CATALOG_ORIGIN
    assert "candidate_event_id" not in event
    assert event["preferred_report"]["official_event_id"] == "SGC2026abc"


@pytest.mark.asyncio
async def test_a_broken_catalog_does_not_stop_the_others() -> None:
    redis = FakeRedis(decode_responses=True)
    feed = feed_with(redis, {"sgc_colombia": [report()], "usgs_global": TimeoutError("caído")})
    assert await feed.poll((SGC, USGS), NOW) == 1


@pytest.mark.asyncio
async def test_a_strong_catalog_quake_rings_nearby_and_notifies_those_who_felt_it() -> None:
    redis = FakeRedis(decode_responses=True)
    settings = AppSettings()
    # Cerca del epicentro, con todo apagado y la magnitud mínima al máximo.
    await register(
        redis, "device-bogota-01", latitude=4.70, longitude=-74.00,
        early=False, official=False, minimum_magnitude=9.0, radius_km=10,
    )
    # Medellín, ~240 km: se siente (MMI ~III-IV), no es fuerte.
    await register(redis, "device-medellin-1", latitude=6.25, longitude=-75.57)
    # Barranquilla, ~700 km: no se siente.
    await register(redis, "device-barranquilla", latitude=10.96, longitude=-74.80, radius_km=2_000)

    await feed_with(redis, {"sgc_colombia": [report()], "usgs_global": []}).poll((SGC, USGS), NOW)
    push = await dispatch_stream(redis, settings)

    sent = {critical: [target.device_id for target in targets] for _event, targets, critical in push.calls}
    assert sent == {True: ["device-bogota-01"], False: ["device-medellin-1"]}
    # Los webhooks de organizaciones no reciben los sismos de catálogo.
    assert await redis.xlen(settings.integration_stream) == 0


@pytest.mark.asyncio
async def test_the_same_quake_from_another_agency_is_not_announced_twice() -> None:
    redis = FakeRedis(decode_responses=True)
    settings = AppSettings()
    await register(redis, "device-medellin-1", latitude=6.25, longitude=-75.57)
    usgs_copy = report("us7000abc", source_id="usgs_global", magnitude=6.5, latitude=4.70, longitude=-74.10)

    await feed_with(redis, {"sgc_colombia": [report()], "usgs_global": [usgs_copy]}).poll((SGC, USGS), NOW)
    push = await dispatch_stream(redis, settings)

    assert [event["preferred_report"]["source_id"] for event, _targets, _critical in push.calls] == [
        "sgc_colombia"
    ]


@pytest.mark.asyncio
async def test_a_large_upward_revision_is_announced_again() -> None:
    redis = FakeRedis(decode_responses=True)
    settings = AppSettings()
    await register(redis, "device-medellin-1", latitude=6.25, longitude=-75.57)
    feed = feed_with(redis, {"sgc_colombia": [report()], "usgs_global": []})
    await feed.poll((SGC, USGS), NOW)
    await dispatch_stream(redis, settings)

    feed = feed_with(redis, {"sgc_colombia": [report(magnitude=7.1)], "usgs_global": []})
    assert await feed.poll((SGC, USGS), NOW + timedelta(minutes=1)) == 1
    await redis.xtrim(settings.official_stream, maxlen=1)
    push = await dispatch_stream(redis, settings)
    assert [event["preferred_report"]["magnitude"] for event, _targets, _critical in push.calls] == [7.1]


def test_a_blocked_agency_leaves_the_alert_cycle() -> None:
    """Misma regla que en el publicador: fuera del ciclo, no del catálogo."""

    feed = feed_with(FakeRedis(decode_responses=True), {})
    watched = {source.id for source in feed.watched_sources()}

    assert "sgc_colombia" not in watched
    assert "usgs_global" in watched, "excluir una agencia no puede apagar las demás"


def test_the_alert_threshold_is_shaking_and_not_magnitude() -> None:
    """Lo que decide es el perímetro de sacudida, no el número de la magnitud.

    Un M4 somero bajo una ciudad sacude IV; el mismo M4 a 150 km de
    profundidad, en el nido de Bucaramanga, apenas se siente. El umbral del
    ajuste tiene que llegar a `alertable`, no quedarse escrito.
    """

    settings = AppSettings()
    assert settings.catalog_alerts_minimum_intensity == 4.0
    threshold = settings.catalog_alerts_minimum_intensity

    assert alertable(report(magnitude=4.0, depth_km=10.0), START, NOW, threshold)
    assert not alertable(report(magnitude=4.0, depth_km=150.0), START, NOW, threshold)
    # Un M4.2 somero entra, aunque el umbral por magnitud de antes (4.5) lo dejaba fuera.
    assert alertable(report(magnitude=4.2, depth_km=8.0), START, NOW, threshold)
    # Y un sismo profundo grande sí alcanza esa sacudida en superficie.
    assert alertable(report(magnitude=6.5, depth_km=150.0), START, NOW, threshold)


def test_without_a_threshold_everything_felt_still_alerts() -> None:
    """El valor por defecto no puede endurecer a quien llame sin pasarlo."""

    assert alertable(report(magnitude=4.0, depth_km=150.0), START, NOW)
