from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from collections.abc import Callable

from obspy import UTCDateTime  # type: ignore[import-untyped]

from eew.config import CoincidenceSettings
from eew.models import EarthquakeCandidate, StationTrigger, utc_now_iso


class CoincidenceDetector:
    """Confirma un candidato cuando N estaciones disparan dentro de una ventana."""

    def __init__(
        self,
        settings: CoincidenceSettings,
        monotonic_clock: Callable[[], float] = time.monotonic,
    ):
        self.settings = settings
        self._monotonic_clock = monotonic_clock
        self._triggers: deque[StationTrigger] = deque()
        self._last_alert_monotonic = float("-inf")
        self._lock = threading.Lock()

    def add(self, trigger: StationTrigger) -> EarthquakeCandidate | None:
        with self._lock:
            if self._triggers and any(item.zone_id != trigger.zone_id for item in self._triggers):
                raise ValueError("CoincidenceDetector no debe mezclar zonas")
            current_time = UTCDateTime(trigger.trigger_time)
            window = self.settings.window_seconds
            self._triggers.append(trigger)
            self._triggers = deque(
                item
                for item in self._triggers
                if abs(float(UTCDateTime(item.trigger_time) - current_time)) <= window
            )

            # Un canal o paquete repetido nunca cuenta dos veces como dos estaciones.
            latest_by_station: dict[str, StationTrigger] = {}
            for item in self._triggers:
                latest_by_station[item.station_id] = item
            matches = tuple(
                sorted(latest_by_station.values(), key=lambda item: item.trigger_time)
            )
            if len(matches) < self.settings.minimum_stations:
                return None

            now_monotonic = self._monotonic_clock()
            if now_monotonic - self._last_alert_monotonic < self.settings.alert_cooldown_seconds:
                return None
            self._last_alert_monotonic = now_monotonic

            countries = tuple(sorted({item.country_code for item in matches}))
            located = [
                item for item in matches
                if item.latitude is not None and item.longitude is not None
            ]
            return EarthquakeCandidate(
                event_id=str(uuid.uuid4()),
                type="earthquake_candidate",
                status="unlocated_unreviewed",
                zone_id=trigger.zone_id,
                country_code=countries[0] if len(countries) == 1 else None,
                country_codes=countries,
                detected_at=utc_now_iso(),
                coincidence_window_seconds=window,
                required_stations=self.settings.minimum_stations,
                station_count=len(matches),
                stations=matches,
                # Es el centroide de las estaciones disparadas, no un hipocentro.
                # Solo sirve como pista espacial para asociar el informe oficial.
                estimated_latitude=(
                    sum(item.latitude for item in located if item.latitude is not None) / len(located)
                    if located else None
                ),
                estimated_longitude=(
                    sum(item.longitude for item in located if item.longitude is not None) / len(located)
                    if located else None
                ),
            )


class ZoneCoincidenceRouter:
    """Mantiene ventanas independientes por zona sísmica, incluso transfronteriza."""

    def __init__(
        self,
        settings: CoincidenceSettings,
        monotonic_clock: Callable[[], float] = time.monotonic,
    ):
        self.settings = settings
        self._monotonic_clock = monotonic_clock
        self._detectors: dict[str, CoincidenceDetector] = {}
        self._lock = threading.Lock()

    def add(self, trigger: StationTrigger) -> EarthquakeCandidate | None:
        with self._lock:
            detector = self._detectors.setdefault(
                trigger.zone_id, CoincidenceDetector(self.settings, self._monotonic_clock)
            )
        return detector.add(trigger)


# Alias compatible con configuraciones/imports de la versión multi-país anterior.
CountryCoincidenceRouter = ZoneCoincidenceRouter
