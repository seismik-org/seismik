from __future__ import annotations

import math
from dataclasses import replace

from eew.magnitude_shadow import fit_shadow_model, observation_for_match
from eew.models import EarthquakeCandidate, OfficialReport, StationTrigger


def _candidate() -> EarthquakeCandidate:
    stations = tuple(
        StationTrigger(
            provider_id="test",
            country_code="CO",
            zone_id="northern_andes",
            station_id=f"CM.T{index}",
            stream_id=f"CM.T{index}.00.HHZ",
            trigger_time="2026-09-14T20:00:00Z",
            received_at="2026-09-14T20:00:01Z",
            sta_lta_ratio=5.0,
            peak_amplitude_counts=1000.0 * (index + 1),
            noise_rms_counts=10.0,
            latitude=4.5 + index / 10,
            longitude=-76.7 - index / 10,
        )
        for index in range(3)
    )
    return EarthquakeCandidate(
        event_id="candidate-1",
        type="earthquake_candidate",
        status="unlocated_unreviewed",
        zone_id="northern_andes",
        country_code="CO",
        country_codes=("CO",),
        detected_at="2026-09-14T20:00:02Z",
        coincidence_window_seconds=10,
        required_stations=3,
        station_count=3,
        stations=stations,
    )


def _report(magnitude: float = 4.9) -> OfficialReport:
    return OfficialReport(
        source_id="sgc_colombia",
        agency="SGC",
        jurisdiction="CO",
        official_event_id="SGC2026test",
        origin_time="2026-09-14T20:00:00Z",
        updated_at=None,
        latitude=4.55,
        longitude=-76.75,
        depth_km=39,
        magnitude=magnitude,
        magnitude_type="Ml",
        place="Istmina",
        review_status="reported",
        official_url="https://example.test/event",
    )


def test_shadow_observation_records_official_match_but_never_an_estimate() -> None:
    observation = observation_for_match(_candidate(), _report())
    assert observation is not None
    assert observation["mode"] == "shadow_calibration_only"
    assert observation["official_magnitude"] == 4.9
    assert observation["station_count_with_geometry"] == 3
    assert "estimated_magnitude" not in observation


def test_shadow_fit_requires_fifty_official_associations_and_validates_holdout() -> None:
    prototype = {
        "zone_id": "northern_andes",
        "median_log10_snr": 1.0,
        "median_hypocentral_distance_km": 10.0,
        "official_magnitude": 3.0,
        "candidate_event_id": "0",
    }
    assert fit_shadow_model([prototype] * 49) is None
    observations = []
    for index in range(60):
        signal = 0.5 + index / 40
        distance = 10 + index * 2
        magnitude = 1.2 + 1.5 * signal + 0.4 * math.log10(distance)
        observations.append(
            {
                **prototype,
                "median_log10_snr": signal,
                "median_hypocentral_distance_km": distance,
                "official_magnitude": magnitude,
                "candidate_event_id": str(index),
            }
        )
    fit = fit_shadow_model(observations)
    assert fit is not None
    assert fit.sample_count == 60
    assert fit.validation_count == 12
    assert fit.validation_mae < 0.001
    assert fit.is_ready_for_review


def test_shadow_observation_needs_an_official_magnitude_and_three_stations() -> None:
    assert observation_for_match(_candidate(), replace(_report(), magnitude=None)) is None
    short = replace(_candidate(), stations=_candidate().stations[:2], station_count=2)
    assert observation_for_match(short, _report()) is None
