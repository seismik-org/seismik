from __future__ import annotations

import math
import threading
import time
import uuid
from collections import deque
from collections.abc import Callable

from obspy import UTCDateTime  # type: ignore[import-untyped]

from eew.config import CoincidenceSettings
from eew.magnitude import estimate_preliminary_magnitude
from eew.models import EarthquakeCandidate, StationTrigger, utc_now_iso

# Solo se llena tras calibración retrospectiva y validada con informes oficiales.
VALIDATED_MAGNITUDE_CALIBRATIONS = {}


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
                if (
                    item.packet_lag_seconds is not None
                    and item.packet_lag_seconds > self.settings.max_station_lag_seconds
                ):
                    continue
                latest_by_station[item.station_id] = item
            matches = tuple(sorted(latest_by_station.values(), key=lambda item: item.trigger_time))
            if len(matches) < self.settings.minimum_stations:
                return None

            located = [
                item for item in matches if item.latitude is not None and item.longitude is not None
            ]
            if len(located) < self.settings.minimum_located_stations:
                return None
            if (
                self.settings.minimum_network_aperture_km > 0
                and _network_aperture_km(located) < self.settings.minimum_network_aperture_km
            ):
                return None

            now_monotonic = self._monotonic_clock()
            if now_monotonic - self._last_alert_monotonic < self.settings.alert_cooldown_seconds:
                return None
            self._last_alert_monotonic = now_monotonic

            countries = tuple(sorted({item.country_code for item in matches}))
            wave_strength_index = _wave_strength_index(matches)
            magnitude_estimate = estimate_preliminary_magnitude(
                matches, VALIDATED_MAGNITUDE_CALIBRATIONS.get(trigger.zone_id)
            )
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
                    sum(item.latitude for item in located if item.latitude is not None)
                    / len(located)
                    if located
                    else None
                ),
                estimated_longitude=(
                    sum(item.longitude for item in located if item.longitude is not None)
                    / len(located)
                    if located
                    else None
                ),
                wave_strength_index=wave_strength_index,
                magnitude_estimate=magnitude_estimate,
                magnitude_estimate_status=(
                    "validated_preliminary"
                    if magnitude_estimate is not None
                    else "pending_station_calibration"
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


def _wave_strength_index(stations: tuple[StationTrigger, ...]) -> float | None:
    """Índice reproducible de señal; explícitamente no es una magnitud.

    El cociente señal/ruido reduce el efecto de una estación particularmente
    ruidosa. Sigue dependiendo de la ganancia del instrumento, por lo que
    nunca se usa para alertar ni se etiqueta como M/Mw/ML.
    """

    values: list[float] = []
    for station in stations:
        amplitude = station.peak_amplitude_counts
        noise = station.noise_rms_counts
        if amplitude is None or noise is None or amplitude <= 0 or noise <= 0:
            continue
        values.append(math.log10(amplitude / noise))
    if not values:
        return None
    values.sort()
    midpoint = len(values) // 2
    median = values[midpoint] if len(values) % 2 else (values[midpoint - 1] + values[midpoint]) / 2
    return round(median, 3)


def _network_aperture_km(stations: list[StationTrigger]) -> float:
    maximum = 0.0
    for index, first in enumerate(stations):
        for second in stations[index + 1 :]:
            assert first.latitude is not None and first.longitude is not None
            assert second.latitude is not None and second.longitude is not None
            maximum = max(
                maximum,
                _haversine_km(
                    first.latitude,
                    first.longitude,
                    second.latitude,
                    second.longitude,
                ),
            )
    return maximum


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
