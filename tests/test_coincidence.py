from eew.coincidence import CoincidenceDetector
from eew.config import CoincidenceSettings
from eew.models import StationTrigger


def trigger(station: str, second: int) -> StationTrigger:
    return StationTrigger(
        provider_id="earthscope_colombia",
        country_code="CO",
        zone_id="northern_andes",
        station_id=f"CX.{station}",
        stream_id=f"CX.{station}..HHZ",
        trigger_time=f"2026-01-01T00:00:{second:02d}.000000Z",
        received_at="2026-01-01T00:00:20Z",
        sta_lta_ratio=5.0,
    )


def test_requires_unique_stations_inside_window() -> None:
    detector = CoincidenceDetector(
        CoincidenceSettings(minimum_stations=3, window_seconds=10, alert_cooldown_seconds=0)
    )
    assert detector.add(trigger("PB01", 1)) is None
    assert detector.add(trigger("PB01", 2)) is None
    assert detector.add(trigger("PB03", 5)) is None
    event = detector.add(trigger("PB07", 9))
    assert event is not None
    assert event.country_code == "CO"
    assert event.country_codes == ("CO",)
    assert event.zone_id == "northern_andes"
    assert event.station_count == 3
    assert {item.station_id for item in event.stations} == {"CX.PB01", "CX.PB03", "CX.PB07"}


def test_discards_old_triggers() -> None:
    detector = CoincidenceDetector(
        CoincidenceSettings(minimum_stations=2, window_seconds=5, alert_cooldown_seconds=0)
    )
    assert detector.add(trigger("PB01", 1)) is None
    assert detector.add(trigger("PB03", 8)) is None


def test_router_combines_countries_only_inside_same_seismic_zone() -> None:
    from dataclasses import replace

    from eew.coincidence import CountryCoincidenceRouter

    router = CountryCoincidenceRouter(
        CoincidenceSettings(minimum_stations=2, window_seconds=10, alert_cooldown_seconds=0)
    )
    assert router.add(trigger("CO1", 1)) is None
    chile = replace(
        trigger("CL1", 2),
        country_code="CL",
        zone_id="northern_chile",
        provider_id="geofon_chile",
    )
    assert router.add(chile) is None
    event = router.add(trigger("CO2", 3))
    assert event is not None
    assert event.country_code == "CO"

    # Ecuador puede asociarse con Colombia si ambos pertenecen a la misma zona.
    router2 = CountryCoincidenceRouter(
        CoincidenceSettings(minimum_stations=2, window_seconds=10, alert_cooldown_seconds=0)
    )
    assert router2.add(trigger("CO3", 4)) is None
    ecuador = replace(trigger("EC1", 5), country_code="EC")
    cross_border = router2.add(ecuador)
    assert cross_border is not None
    assert cross_border.country_code is None
    assert cross_border.country_codes == ("CO", "EC")


def test_stale_station_does_not_count_silently() -> None:
    from dataclasses import replace

    detector = CoincidenceDetector(
        CoincidenceSettings(
            minimum_stations=2,
            window_seconds=10,
            alert_cooldown_seconds=0,
            max_station_lag_seconds=5,
        )
    )
    assert detector.add(replace(trigger("A", 1), packet_lag_seconds=30)) is None
    assert detector.add(replace(trigger("B", 2), packet_lag_seconds=1)) is None
    event = detector.add(replace(trigger("C", 3), packet_lag_seconds=1))
    assert event is not None
    assert {item.station_id for item in event.stations} == {"CX.B", "CX.C"}


def test_requires_minimum_geographic_aperture() -> None:
    from dataclasses import replace

    settings = CoincidenceSettings(
        minimum_stations=2,
        window_seconds=10,
        alert_cooldown_seconds=0,
        minimum_located_stations=2,
        minimum_network_aperture_km=50,
    )
    detector = CoincidenceDetector(settings)
    near_a = replace(trigger("A", 1), latitude=4.65, longitude=-74.05)
    near_b = replace(trigger("B", 2), latitude=4.66, longitude=-74.06)
    assert detector.add(near_a) is None
    assert detector.add(near_b) is None
    far = replace(trigger("C", 3), latitude=6.25, longitude=-75.57)
    event = detector.add(far)
    assert event is not None
    assert event.station_count == 3


def test_candidate_exposes_signal_index_without_claiming_magnitude() -> None:
    from dataclasses import replace

    detector = CoincidenceDetector(
        CoincidenceSettings(minimum_stations=2, window_seconds=10, alert_cooldown_seconds=0)
    )
    assert detector.add(
        replace(trigger("A", 1), peak_amplitude_counts=100.0, noise_rms_counts=10.0)
    ) is None
    event = detector.add(
        replace(trigger("B", 2), peak_amplitude_counts=1000.0, noise_rms_counts=10.0)
    )
    assert event is not None
    assert event.wave_strength_index == 1.5
    assert event.magnitude_estimate is None
    assert event.magnitude_estimate_status == "pending_station_calibration"
