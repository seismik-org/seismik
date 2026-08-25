from __future__ import annotations

from pathlib import Path

import numpy as np
from obspy import Stream, Trace, UTCDateTime

from eew.config import CoincidenceSettings, DetectionSettings, StationSubscription
from eew.replay import MiniSeedReplay


def _write_case(path: Path) -> tuple[StationSubscription, ...]:
    rate = 100.0
    start = UTCDateTime("2026-01-01T00:00:00Z")
    traces = []
    subscriptions = []
    for index, station in enumerate(("ONE", "TWO", "THREE")):
        rng = np.random.default_rng(index)
        data = rng.normal(0, 0.01, 1200)
        data[800:830] += 8
        trace = Trace(data=data.astype(np.float32))
        trace.stats.network = "XX"
        trace.stats.station = station
        trace.stats.location = ""
        trace.stats.channel = "HHZ"
        trace.stats.sampling_rate = rate
        trace.stats.starttime = start
        traces.append(trace)
        subscriptions.append(
            StationSubscription("XX", station, "HHZ", country_code="CO", zone_id="CO")
        )
    Stream(traces).write(path, format="MSEED")
    return tuple(subscriptions)


def test_miniseed_replay_is_deterministic(tmp_path: Path) -> None:
    case_path = tmp_path / "case.mseed"
    subscriptions = _write_case(case_path)
    detection = DetectionSettings(
        buffer_seconds=20,
        sta_seconds=0.2,
        lta_seconds=5,
        trigger_on=3,
        trigger_off=1,
        filter_enabled=False,
    )
    coincidence = CoincidenceSettings(
        minimum_stations=3,
        window_seconds=3,
        alert_cooldown_seconds=0,
    )

    first = MiniSeedReplay(subscriptions, detection, coincidence).run([case_path])
    second = MiniSeedReplay(subscriptions, detection, coincidence).run([case_path])

    assert first == second
    assert len(first["triggers"]) == 3
    assert len(first["candidates"]) == 1
    assert first["candidates"][0]["stations"] == ("XX.ONE", "XX.THREE", "XX.TWO")
