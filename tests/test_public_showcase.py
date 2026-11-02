"""El panel "Así se ve Seismik" de la portada no lleva clave ni sesión: es la
misma fuente que usa la app, filtrada a lo que vale la pena mostrar en
mercadeo."""

from __future__ import annotations

import json

import httpx
import pytest
from fakeredis.aioredis import FakeRedis
from fastapi import FastAPI

from api.config import AppSettings
from api.dependencies import require_mobile_events_read
from api.edge_origin import EdgeOriginGuard
from api.public import router


def showcase_app(**settings_overrides: object) -> FastAPI:
    app = FastAPI()
    app.state.redis = FakeRedis(decode_responses=True)
    app.state.settings = AppSettings(**settings_overrides)
    app.include_router(router)
    return app


async def _add_report(
    redis: FakeRedis,
    stream: str,
    *,
    event_id: str,
    magnitude: float | None,
    place: str = "Los Santos, Santander",
    agency: str = "Servicio Geológico Colombiano",
) -> None:
    event = {
        "event_id": event_id,
        "type": "official_report_update",
        "preferred_report": {
            "origin_time": "2026-09-20T01:12:47Z",
            "latitude": 6.7,
            "longitude": -73.1,
            "magnitude": magnitude,
            "magnitude_type": "Mw",
            "depth_km": 142.0,
            "agency": agency,
            "place": place,
            "official_url": "https://example.org/report",
        },
    }
    await redis.xadd(stream, {"payload": json.dumps(event)})


@pytest.mark.asyncio
async def test_the_showcase_needs_no_key_or_session() -> None:
    app = showcase_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/v1/public/showcase-events")

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_only_events_at_or_above_the_threshold_are_shown() -> None:
    app = showcase_app(public_showcase_minimum_magnitude=4.5)
    stream = app.state.settings.official_stream
    await _add_report(app.state.redis, stream, event_id="a", magnitude=3.2)
    await _add_report(app.state.redis, stream, event_id="b", magnitude=4.5)
    await _add_report(app.state.redis, stream, event_id="c", magnitude=5.8)
    await _add_report(app.state.redis, stream, event_id="d", magnitude=None)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/v1/public/showcase-events")

    body = response.json()
    assert body["minimum_magnitude"] == 4.5
    ids = {event["event_id"] for event in body["events"]}
    assert ids == {"b", "c"}


@pytest.mark.asyncio
async def test_the_result_is_capped_and_newest_first() -> None:
    app = showcase_app(public_showcase_minimum_magnitude=4.0, public_showcase_limit=2)
    stream = app.state.settings.official_stream
    for index in range(5):
        await _add_report(app.state.redis, stream, event_id=f"event-{index}", magnitude=5.0)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/v1/public/showcase-events")

    events = response.json()["events"]
    assert len(events) == 2
    # xrevrange entrega lo más reciente primero: el último añadido es el primero.
    assert events[0]["event_id"] == "event-4"
    assert events[1]["event_id"] == "event-3"


@pytest.mark.asyncio
async def test_the_limit_query_param_overrides_the_default() -> None:
    app = showcase_app(public_showcase_minimum_magnitude=4.0, public_showcase_limit=6)
    stream = app.state.settings.official_stream
    for index in range(5):
        await _add_report(app.state.redis, stream, event_id=f"event-{index}", magnitude=5.0)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/v1/public/showcase-events", params={"limit": 2})

    assert len(response.json()["events"]) == 2


@pytest.mark.asyncio
async def test_requests_from_the_same_ip_are_throttled() -> None:
    app = showcase_app(public_showcase_requests_per_minute=2)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        first = await client.get("/v1/public/showcase-events")
        second = await client.get("/v1/public/showcase-events")
        third = await client.get("/v1/public/showcase-events")

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
    assert third.headers["Retry-After"] == "60"


@pytest.mark.asyncio
async def test_only_public_facing_fields_are_exposed() -> None:
    """Nada de identificadores internos ni de campos que no estén ya en el
    ejemplo público de la documentación."""

    app = showcase_app(public_showcase_minimum_magnitude=4.0)
    await _add_report(app.state.redis, app.state.settings.official_stream, event_id="a", magnitude=6.1)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/v1/public/showcase-events")

    event = response.json()["events"][0]
    assert set(event) == {
        "event_id",
        "origin_time",
        "latitude",
        "longitude",
        "magnitude",
        "magnitude_type",
        "depth_km",
        "agency",
        "place",
        "official_url",
    }


@pytest.mark.asyncio
async def test_magnitude_revisions_replace_previous_cards_without_changing_delivery_ids():
    app = showcase_app()
    stream = app.state.settings.official_stream
    await _add_report(app.state.redis, stream, event_id="catalog:emsc:one:m46", magnitude=4.6)
    await _add_report(app.state.redis, stream, event_id="catalog:emsc:two:m51", magnitude=5.1)
    await _add_report(app.state.redis, stream, event_id="catalog:emsc:one:m47", magnitude=4.7)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        events = (await client.get("/v1/public/showcase-events")).json()["events"]
    assert [row["event_id"] for row in events] == ["catalog:emsc:one:m47", "catalog:emsc:two:m51"]
    assert await app.state.redis.xlen(stream) == 3


@pytest.mark.asyncio
async def test_revision_below_threshold_does_not_resurrect_previous_large_magnitude():
    app = showcase_app()
    stream = app.state.settings.official_stream
    await _add_report(app.state.redis, stream, event_id="catalog:emsc:one:m51", magnitude=5.1)
    await _add_report(app.state.redis, stream, event_id="catalog:emsc:one:m20", magnitude=2.0)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/v1/public/showcase-events")).json()["events"] == []


@pytest.mark.asyncio
async def test_damaged_stream_record_does_not_hide_healthy_events():
    app = showcase_app()
    stream = app.state.settings.official_stream
    await _add_report(app.state.redis, stream, event_id="valid", magnitude=5.0)
    for payload in ("{broken", "[]", '{"event_id":"bad","preferred_report":null}'):
        await app.state.redis.xadd(stream, {"payload": payload})
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        events = (await client.get("/v1/public/showcase-events")).json()["events"]
    assert [row["event_id"] for row in events] == ["valid"]


@pytest.mark.asyncio
async def test_recent_events_fill_limit_after_consolidating_revisions():
    app = showcase_app(public_recent_event_limit=2)
    app.dependency_overrides[require_mobile_events_read] = lambda: None
    stream = app.state.settings.official_stream
    for event_id in ("catalog:a:older:m50", "catalog:a:latest:m50", "catalog:a:latest:m51"):
        await _add_report(app.state.redis, stream, event_id=event_id, magnitude=5.0)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        events = (await client.get("/v1/events/recent")).json()["events"]
    assert [row["event_id"] for row in events] == ["catalog:a:latest:m51", "catalog:a:older:m50"]


@pytest.mark.asyncio
async def test_authenticated_edge_visitors_have_independent_showcase_budgets():
    app = showcase_app(public_showcase_requests_per_minute=1)
    app.add_middleware(EdgeOriginGuard, secret="test-edge")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        headers = {"X-Seismik-Origin-Auth": "test-edge", "X-Seismik-Client-IP": "192.0.2.1"}
        assert (await client.get("/v1/public/showcase-events", headers=headers)).status_code == 200
        assert (await client.get("/v1/public/showcase-events", headers=headers)).status_code == 429
        headers["X-Seismik-Client-IP"] = "192.0.2.2"
        assert (await client.get("/v1/public/showcase-events", headers=headers)).status_code == 200


@pytest.mark.asyncio
async def test_untrusted_ip_header_cannot_reset_showcase_budget():
    app = showcase_app(public_showcase_requests_per_minute=1)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/v1/public/showcase-events", headers={"X-Seismik-Client-IP": "192.0.2.1"})).status_code == 200
        assert (await client.get("/v1/public/showcase-events", headers={"X-Seismik-Client-IP": "192.0.2.2"})).status_code == 429
