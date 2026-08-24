from __future__ import annotations

import logging
import threading
import time

import numpy as np
from obspy import Trace, UTCDateTime  # type: ignore[import-untyped]
from obspy.signal.trigger import classic_sta_lta  # type: ignore[import-untyped]

from eew.config import DetectionSettings, StationSubscription
from eew.models import StationTrigger, utc_now_iso

LOGGER = logging.getLogger(__name__)


class StationProcessor:
    """Búfer crudo y detector STA/LTA independiente para una estación."""

    def __init__(
        self,
        subscription: StationSubscription,
        settings: DetectionSettings,
        provider_id: str = "test",
        country_code: str = "XX",
        zone_id: str = "XX",
    ):
        self.subscription = subscription
        self.settings = settings
        self.provider_id = provider_id
        self.country_code = country_code
        self.zone_id = zone_id
        self._data = np.empty(0, dtype=np.float64)
        self._sampling_rate: float | None = None
        self._end_time: UTCDateTime | None = None
        self._active = False
        self._last_trigger_monotonic = float("-inf")
        self._lock = threading.Lock()

    def process(self, trace: Trace) -> StationTrigger | None:
        if trace.stats.network != self.subscription.network:
            return None
        if trace.stats.station != self.subscription.station:
            return None
        if trace.stats.channel != self.subscription.channel:
            return None
        if self.subscription.location is not None and trace.stats.location != self.subscription.location:
            return None

        with self._lock:
            new_samples = self._append_raw(trace)
            if new_samples <= 0 or self._sampling_rate is None or self._end_time is None:
                return None

            sampling_rate = self._sampling_rate
            nsta = max(1, round(self.settings.sta_seconds * sampling_rate))
            nlta = max(nsta + 1, round(self.settings.lta_seconds * sampling_rate))
            if self._data.size < nlta + new_samples:
                return None

            processed = Trace(data=self._data.copy())
            processed.stats.sampling_rate = sampling_rate
            processed.detrend("demean")
            processed.detrend("linear")
            if self.settings.filter_enabled:
                self._filter(processed, sampling_rate)

            characteristic = classic_sta_lta(
                np.asarray(processed.data, dtype=np.float64), nsta, nlta
            )
            recent_start = max(nlta, characteristic.size - new_samples)
            recent = characteristic[recent_start:]
            if recent.size == 0:
                return None

            latest_ratio = float(recent[-1])
            if self._active:
                if latest_ratio < self.settings.trigger_off:
                    self._active = False
                    LOGGER.info("Detector rearmado station=%s ratio=%.3f", self.subscription.station_id, latest_ratio)
                return None

            peak_offset = int(np.argmax(recent))
            peak_ratio = float(recent[peak_offset])
            if peak_ratio < self.settings.trigger_on:
                return None

            self._active = True
            now_monotonic = time.monotonic()
            if now_monotonic - self._last_trigger_monotonic < self.settings.station_cooldown_seconds:
                return None
            self._last_trigger_monotonic = now_monotonic

            peak_index = recent_start + peak_offset
            buffer_start = self._end_time - (self._data.size - 1) / sampling_rate
            trigger_time = buffer_start + peak_index / sampling_rate
            station_trigger = StationTrigger(
                provider_id=self.provider_id,
                country_code=self.country_code,
                zone_id=self.zone_id,
                station_id=self.subscription.station_id,
                stream_id=trace.id,
                trigger_time=trigger_time.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                received_at=utc_now_iso(),
                sta_lta_ratio=round(peak_ratio, 4),
                latitude=self.subscription.latitude,
                longitude=self.subscription.longitude,
            )
            LOGGER.warning(
                "Disparo local station=%s stream=%s ratio=%.3f time=%s",
                station_trigger.station_id,
                station_trigger.stream_id,
                station_trigger.sta_lta_ratio,
                station_trigger.trigger_time,
            )
            return station_trigger

    def _append_raw(self, trace: Trace) -> int:
        incoming = np.asarray(trace.data, dtype=np.float64)
        incoming = incoming[np.isfinite(incoming)]
        if incoming.size == 0:
            return 0

        sampling_rate = float(trace.stats.sampling_rate)
        if self._sampling_rate is None or not np.isclose(self._sampling_rate, sampling_rate):
            self._reset(incoming, sampling_rate, trace.stats.endtime)
            return incoming.size

        assert self._end_time is not None
        expected_start = self._end_time + 1.0 / sampling_rate
        offset_samples = int(round(float(trace.stats.starttime - expected_start) * sampling_rate))
        max_gap_samples = round(self.settings.max_interpolated_gap_seconds * sampling_rate)

        if offset_samples > max_gap_samples:
            LOGGER.warning(
                "Hueco grande; reiniciando buffer station=%s gap_samples=%d",
                self.subscription.station_id,
                offset_samples,
            )
            self._reset(incoming, sampling_rate, trace.stats.endtime)
            return incoming.size

        if offset_samples > 0:
            # Solo se interpolan huecos muy pequeños; rellenar huecos largos puede
            # fabricar un transitorio que STA/LTA interpretaría como una onda P.
            gap = np.linspace(self._data[-1], incoming[0], offset_samples + 2)[1:-1]
            incoming = np.concatenate((gap, incoming))
        elif offset_samples < 0:
            overlap = -offset_samples
            if overlap >= incoming.size:
                return 0
            incoming = incoming[overlap:]

        self._data = np.concatenate((self._data, incoming))
        max_samples = max(1, round(self.settings.buffer_seconds * sampling_rate))
        if self._data.size > max_samples:
            self._data = self._data[-max_samples:]
        self._end_time = trace.stats.endtime
        return incoming.size

    def _reset(self, data: np.ndarray, sampling_rate: float, end_time: UTCDateTime) -> None:
        max_samples = max(1, round(self.settings.buffer_seconds * sampling_rate))
        self._data = data[-max_samples:]
        self._sampling_rate = sampling_rate
        self._end_time = end_time
        self._active = False

    def _filter(self, trace: Trace, sampling_rate: float) -> None:
        nyquist_safe = sampling_rate * 0.45
        low = min(self.settings.filter_low_hz, nyquist_safe)
        high = min(self.settings.filter_high_hz, nyquist_safe)
        if high > low:
            trace.filter(
                "bandpass",
                freqmin=low,
                freqmax=high,
                corners=self.settings.filter_corners,
                zerophase=False,
            )
        else:
            trace.filter(
                "highpass",
                freq=low,
                corners=self.settings.filter_corners,
                zerophase=False,
            )
