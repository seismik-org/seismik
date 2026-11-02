"""Bounded asynchronous association: never block the SeedLink reader on a grid."""
from __future__ import annotations

import logging
import queue
import threading
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import replace

from obspy import UTCDateTime  # type: ignore[import-untyped]

from eew.models import EarthquakeCandidate, StationTrigger, utc_now_iso
from eew.phase_association import AssociationQuality, PhaseAssociator, _distance, eligible_onsets

LOGGER = logging.getLogger(__name__)


class CandidateQualityWorker:
    def __init__(self, associator: PhaseAssociator,
                 publish: Callable[[EarthquakeCandidate], object],
                 on_regional_candidate: Callable[[EarthquakeCandidate], object] | None = None):
        self.associator = associator
        self.publish = publish
        self.on_regional_candidate = on_regional_candidate
        self._recent: deque[StationTrigger] = deque(maxlen=256)
        self._queue: queue.Queue[tuple[EarthquakeCandidate | None, tuple[StationTrigger, ...]]] = queue.Queue(8)
        self._regional_pending = False
        self._regional_events: deque[AssociationQuality] = deque(maxlen=32)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="phase-association", daemon=True)

    def observe(self, trigger: StationTrigger) -> None:
        if self._stop.is_set():
            return
        with self._lock:
            self._recent.append(trigger)
            latest = float(UTCDateTime(trigger.trigger_time))
            observations = tuple(s for s in self._recent if s.zone_id == trigger.zone_id
                                 and 0 <= latest - float(UTCDateTime(s.trigger_time)) <= 120)
            if (trigger.country_code != "CO" or trigger.p_onset_time is None
                    or self._regional_pending
                    or len({s.station_id for s in observations if s.p_onset_time}) < 4):
                return
            # This path does not depend on three STA/LTA peaks fitting 10 s.
            # A fourth or later arrival can initiate its own physical fit.
            try:
                self._queue.put_nowait((None, observations))
                self._regional_pending = True
            except queue.Full:
                LOGGER.warning("regional_phase_observation_queue_full")

    def submit(self, candidate: EarthquakeCandidate) -> None:
        # Preserve personal diagnostic delivery, even if the bounded worker is full.
        with self._lock:
            latest = max(float(UTCDateTime(s.trigger_time)) for s in candidate.stations)
            stations = tuple(s for s in self._recent if s.zone_id == candidate.zone_id
                             and 0 <= latest - float(UTCDateTime(s.trigger_time)) <= 120)
        try:
            self._queue.put_nowait((candidate, stations))
        except queue.Full:
            self.publish(replace(candidate, association_quality=AssociationQuality(
                "insufficient_data", "association_queue_full"
            ).to_dict()))

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=5)

    def process_one(self) -> bool:
        try:
            candidate, stations = self._queue.get_nowait()
        except queue.Empty:
            return False
        try:
            try:
                quality = self.associator.assess(stations)
                anchors = {s.station_id for s in candidate.stations} if candidate else set()
                if candidate and quality.status == "experimental_consistent" and len(
                    anchors.intersection(quality.used_station_ids)
                ) < min(3, candidate.required_stations):
                    quality = replace(quality, status="incoherent",
                                      reason="solution_does_not_explain_candidate_stations")
            except Exception:
                LOGGER.exception("phase_association_failed event_id=%s",
                                 candidate.event_id if candidate else "regional_observation")
                quality = AssociationQuality("insufficient_data", "association_calculation_failed")
            if candidate is None:
                self._publish_regional(quality, stations)
                return True
            LOGGER.info("phase_association event_id=%s quality=%s", candidate.event_id, quality.to_dict())
            # Estimated coordinates remain explicitly the legacy station centroid.
            # Hypocenter hypotheses live separately; never silently substitute one.
            self.publish(replace(candidate, association_quality=quality.to_dict()))
        finally:
            if candidate is None:
                with self._lock:
                    self._regional_pending = False
            self._queue.task_done()
        return True

    def _publish_regional(self, quality: AssociationQuality,
                          stations: tuple[StationTrigger, ...]) -> None:
        if quality.status != "experimental_consistent":
            LOGGER.info("regional_phase_observation quality=%s", quality.to_dict())
            return
        assert quality.origin_time is not None
        assert quality.latitude is not None and quality.longitude is not None
        for previous in self._regional_events:
            assert previous.origin_time is not None
            if abs(float(UTCDateTime(quality.origin_time) - UTCDateTime(previous.origin_time))) <= 10:
                distance = float(_distance(quality.latitude, quality.longitude,
                                          previous.latitude, previous.longitude)) * 111.195
                if distance <= 80:
                    return
        latest_by_station = eligible_onsets(stations)
        used = tuple(latest_by_station[s] for s in quality.used_station_ids)
        event = EarthquakeCandidate(
            event_id=str(uuid.uuid4()), type="earthquake_candidate", status="unlocated_unreviewed",
            zone_id=used[0].zone_id, country_code="CO", country_codes=("CO",),
            detected_at=utc_now_iso(), coincidence_window_seconds=120., required_stations=4,
            station_count=len(used), stations=used,
            # Keep legacy field semantics. Location hypothesis is separate.
            estimated_latitude=sum(s.latitude for s in used if s.latitude is not None) / len(used),
            estimated_longitude=sum(s.longitude for s in used if s.longitude is not None) / len(used),
            association_quality=quality.to_dict(),
        )
        self.publish(event)
        self._regional_events.append(quality)
        if self.on_regional_candidate is not None:
            self.on_regional_candidate(event)
        LOGGER.info("regional_phase_candidate event_id=%s quality=%s", event.event_id, quality.to_dict())

    def _run(self) -> None:
        while not self._stop.wait(0.05):
            try:
                self.process_one()
            except Exception:
                LOGGER.exception("candidate_quality_publication_failed")
