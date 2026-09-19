from __future__ import annotations

from dataclasses import replace
from datetime import datetime

import pytest
import requests

from eew.config import OfficialReportsSettings
from eew.models import EarthquakeCandidate, OfficialReport, StationTrigger
from eew.official import (
    USER_AGENT,
    OfficialApiClient,
    OfficialSource,
    SourceRejected,
    _candidate_query_window,
    match_report,
    source_pause_remaining,
)


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200, headers: dict | None = None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")

    def json(self) -> dict:
        return self._payload


class FakeSession:
    def __init__(self, payload: dict):
        self.payload = payload
        self.headers: dict[str, str] = {}
        self.calls: list[dict] = []

    def get(self, *_args, **kwargs) -> FakeResponse:
        self.calls.append(kwargs)
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


def test_association_boundaries_are_inclusive_and_query_is_bounded() -> None:
    settings = OfficialReportsSettings(
        enabled=False,
        max_origin_time_delta_seconds=120,
        max_distance_km=100,
    )
    at_limit = replace(report(), origin_time="2025-12-31T23:58:30Z")
    beyond_limit = replace(report(), origin_time="2025-12-31T23:58:29.999Z")

    assert match_report(candidate(), at_limit, settings) is not None
    assert match_report(candidate(), beyond_limit, settings) is None
    start, end = _candidate_query_window(candidate(), settings)
    assert start.isoformat() == "2025-12-31T23:58:30+00:00"
    assert end.isoformat() == "2026-01-01T00:02:30+00:00"


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


def test_sgc_rapid_feed_contract_is_normalized() -> None:
    sgc = OfficialSource(
        id="sgc_colombia", agency="SGC", jurisdiction="Colombia", countries=("CO",),
        adapter="sgc_geojson", endpoint="https://example.test",
        official_site="https://www.sgc.gov.co/sismos", priority=100,
    )
    payload = {"features": [{
        "id": "SGC2026pqqmro",
        "geometry": {"coordinates": [-76.291741, 4.9909347, 31.2]},
        "properties": {
            "utcTime": "2026-08-10T12:34:27Z", "mag": 7.4, "magType": "Mw",
            "depth": 31.2, "place": "San Jose del Palmar", "status": "reviewed",
            "updated": "2026-08-10T13:00:00Z",
        },
    }]}
    session = FakeSession(payload)
    rows = OfficialApiClient(sgc, 1, session).fetch(
        datetime(2026, 8, 10), datetime(2026, 8, 11)
    )
    assert rows[0].official_event_id == "SGC2026pqqmro"
    assert rows[0].magnitude == 7.4
    assert rows[0].depth_km == 31.2
    assert rows[0].official_url.endswith("/SGC2026pqqmro/resumen")
    # El SGC filtra en hora de Colombia (UTC-5): en UTC, una ventana de la
    # última hora caía cinco horas en el futuro y llegaba vacía.
    assert session.calls[0]["params"] == {
        "startdate": "2026-08-09T19:00:00",
        "enddate": "2026-08-10T19:00:00",
    }


class RejectingSession(FakeSession):
    """El SGC corta a Cloud Run con un 403; luego respondería normal."""

    def __init__(self, status_code: int = 403, headers: dict | None = None):
        super().__init__({"features": []})
        self.status_code = status_code
        self.rejection_headers = headers

    def get(self, *_args, **kwargs) -> FakeResponse:
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            return FakeResponse({}, self.status_code, self.rejection_headers)
        return FakeResponse(self.payload)


def _sgc() -> OfficialSource:
    return OfficialSource(
        id="sgc_colombia", agency="SGC", jurisdiction="Colombia", countries=("CO",),
        adapter="sgc_geojson", endpoint="https://example.test",
        official_site="https://www.sgc.gov.co/sismos", priority=100,
    )


@pytest.mark.parametrize("status", [403, 429])
def test_a_rejected_source_is_left_alone_instead_of_hammered(status: int) -> None:
    session = RejectingSession(status)
    client = OfficialApiClient(_sgc(), 1, session)

    with pytest.raises(SourceRejected):
        client.fetch(datetime(2026, 9, 18), datetime(2026, 9, 18, 1))
    # Los siguientes intentos no salen a la red mientras dure la pausa: son
    # los que convertían un límite de tráfico en un bloqueo de la IP.
    for _ in range(5):
        with pytest.raises(SourceRejected):
            OfficialApiClient(_sgc(), 1, session).fetch(datetime(2026, 9, 18), datetime(2026, 9, 18, 1))
    assert len(session.calls) == 1
    assert 29 * 60 < source_pause_remaining("sgc_colombia") <= 30 * 60


def test_the_agency_retry_after_sets_the_pause_within_limits() -> None:
    with pytest.raises(SourceRejected):
        OfficialApiClient(_sgc(), 1, RejectingSession(429, {"Retry-After": "120"})).fetch(
            datetime(2026, 9, 18), datetime(2026, 9, 18, 1)
        )
    assert 110 < source_pause_remaining("sgc_colombia") <= 120


def test_an_absurd_retry_after_does_not_silence_a_source_for_days() -> None:
    with pytest.raises(SourceRejected):
        OfficialApiClient(_sgc(), 1, RejectingSession(429, {"Retry-After": "999999"})).fetch(
            datetime(2026, 9, 18), datetime(2026, 9, 18, 1)
        )
    assert source_pause_remaining("sgc_colombia") <= 6 * 3600


def test_one_rejected_agency_does_not_pause_the_others() -> None:
    with pytest.raises(SourceRejected):
        OfficialApiClient(_sgc(), 1, RejectingSession()).fetch(datetime(2026, 9, 18), datetime(2026, 9, 18, 1))
    usgs = replace(_sgc(), id="usgs_global")
    assert source_pause_remaining("usgs_global") == 0
    assert OfficialApiClient(usgs, 1, FakeSession({"features": []})).fetch(
        datetime(2026, 9, 18), datetime(2026, 9, 18, 1)
    ) == []


def test_other_http_errors_are_not_mistaken_for_a_block() -> None:
    session = RejectingSession(503)
    with pytest.raises(requests.HTTPError):
        OfficialApiClient(_sgc(), 1, session).fetch(datetime(2026, 9, 18), datetime(2026, 9, 18, 1))
    assert source_pause_remaining("sgc_colombia") == 0


def test_requests_identify_seismik_with_a_contact_url() -> None:
    session = FakeSession({"features": []})
    OfficialApiClient(_sgc(), 1, session)
    assert session.headers["User-Agent"] == USER_AGENT
    assert "https://seismik.org" in USER_AGENT
