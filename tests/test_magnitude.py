from dataclasses import replace

from eew.magnitude import MagnitudeCalibration, estimate_preliminary_magnitude
from eew.models import StationTrigger


def _station(index: int, amplitude: float = 1000.0) -> StationTrigger:
    return StationTrigger(
        provider_id="test",
        country_code="CO",
        zone_id="CO_andes",
        station_id=f"CM.T{index}",
        stream_id=f"CM.T{index}.00.HHZ",
        trigger_time="2026-09-01T00:00:00Z",
        received_at="2026-09-01T00:00:01Z",
        sta_lta_ratio=8.0,
        peak_amplitude_counts=amplitude,
        noise_rms_counts=10.0,
    )


def test_magnitude_never_uses_an_unvalidated_calibration() -> None:
    calibration = MagnitudeCalibration("CO_andes", 1.0, 1.0, 49, 0.1)
    assert estimate_preliminary_magnitude(tuple(_station(i) for i in range(3)), calibration) is None


def test_magnitude_requires_three_station_signal_and_audited_model() -> None:
    calibration = MagnitudeCalibration("CO_andes", 1.0, 1.0, 80, 0.3)
    stations = tuple(_station(i) for i in range(3))
    assert estimate_preliminary_magnitude(stations, calibration) == 3.0
    assert estimate_preliminary_magnitude(stations[:2], calibration) is None
    assert (
        estimate_preliminary_magnitude(
            (replace(stations[0], noise_rms_counts=None),) + stations[1:], calibration
        )
        is None
    )
