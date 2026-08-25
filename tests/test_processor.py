import numpy as np
from obspy import Trace, UTCDateTime

from eew.config import DetectionSettings, StationSubscription
from eew.processor import StationProcessor


def make_trace(data: np.ndarray, start: UTCDateTime, sampling_rate: float = 100.0) -> Trace:
    trace = Trace(data=np.asarray(data, dtype=np.float64))
    trace.stats.network = "XX"
    trace.stats.station = "TEST"
    trace.stats.location = ""
    trace.stats.channel = "HHZ"
    trace.stats.starttime = start
    trace.stats.sampling_rate = sampling_rate
    return trace


def test_detects_impulsive_amplitude_change() -> None:
    rng = np.random.default_rng(42)
    settings = DetectionSettings(
        buffer_seconds=30,
        sta_seconds=0.2,
        lta_seconds=5,
        trigger_on=3.0,
        trigger_off=1.0,
        station_cooldown_seconds=0,
        filter_enabled=False,
    )
    processor = StationProcessor(StationSubscription("XX", "TEST", "HHZ"), settings)
    start = UTCDateTime("2026-01-01T00:00:00Z")
    warmup = make_trace(rng.normal(0, 0.02, 1000), start)
    assert processor.process(warmup) is None

    burst = np.concatenate((rng.normal(0, 0.02, 20), np.ones(30) * 8, np.zeros(50)))
    event = processor.process(make_trace(burst, warmup.stats.endtime + 0.01))
    assert event is not None
    assert event.station_id == "XX.TEST"
    assert event.sta_lta_ratio >= 3.0


def test_large_gap_resets_buffer_without_trigger() -> None:
    settings = DetectionSettings(
        buffer_seconds=30,
        sta_seconds=0.2,
        lta_seconds=5,
        trigger_on=3,
        trigger_off=1,
        filter_enabled=False,
        max_interpolated_gap_seconds=0.1,
    )
    processor = StationProcessor(StationSubscription("XX", "TEST", "HHZ"), settings)
    start = UTCDateTime("2026-01-01T00:00:00Z")
    assert processor.process(make_trace(np.zeros(1000), start)) is None
    assert processor.process(make_trace(np.ones(100), start + 20)) is None
    assert processor.stats.reset_count == 1
    assert processor.stats.last_reset_reason == "large_gap"


def test_small_gap_is_interpolated_and_audited() -> None:
    settings = DetectionSettings(
        buffer_seconds=30,
        sta_seconds=0.2,
        lta_seconds=5,
        trigger_on=3,
        trigger_off=1,
        filter_enabled=False,
        max_interpolated_gap_seconds=0.05,
    )
    processor = StationProcessor(StationSubscription("XX", "TEST", "HHZ"), settings)
    start = UTCDateTime("2026-01-01T00:00:00Z")
    first = make_trace(np.zeros(600), start)
    assert processor.process(first) is None
    second_start = first.stats.endtime + 0.03
    assert processor.process(make_trace(np.zeros(100), second_start)) is None
    assert processor.stats.interpolated_gap_samples == 2
    assert processor.stats.reset_count == 0


def test_non_finite_samples_do_not_compress_timeline() -> None:
    settings = DetectionSettings(
        buffer_seconds=30,
        sta_seconds=0.2,
        lta_seconds=5,
        trigger_on=3,
        trigger_off=1,
        filter_enabled=False,
        max_interpolated_gap_seconds=0.01,
    )
    processor = StationProcessor(StationSubscription("XX", "TEST", "HHZ"), settings)
    start = UTCDateTime("2026-01-01T00:00:00Z")
    contaminated = np.concatenate((np.zeros(300), np.full(5, np.nan), np.zeros(300)))
    assert processor.process(make_trace(np.zeros(600), start)) is None
    assert processor.process(make_trace(contaminated, start + 6)) is None
    stats = processor.stats
    assert stats.non_finite_samples == 5
    assert stats.reset_count == 1
    assert stats.last_reset_reason == "non_finite_run"
