from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from eew.config import OfficialReportsSettings
from eew.models import EarthquakeCandidate, OfficialReport, StationTrigger
from eew.official import OfficialApiClient, OfficialSource, match_report


class FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._payload


class FakeSession:
    def __init__(self, payload: dict):
        self.payload = payload
        self.headers: dict[str, str] = {}

    def get(self, *_args, **_kwargs) -> FakeResponse:
        return FakeResponse(self.payload)


def candidate() -> EarthquakeCandidate:
    stations = (
        StationTrigger(
            provider_id="earthscope",
            country_code="CO",
            zone_id="northern_andes",
            station_id="CM.A",
            stream_id="CM.A.00.HHZ",
            trigger_time="2026-01-01T00:00:30Z",
            received_at="2026-01-01T00:00:31Z",
            sta_lta_ratio=4.2,
            latitude=6.8,
            longitude=-73.1,
        ),
    )
    return EarthquakeCandidate(
        event_id="candidate-1",
        type="earthquake_candidate",
        status="unlocated_unreviewed",
        zone_id="northern_andes",
        country_code="CO",
        country_codes=("CO",),
        detected_at="2026-01-01T00:00:32Z",
        coincidence_window_seconds=15,
        required_stations=1,
        station_count=1,
        stations=stations,
        estimated_latitude=6.8,
        estimated_longitude=-73.1,
    )


def report() -> OfficialReport:
    return OfficialReport(
        source_id="sgc_colombia",
        agency="SGC",
        jurisdiction="Colombia",
        official_event_id="SGC2026abc",
        origin_time="2026-01-01T00:00:10Z",
        updated_at="2026-01-01T00:01:00Z",
        latitude=6.75,
        longitude=-73.05,
        depth_km=140,
        magnitude=4.1,
        magnitude_type="ML",
        place="Los Santos - Santander, Colombia",
        review_status="manual",
        official_url="https://www.sgc.gov.co/detallesismo/SGC2026abc/resumen",
    )


def test_matches_by_time_and_station_centroid_distance() -> None:
    settings = OfficialReportsSettings(
        enabled=False,
        max_origin_time_delta_seconds=120,
        max_distance_km=100,
    )
    matched = match_report(candidate(), report(), settings)
    assert matched is not None
    assert matched.origin_time_delta_seconds == 20
    assert matched.distance_from_station_centroid_km is not None
    assert matched.distance_from_station_centroid_km < 10


def test_rejects_distant_or_temporally_unrelated_report() -> None:
    settings = OfficialReportsSettings(
        enabled=False,
        max_origin_time_delta_seconds=120,
        max_distance_km=100,
    )
    assert match_report(candidate(), replace(report(), latitude=35, longitude=140), settings) is None
    assert match_report(
        candidate(), replace(report(), origin_time="2026-01-01T01:00:00Z"), settings
    ) is None


def test_source_configuration_has_national_priority_and_global_fallback() -> None:
    national = OfficialSource(
        id="sgc",
        agency="SGC",
        jurisdiction="Colombia",
        countries=("CO",),
        adapter="sgc_geojson",
        endpoint="https://api.sgc.gov.co/biweekly/biweekly_earthquakes",
        official_site="https://www.sgc.gov.co/sismos",
        priority=100,
    )
    global_source = OfficialSource(
        id="usgs",
        agency="USGS",
        jurisdiction="Global",
        countries=("US",),
        adapter="fdsn_geojson",
        endpoint="https://earthquake.usgs.gov/fdsnws/event/1/query",
        official_site="https://earthquake.usgs.gov/earthquakes/",
        priority=10,
        global_fallback=True,
    )
    assert national.priority > global_source.priority
    assert global_source.global_fallback


def test_geonet_and_bmkg_contracts_are_normalized() -> None:
    geonet = OfficialSource(
        id="geonet", agency="GeoNet", jurisdiction="NZ", countries=("NZ",),
        adapter="geonet_geojson", endpoint="https://example.test", official_site="https://geonet.org.nz",
        priority=100,
    )
    geonet_payload = {
        "features": [{
            "geometry": {"coordinates": [175.6, -39.5]},
            "properties": {
                "publicID": "2026p1", "time": "2026-01-01T00:00:00Z",
                "depth": 5, "magnitude": 3.2, "mmi": 2, "locality": "Taihape",
            },
        }]
    }
    rows = OfficialApiClient(geonet, 1, FakeSession(geonet_payload)).fetch(
        datetime(2026, 1, 1), datetime(2026, 1, 2)
    )
    assert rows[0].official_event_id == "2026p1"
    assert rows[0].longitude == 175.6

    bmkg = OfficialSource(
        id="bmkg", agency="BMKG", jurisdiction="ID", countries=("ID",),
        adapter="bmkg_json", endpoint="https://example.test", official_site="https://bmkg.go.id",
        priority=100,
    )
    bmkg_payload = {"Infogempa": {"gempa": [{
        "DateTime": "2026-01-01T00:00:00Z", "Coordinates": "-6.2,106.8",
        "Magnitude": "5.1", "Kedalaman": "10 km", "Potensi": "Tidak berpotensi tsunami",
    }]}}
    rows = OfficialApiClient(bmkg, 1, FakeSession(bmkg_payload)).fetch(
        datetime(2026, 1, 1), datetime(2026, 1, 2)
    )
    assert rows[0].depth_km == 10
    assert rows[0].tsunami is False
