"""Salida GeoJSON de los endpoints de datos y códigos de error estables."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from fakeredis.aioredis import FakeRedis
from fastapi import FastAPI, HTTPException

from api import history
from api.config import AppSettings
from api.dependencies import (
    UNLIMITED_PRINCIPAL,
    get_app_settings,
    get_redis,
    require_mobile_events_read,
    require_mobile_stations_read,
)
from api.errors import GENERIC, KNOWN, error_code
from api.errors import install as install_error_codes
from api.geojson import GEOJSON_MEDIA_TYPE, _point, feature_collection
from api.public import router

DOCS = Path("web/developers.html")


def app_with(**overrides: object) -> FastAPI:
    app = FastAPI()
    app.state.redis = FakeRedis(decode_responses=True)
    app.state.settings = AppSettings(**overrides)
    install_error_codes(app)
    app.include_router(router)
    app.include_router(history.router)
    settings, redis = app.state.settings, app.state.redis
    app.dependency_overrides[get_app_settings] = lambda: settings
    app.dependency_overrides[get_redis] = lambda: redis
    app.dependency_overrides[require_mobile_events_read] = lambda: UNLIMITED_PRINCIPAL
    app.dependency_overrides[require_mobile_stations_read] = lambda: UNLIMITED_PRINCIPAL
    return app


def client_for(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def add_report(
    app: FastAPI, event_id: str, *, latitude: Any = 6.7, longitude: Any = -73.1, magnitude: float = 5.1
) -> None:
    event = {
        "event_id": event_id,
        "preferred_report": {
            "origin_time": "2026-09-20T01:12:47Z", "latitude": latitude, "longitude": longitude,
            "magnitude": magnitude, "magnitude_type": "Mw", "depth_km": 142.0, "agency": "SGC",
            "place": "Los Santos, Santander", "official_url": "https://example.org/report",
        },
    }
    await app.state.redis.xadd(app.state.settings.official_stream, {"payload": json.dumps(event)})


# --- GeoJSON ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_showcase_as_geojson_is_a_valid_feature_collection() -> None:
    app = app_with()
    await add_report(app, "ev-1")
    async with client_for(app) as client:
        response = await client.get("/v1/public/showcase-events", params={"format": "geojson"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(GEOJSON_MEDIA_TYPE)
    body = response.json()
    assert body["type"] == "FeatureCollection" and len(body["features"]) == 1
    event = body["features"][0]
    assert event["type"] == "Feature" and event["id"] == "ev-1"
    assert event["geometry"] == {"type": "Point", "coordinates": [-73.1, 6.7]}, "RFC 7946: [longitud, latitud]"
    assert event["properties"]["magnitude"] == 5.1 and event["properties"]["depth_km"] == 142.0
    assert "latitude" not in event["properties"] and "longitude" not in event["properties"]
    assert body["metadata"] == {"minimum_magnitude": 4.5}


@pytest.mark.asyncio
async def test_json_stays_the_default_and_matches_the_geojson_content() -> None:
    app = app_with()
    await add_report(app, "ev-1")
    async with client_for(app) as client:
        plain = await client.get("/v1/public/showcase-events")
        explicit = await client.get("/v1/public/showcase-events", params={"format": "json"})
        geo = await client.get("/v1/public/showcase-events", params={"format": "geojson"})

    assert plain.headers["content-type"].startswith("application/json")
    assert plain.json() == explicit.json()
    original = plain.json()["events"][0]
    properties = geo.json()["features"][0]["properties"]
    assert {**properties, "latitude": 6.7, "longitude": -73.1} == original, "GeoJSON no pierde ni cambia ningún campo"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("latitude", "longitude"), [(None, None), (95.0, 10.0), (10.0, 200.0), ("6.7", "-73.1"), (True, False)]
)
async def test_an_event_without_valid_coordinates_keeps_a_null_geometry(latitude: Any, longitude: Any) -> None:
    app = app_with()
    await add_report(app, "sin-sitio", latitude=latitude, longitude=longitude)
    async with client_for(app) as client:
        response = await client.get("/v1/public/showcase-events", params={"format": "geojson"})

    feature = response.json()["features"][0]
    assert feature["geometry"] is None and feature["id"] == "sin-sitio", "el evento no se descarta: RFC 7946 permite geometry null"


@pytest.mark.asyncio
async def test_an_unknown_format_is_rejected_with_a_stable_code() -> None:
    app = app_with()
    async with client_for(app) as client:
        response = await client.get("/v1/public/showcase-events", params={"format": "kml"})

    assert response.status_code == 422 and response.json()["code"] == "invalid_parameter"
    assert isinstance(response.json()["detail"], list), "`detail` conserva el formato de siempre"


@pytest.mark.asyncio
async def test_recent_events_and_stations_support_geojson() -> None:
    app = app_with(station_catalog_path="config.json")
    await add_report(app, "ev-2", magnitude=3.0)
    async with client_for(app) as client:
        recent = await client.get("/v1/events/recent", params={"format": "geojson"})
        stations = await client.get("/v1/network/stations", params={"format": "geojson"})
        stations_json = await client.get("/v1/network/stations")

    assert recent.json()["features"][0]["id"] == "ev-2"
    assert recent.headers["content-type"].startswith(GEOJSON_MEDIA_TYPE)
    features = stations.json()["features"]
    assert len(features) == len(stations_json.json()["stations"]) > 5
    first = features[0]
    assert first["geometry"]["type"] == "Point" and len(first["geometry"]["coordinates"]) == 2
    assert {"station_id", "network", "provider_id"} <= set(first["properties"])
    assert first["id"] == first["properties"]["station_id"]


@pytest.mark.asyncio
async def test_history_as_geojson_carries_sources_and_partial_errors_in_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fetch(source: Any, start: Any, end: Any, timeout_seconds: Any) -> list[dict[str, Any]]:
        if source.id == "usgs_global":
            raise TimeoutError
        return [{
            "event_id": f"{source.id}:1", "origin_time": "2026-08-29T12:00:00+00:00", "latitude": 4.6,
            "longitude": -74.0, "magnitude": 4.2, "depth_km": 10.0, "place": "Zona de prueba", "source_id": source.id,
        }]

    monkeypatch.setattr(history, "_fetch_source", fetch)
    app = app_with(official_sources_path="official_sources.json")
    async with client_for(app) as client:
        response = await client.get(
            "/v1/events/history", params={"format": "geojson", "sources": "sgc_colombia,usgs_global"}
        )

    body = response.json()
    assert response.status_code == 200 and body["type"] == "FeatureCollection"
    assert [item["id"] for item in body["features"]] == ["sgc_colombia:1"]
    assert body["metadata"]["errors"] == [{"source_id": "usgs_global", "message": "TimeoutError"}]
    assert body["metadata"]["cached"] is False
    assert {item["source_id"] for item in body["metadata"]["sources"]} == {"sgc_colombia", "usgs_global"}
    assert "events" not in body["metadata"]


def test_the_collection_builder_ignores_blank_identifiers() -> None:
    response = feature_collection([{"event_id": "", "latitude": 1.0, "longitude": 2.0}], id_field="event_id")
    body = json.loads(bytes(response.body))

    assert "id" not in body["features"][0] and body["features"][0]["geometry"]["coordinates"] == [2.0, 1.0]


# --- códigos de error ------------------------------------------------------------------------------------


@pytest.mark.parametrize("latitude,longitude", [(float("nan"), 0), (0, float("inf")), (-90, -180), (90, 180)])
def test_coordinate_boundaries_and_non_finite_values(latitude: float, longitude: float) -> None:
    import math

    point = _point(latitude, longitude)
    if not (math.isfinite(latitude) and math.isfinite(longitude)):
        assert point is None
    else:
        assert point == {"type": "Point", "coordinates": [longitude, latitude]}


@pytest.mark.asyncio
async def test_geojson_does_not_bypass_authentication() -> None:
    app = app_with()
    app.dependency_overrides.pop(require_mobile_events_read)
    app.dependency_overrides.pop(require_mobile_stations_read)
    async with client_for(app) as client:
        for path in ("/v1/events/recent", "/v1/events/history", "/v1/network/stations"):
            response = await client.get(path, params={"format": "geojson"})
            assert response.status_code == 401
            assert response.headers["content-type"].startswith("application/json")


@pytest.mark.parametrize(
    ("status", "detail", "code"),
    [
        (401, "Missing or invalid Seismik API key", "api_key_missing_or_invalid"),
        (401, "Invalid Seismik API key", "api_key_invalid"),
        (403, "API key scope is insufficient", "scope_insufficient"),
        (429, "Per-minute API quota exceeded", "rate_limit_minute"),
        (429, "Daily API quota exceeded", "quota_daily"),
        (429, "Monthly API quota exceeded", "quota_monthly"),
        (503, "Station catalog is unavailable", "station_catalog_unavailable"),
        (404, "Not Found", "not_found"),
        (418, "otro", "client_error"),
        (507, "otro", "server_error"),
        (409, {"campo": 1}, "conflict"),
    ],
)
def test_known_messages_map_to_stable_codes_and_unknown_ones_fall_back_to_their_status(
    status: int, detail: Any, code: str
) -> None:
    assert error_code(status, detail) == code


@pytest.mark.asyncio
async def test_error_bodies_add_a_code_and_keep_detail_and_headers() -> None:
    app = FastAPI()
    install_error_codes(app)

    @app.get("/cuota")
    async def quota() -> None:
        raise HTTPException(status_code=429, detail="Daily API quota exceeded", headers={"Retry-After": "86400"})

    async with client_for(app) as client:
        limited = await client.get("/cuota")
        missing = await client.get("/no-existe")

    assert limited.status_code == 429 and limited.headers["retry-after"] == "86400"
    assert limited.json() == {"detail": "Daily API quota exceeded", "code": "quota_daily"}
    assert missing.status_code == 404 and missing.json() == {"detail": "Not Found", "code": "not_found"}


@pytest.mark.asyncio
async def test_the_free_endpoint_distinguishes_its_ip_limit_by_code() -> None:
    app = app_with(public_showcase_requests_per_minute=1)
    async with client_for(app) as client:
        await client.get("/v1/public/showcase-events")
        limited = await client.get("/v1/public/showcase-events")

    assert limited.status_code == 429 and limited.json()["code"] == "rate_limit_ip"
    assert limited.headers["retry-after"] == "60"


@pytest.mark.asyncio
async def test_the_real_app_installs_the_error_codes() -> None:
    from api.app import create_app

    async with client_for(create_app(AppSettings())) as client:
        response = await client.get("/v1/ruta/que/no/existe")

    assert response.status_code == 404 and response.json()["code"] == "not_found"


# --- documentación ---------------------------------------------------------------------------------------


def test_the_developer_docs_list_every_code_the_api_can_return() -> None:
    page = DOCS.read_text(encoding="utf-8")
    published = set(KNOWN.values()) | {GENERIC[status] for status in (400, 401, 403, 404, 422, 429, 500, 503, 504)}

    missing = sorted(code for code in published if f"<code>{code}</code>" not in page)

    assert not missing, f"códigos sin documentar en web/developers.html: {missing}"


def test_the_developer_docs_describe_geojson_and_the_format_parameter() -> None:
    page = DOCS.read_text(encoding="utf-8")

    for needle in ("format=geojson", "application/geo+json", "FeatureCollection", "RFC 7946"):
        assert needle in page, needle
    assert page.count("<code>format</code>") >= 4, "el parámetro `format` figura en cada endpoint que lo admite"
