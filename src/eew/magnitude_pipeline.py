"""Canal completo de magnitud propia: picks P -> hipocentro -> ML en horizontales.

Se separa la *medición* (costosa, determinista, una vez por evento) de la
*estimación* (aplicar una calibración y las compuertas). Así la evaluación puede
ajustar y validar calibraciones sin recalcular ondas, y producción comparte
exactamente el mismo código que la evaluación.

Entradas que NO se usan nunca: coordenadas o magnitudes de informes oficiales,
ni el centroide de las estaciones disparadas. El único dato del detector es el
instante del primer disparo, que acota dónde buscar la P.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np
from obspy import Inventory, Stream  # type: ignore[import-untyped]

from eew.local_magnitude import (
    METHOD_DESCRIPTION,
    ChannelAmplitude,
    LocalMagnitudeCalibration,
    MagnitudeEstimate,
    StationMagnitude,
    station_amplitude,
    unavailable,
    wood_anderson_amplitudes,
)
from eew.location import (
    KM_PER_DEGREE,
    Hypocenter,
    StationPick,
    TravelTimeTable,
    haversine_deg,
    locate_hypocenter,
)
from eew.picking import PickSettings, pick_p_onset

VERTICAL_CODE = "HHZ"
HORIZONTAL_CODES = ("HHN", "HHE")


@dataclass(frozen=True)
class QualityGates:
    """Compuertas de la ubicación y de las medidas; se fijan con datos de entrenamiento."""

    minimum_location_picks: int = 5
    maximum_rms_seconds: float = 1.5
    maximum_gap_deg: float = 270.0
    maximum_horizontal_uncertainty_km: float = 80.0
    minimum_snr: float = 3.0
    pick_search_before_seconds: float = 30.0
    pick_search_after_seconds: float = 110.0
    noise_seconds: float = 30.0
    lg_velocity_km_s: float = 3.0
    coda_seconds: float = 25.0


@dataclass(frozen=True)
class StationMeasurement:
    station_id: str
    hypocentral_km: float
    channels: tuple[ChannelAmplitude, ...]
    amplitude_mean_mm: float
    amplitude_max_mm: float
    snr: float
    saturated: bool


@dataclass(frozen=True)
class Measurement:
    first_trigger_time: float
    picks: tuple[StationPick, ...]
    hypocenter: Hypocenter | None
    stations: tuple[StationMeasurement, ...]
    notes: tuple[str, ...] = field(default_factory=tuple)


class MagnitudePipeline:
    def __init__(
        self,
        inventory: Inventory,
        table: TravelTimeTable,
        station_coordinates: Mapping[str, tuple[float, float]],
        *,
        gates: QualityGates = QualityGates(),
        pick_settings: PickSettings = PickSettings(),
    ) -> None:
        self.inventory = inventory
        self.table = table
        self.coordinates = dict(station_coordinates)
        self.gates = gates
        self.pick_settings = pick_settings

    def measure(self, stream: Stream, first_trigger_time: float) -> Measurement:
        notes: list[str] = []
        picks: list[StationPick] = []
        for station, (lat, lon) in sorted(self.coordinates.items()):
            vertical = stream.select(station=station, channel=VERTICAL_CODE)
            if len(vertical) != 1:
                continue
            onset = pick_p_onset(
                vertical[0],
                first_trigger_time - self.gates.pick_search_before_seconds,
                first_trigger_time + self.gates.pick_search_after_seconds,
                self.pick_settings,
            )
            if onset is not None:
                picks.append(StationPick(station, lat, lon, onset.time, onset.snr))
        hypocenter = locate_hypocenter(
            picks, self.table, minimum_picks=self.gates.minimum_location_picks
        )
        if hypocenter is None:
            notes.append(f"location_failed_picks={len(picks)}")
            return Measurement(first_trigger_time, tuple(picks), None, (), tuple(notes))

        stations: list[StationMeasurement] = []
        for station, (lat, lon) in sorted(self.coordinates.items()):
            epicentral_km = float(
                haversine_deg(hypocenter.latitude, hypocenter.longitude, np.array(lat), np.array(lon))
                * KM_PER_DEGREE
            )
            hypocentral_km = math.hypot(epicentral_km, hypocenter.depth_km)
            distance_deg = epicentral_km / KM_PER_DEGREE
            p_arrival = hypocenter.origin_time + float(
                self.table.p(np.array(hypocenter.depth_km), np.array(distance_deg))
            )
            window_start = p_arrival - 1.0
            window_end = (
                hypocenter.origin_time
                + hypocentral_km / self.gates.lg_velocity_km_s
                + self.gates.coda_seconds
            )
            channels = wood_anderson_amplitudes(
                stream,
                self.inventory,
                station,
                window_start=window_start,
                window_end=window_end,
                noise_start=p_arrival - 1.0 - self.gates.noise_seconds,
                noise_end=p_arrival - 1.0,
                horizontal_codes=HORIZONTAL_CODES,
            )
            summary = station_amplitude(channels, "mean")
            if summary is None:
                continue
            maximum = station_amplitude(channels, "max")
            assert maximum is not None
            stations.append(
                StationMeasurement(
                    station_id=station,
                    hypocentral_km=hypocentral_km,
                    channels=tuple(channels),
                    amplitude_mean_mm=summary[0],
                    amplitude_max_mm=maximum[0],
                    snr=summary[1],
                    saturated=any(c.saturated for c in channels),
                )
            )
        return Measurement(first_trigger_time, tuple(picks), hypocenter, tuple(stations), tuple(notes))

    def location_reason(self, measurement: Measurement) -> str | None:
        return location_reason(measurement, self.gates)


def location_reason(measurement: Measurement, gates: QualityGates) -> str | None:
    """Razón por la que la ubicación no basta para estimar, o ``None``."""

    h = measurement.hypocenter
    if h is None:
        return "location_failed_insufficient_picks"
    if h.pick_count < gates.minimum_location_picks:
        return "location_failed_insufficient_picks"
    if h.rms_seconds > gates.maximum_rms_seconds:
        return "location_residual_too_large"
    if h.azimuthal_gap_deg > gates.maximum_gap_deg:
        return "location_azimuthal_gap_too_large"
    if h.horizontal_uncertainty_km > gates.maximum_horizontal_uncertainty_km:
        return "location_uncertainty_too_large"
    return None


def estimate(
    measurement: Measurement,
    calibration: LocalMagnitudeCalibration,
    gates: QualityGates = QualityGates(),
    *,
    aggregation: str | None = None,
    shadow: bool = False,
) -> MagnitudeEstimate:
    """Aplica una calibración y las compuertas a una medición.

    ``shadow=True`` calcula el valor interno para evaluarlo aunque la
    calibración no esté validada; ese valor nunca se publica.
    """

    aggregation = aggregation or calibration.aggregation
    reason = location_reason(measurement, gates)
    if reason is not None:
        return unavailable(reason, calibration)
    h = measurement.hypocenter
    assert h is not None
    low_km, high_km = calibration.distance_range_km
    depth_low, depth_high = calibration.depth_range_km
    # La calibración sólo vale donde hubo eventos de evaluación: las distancias,
    # las correcciones por estación y la fuente están confundidas.
    box = calibration.epicentre_box
    if box is not None and not (box[0] <= h.latitude <= box[1] and box[2] <= h.longitude <= box[3]):
        return unavailable("epicentre_outside_validated_domain", calibration)
    # Se valida la profundidad del mejor ajuste; su rango (mal resuelto sin S)
    # entra en la incertidumbre y la evaluación mide el error resultante.
    if not depth_low - 1e-6 <= h.depth_km <= depth_high + 1e-6:
        return unavailable("depth_outside_validated_domain", calibration)

    usable: list[StationMagnitude] = []
    saturated = 0
    low_snr = 0
    out_of_range = 0
    for item in measurement.stations:
        if item.saturated:
            saturated += 1
            continue
        if not low_km <= item.hypocentral_km <= high_km:
            out_of_range += 1
            continue
        amplitude = item.amplitude_max_mm if aggregation == "max" else item.amplitude_mean_mm
        if item.snr < gates.minimum_snr or amplitude <= 0:
            low_snr += 1
            continue
        usable.append(
            StationMagnitude(
                station_id=item.station_id,
                hypocentral_km=item.hypocentral_km,
                amplitude_mm=amplitude,
                snr=item.snr,
                magnitude=calibration.model.station_magnitude(amplitude, item.hypocentral_km, item.station_id),
                channels=tuple(c.channel for c in item.channels),
            )
        )
    if len(usable) < calibration.minimum_stations:
        if saturated and not usable:
            return unavailable("saturated_records", calibration, stations=usable)
        why = "insufficient_stations_in_distance_domain" if out_of_range >= low_snr else "insufficient_stations_with_snr"
        return unavailable(why, calibration, stations=usable)

    values = np.array([s.magnitude for s in usable])
    value = float(np.mean(values))
    spread = float(np.std(values, ddof=1)) if values.size > 1 else 0.0
    # Incertidumbre: error de la calibración (medido en validación), dispersión
    # entre estaciones, y cuánto cambiaría la distancia dentro de la incertidumbre
    # de la ubicación.
    distances = np.array([s.hypocentral_km for s in usable])
    slope = np.abs(calibration.model.a / (np.log(10) * distances) + calibration.model.b)
    location_term = float(np.mean(slope) * (h.horizontal_uncertainty_km + (h.depth_range_km[1] - h.depth_range_km[0]) / 2.0))
    uncertainty = math.sqrt(calibration.residual_sigma**2 + spread**2 / values.size + location_term**2)
    lower, upper = calibration.magnitude_range
    if not lower <= value <= upper:
        return unavailable("magnitude_outside_validated_range", calibration, internal=value, stations=usable)

    publishable = calibration.is_publishable and not shadow
    return MagnitudeEstimate(
        value=round(value, 1) if publishable else None,
        scale="ML",
        method=METHOD_DESCRIPTION,
        status="preliminary" if publishable else "unavailable",
        reason=None if publishable else "calibration_not_validated",
        uncertainty=round(uncertainty, 2),
        station_count=len(usable),
        stations=tuple(usable),
        calibration_version=calibration.version,
        hypocentral_range_km=(float(distances.min()), float(distances.max())),
        internal_value=value,
        validation_status=calibration.validation_status,
    )


def distinct_station_count(stations: Sequence[StationMagnitude]) -> int:
    """Una estación cuenta una vez aunque aporte dos horizontales."""

    return len({s.station_id for s in stations})
