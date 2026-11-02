"""Deferred ML telemetry only: never contributes triggers or push policy."""
from __future__ import annotations

import heapq
import logging
import threading
import time
from collections import deque
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from obspy import Stream, Trace, UTCDateTime, read_inventory

from eew.alerts import AlertDispatcher
from eew.local_magnitude import LocalMagnitudeCalibration, MagnitudeEstimate
from eew.location import TravelTimeTable
from eew.magnitude_pipeline import MagnitudePipeline, estimate
from eew.models import EarthquakeCandidate, MagnitudeEstimateUpdate, utc_now_iso

STATIONS = frozenset({"ARGC", "CRJC", "HEL", "OCA", "PRV", "RUS", "SMAR", "TUM", "URI"})
LOGGER = logging.getLogger(__name__)


class WaveformBuffer:
    def __init__(self, seconds: float = 600) -> None:
        self.seconds = seconds
        self._packets: dict[str, deque[Trace]] = {}
        self._lock = threading.Lock()

    def add(self, trace: Trace) -> None:
        if trace.stats.network != "CM" or trace.stats.station not in STATIONS:
            return
        if trace.stats.channel not in {"HHZ", "HHN", "HHE"} or trace.stats.npts == 0:
            return
        packet = trace.copy()
        packet.trim(starttime=packet.stats.endtime - self.seconds)
        with self._lock:
            packets = self._packets.setdefault(packet.id, deque(maxlen=4096))
            newest = max(float(packet.stats.endtime), max((float(p.stats.endtime) for p in packets), default=0))
            cutoff = newest - self.seconds
            if float(packet.stats.endtime) < cutoff:
                return
            packets.append(packet)
            self._packets[packet.id] = deque(
                (p for p in packets if float(p.stats.endtime) >= cutoff), maxlen=4096
            )
            for retained in self._packets[packet.id]:
                if float(retained.stats.starttime) < cutoff:
                    retained.trim(starttime=UTCDateTime(cutoff))

    def snapshot(self, start: float, end: float) -> Stream:
        with self._lock:
            stream = Stream([p.copy() for packets in self._packets.values() for p in packets
                             if float(p.stats.endtime) >= start and float(p.stats.starttime) <= end])
        # No interpolation or zero filling: gaps/overlap conflicts remain split.
        stream.merge(method=0, fill_value=None)
        stream = stream.split()
        stream.trim(UTCDateTime(start), UTCDateTime(end))
        return stream


class LiveMagnitudeEstimator:
    def __init__(self, pipeline: MagnitudePipeline, calibration_path: Path,
                 dispatcher: AlertDispatcher, *, delay_seconds: float = 270,
                 clock: Callable[[], float] = time.time) -> None:
        self.pipeline = pipeline
        self.calibration_path = calibration_path
        self.dispatcher = dispatcher
        self.delay = delay_seconds
        self.clock = clock
        self.buffer = WaveformBuffer()
        self._condition = threading.Condition()
        self._pending: list[tuple[float, str, float]] = []
        self._seen: deque[str] = deque(maxlen=2048)
        self._stopped = False
        self._thread = threading.Thread(target=self._run, name="live-ml", daemon=True)

    @classmethod
    def from_files(cls, settings: Any, coordinates: Mapping[str, tuple[float, float]],
                   dispatcher: AlertDispatcher) -> LiveMagnitudeEstimator:
        pipeline = MagnitudePipeline(read_inventory(settings.responses_path),
                                     TravelTimeTable.load(Path(settings.table_path)), coordinates)
        return cls(pipeline, Path(settings.calibration_path), dispatcher)

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        with self._condition:
            self._stopped = True
            self._pending.clear()
            self._condition.notify_all()
        if self._thread.is_alive():
            self._thread.join(timeout=5)

    def schedule(self, candidate: EarthquakeCandidate) -> bool:
        if not candidate.stations or any(s.station_id not in {f"CM.{name}" for name in STATIONS}
                                          for s in candidate.stations):
            return False
        if candidate.event_id.startswith(("drill-", "replay-", "simulation-")):
            return False
        first = min(datetime.fromisoformat(s.trigger_time.replace("Z", "+00:00")).timestamp()
                    for s in candidate.stations)
        now = self.clock()
        # Live candidates only; historical replays cannot schedule publication.
        if not -5 <= now - first <= 60:
            return False
        with self._condition:
            if self._stopped or candidate.event_id in self._seen or len(self._pending) >= 32:
                return False
            self._seen.append(candidate.event_id)
            heapq.heappush(self._pending, (now + self.delay, candidate.event_id, first))
            self._condition.notify_all()
        return True

    def process_due(self) -> int:
        completed = 0
        while True:
            with self._condition:
                if self._stopped or not self._pending or self._pending[0][0] > self.clock():
                    return completed
                _due, event_id, first = heapq.heappop(self._pending)
            try:
                # Reload every time: a new evaluation invalidates old beta authorization.
                measurement = self.pipeline.measure(self.buffer.snapshot(first - 90, first + 270), first)
                calibration = LocalMagnitudeCalibration.load(self.calibration_path)
                result = estimate(measurement, calibration)
                update = MagnitudeEstimateUpdate(f"ml:{event_id}", event_id, utc_now_iso(), own_payload(result))
                with self._condition:
                    if not self._stopped:
                        self.dispatcher.submit(update)
                completed += 1
            except Exception:
                LOGGER.exception("Deferred ML failed candidate=%s", event_id)

    def _run(self) -> None:
        while True:
            with self._condition:
                if self._stopped:
                    return
                wait = max(0.01, self._pending[0][0] - self.clock()) if self._pending else 60
                self._condition.wait(timeout=min(wait, 60))
            self.process_due()


def own_payload(result: MagnitudeEstimate) -> dict[str, Any]:
    payload = result.to_payload()
    return {"value": result.value, "scale": result.scale, "status": result.status,
            "reason": result.reason, "uncertainty": result.uncertainty, "method": result.method,
            "station_count": result.station_count, "stations": payload["magnitude_stations"],
            "calibration_version": result.calibration_version, "validation_status": result.validation_status}
