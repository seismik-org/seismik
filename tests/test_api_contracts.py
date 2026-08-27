from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError
from test_security_api import candidate_payload

from api.app import create_app
from api.config import AppSettings
from api.schemas import EarthquakeCandidate, OfficialReportUpdate


def official_payload() -> dict:
    report = {
        "source_id": "sgc_colombia",
        "agency": "SGC",
        "jurisdiction": "Colombia",
        "official_event_id": "SGC2026abc",
        "origin_time": "2026-01-01T00:00:10Z",
        "latitude": 6.8,
        "longitude": -73.1,
        "depth_km": 140,
        "magnitude": 4.1,
        "official_url": "https://www.sgc.gov.co/sismos",
    }
    return {
        "event_id": "official-123",
        "candidate_event_id": "candidate-123",
        "type": "official_report_update",
        "status": "official_report_available",
        "matched_at": "2026-01-01T00:01:00Z",
        "preferred_report": report,
        "reports": [report],
    }


def test_candidate_contract_rejects_duplicate_stations_and_naive_time() -> None:
    duplicate = candidate_payload()
    duplicate["stations"][1]["station_id"] = duplicate["stations"][0]["station_id"]
    with pytest.raises(ValidationError, match="stations must be unique"):
        EarthquakeCandidate.model_validate(duplicate)

    naive = candidate_payload()
    naive["detected_at"] = "2026-01-01T00:00:12"
    with pytest.raises(ValidationError):
        EarthquakeCandidate.model_validate(naive)


def test_official_contract_requires_preferred_report_in_report_set() -> None:
    payload = official_payload()
    payload["preferred_report"] = {
        **deepcopy(payload["preferred_report"]),
        "official_event_id": "different",
    }
    with pytest.raises(ValidationError, match="preferred_report must be included"):
        OfficialReportUpdate.model_validate(payload)


def test_openapi_exposes_versioned_strict_event_contracts() -> None:
    schema = create_app(AppSettings()).openapi()
    assert schema["info"]["title"] == "Seismik Platform API"
    candidate = schema["paths"]["/v1/events/candidate"]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"]
    official = schema["paths"]["/v1/events/official-update"]["post"]["requestBody"][
        "content"
    ]["application/json"]["schema"]
    assert candidate["additionalProperties"] is False
    assert official["additionalProperties"] is False
    assert "/v1/events/candidate" in schema["paths"]
    assert "/v1/events/official-update" in schema["paths"]
