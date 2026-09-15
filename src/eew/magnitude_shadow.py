"""Colección y evaluación en sombra de una futura magnitud SeedLink.

Las cuentas del digitalizador no son una magnitud física. Este módulo nunca
publica una M ni participa en alertas: conserva únicamente observaciones que
han sido asociadas con un informe oficial para poder medir un modelo regional.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import median

from eew.models import EarthquakeCandidate, OfficialReport

MINIMUM_OBSERVATIONS = 50
MAX_VALIDATION_MAE = 0.5


@dataclass(frozen=True)
class ShadowMagnitudeFit:
    """Resultado auditable de una regresión de prueba; no habilita producción."""

    zone_id: str
    intercept: float
    signal_slope: float
    distance_slope: float
    sample_count: int
    validation_count: int
    validation_mae: float

    @property
    def is_ready_for_review(self) -> bool:
        return (
            self.sample_count >= MINIMUM_OBSERVATIONS
            and self.validation_count > 0
            and self.validation_mae <= MAX_VALIDATION_MAE
        )


def observation_for_match(
    candidate: EarthquakeCandidate, report: OfficialReport
) -> dict[str, object] | None:
    """Genera la fila de calibración para un candidato confirmado oficialmente.

    La distancia se calcula hacia el epicentro oficial, no hacia el centroide
    de estaciones. La salida se adjunta al evento interno oficial y no llega a
    la app ni a los avisos.
    """

    if report.magnitude is None:
        return None
    signal = _median_log_snr(candidate)
    distances = [
        _hypocentral_distance_km(station.latitude, station.longitude, report)
        for station in candidate.stations
        if station.latitude is not None and station.longitude is not None
    ]
    if signal is None or len(distances) < 3:
        return None
    return {
        "mode": "shadow_calibration_only",
        "zone_id": candidate.zone_id,
        "candidate_event_id": candidate.event_id,
        "official_source_id": report.source_id,
        "official_event_id": report.official_event_id,
        "official_magnitude": round(report.magnitude, 3),
        "official_magnitude_type": report.magnitude_type,
        "median_log10_snr": round(signal, 6),
        "median_hypocentral_distance_km": round(median(distances), 3),
        "station_count_with_geometry": len(distances),
        "station_count_with_signal": sum(
            1
            for station in candidate.stations
            if station.peak_amplitude_counts is not None
            and station.noise_rms_counts is not None
            and station.peak_amplitude_counts > 0
            and station.noise_rms_counts > 0
        ),
        "depth_km": report.depth_km,
    }


def fit_shadow_model(observations: list[dict[str, object]]) -> ShadowMagnitudeFit | None:
    """Ajusta y valida un proxy SNR/distancia separado por zona.

    Es una herramienta de evaluación, no una calibración instrumental. Exige
    50 asociaciones y una partición determinista de validación antes de poder
    siquiera marcarse como lista para revisión humana.
    """

    rows: list[tuple[str, float, float, float, str]] = []
    for observation in observations:
        if (row := _row(observation)) is not None:
            rows.append(row)
    if len(rows) < MINIMUM_OBSERVATIONS:
        return None
    zone_ids = {row[0] for row in rows}
    if len(zone_ids) != 1:
        raise ValueError("Las observaciones de sombra deben pertenecer a una sola zona")
    rows.sort(key=lambda row: str(row[4]))
    validation = rows[::5]
    training = [row for index, row in enumerate(rows) if index % 5]
    if len(training) < 3 or not validation:
        return None
    intercept, signal_slope, distance_slope = _least_squares(training)
    errors = [
        abs((intercept + signal_slope * row[1] + distance_slope * row[2]) - row[3])
        for row in validation
    ]
    return ShadowMagnitudeFit(
        zone_id=next(iter(zone_ids)),
        intercept=round(intercept, 6),
        signal_slope=round(signal_slope, 6),
        distance_slope=round(distance_slope, 6),
        sample_count=len(rows),
        validation_count=len(validation),
        validation_mae=round(sum(errors) / len(errors), 6),
    )


def _median_log_snr(candidate: EarthquakeCandidate) -> float | None:
    values = [
        math.log10(station.peak_amplitude_counts / station.noise_rms_counts)
        for station in candidate.stations
        if station.peak_amplitude_counts is not None
        and station.noise_rms_counts is not None
        and station.peak_amplitude_counts > 0
        and station.noise_rms_counts > 0
    ]
    return median(values) if len(values) >= 3 else None


def _hypocentral_distance_km(latitude: float, longitude: float, report: OfficialReport) -> float:
    earth_radius_km = 6371.0088
    lat1, lat2 = math.radians(latitude), math.radians(report.latitude)
    d_lat = lat2 - lat1
    d_lon = math.radians(report.longitude - longitude)
    a = math.sin(d_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(d_lon / 2) ** 2
    surface = earth_radius_km * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return math.hypot(surface, report.depth_km or 0.0)


def _row(item: dict[str, object]) -> tuple[str, float, float, float, str] | None:
    try:
        zone = str(item["zone_id"])
        signal = _as_float(item["median_log10_snr"])
        distance = _as_float(item["median_hypocentral_distance_km"])
        magnitude = _as_float(item["official_magnitude"])
        identity = str(item["candidate_event_id"])
    except (KeyError, TypeError, ValueError):
        return None
    if not zone or not math.isfinite(signal) or not math.isfinite(distance) or distance <= 0:
        return None
    if not math.isfinite(magnitude):
        return None
    return zone, signal, math.log10(distance), magnitude, identity


def _as_float(value: object) -> float:
    if isinstance(value, bool):
        raise ValueError("los booleanos no son medidas")
    if isinstance(value, (float, int, str)):
        return float(value)
    raise ValueError("medida no numérica")


def _least_squares(rows: list[tuple[str, float, float, float, str]]) -> tuple[float, float, float]:
    # Ecuaciones normales para y = a + b*logSNR + c*logDist. Sin numpy para
    # que el cálculo sea portable y fácil de auditar.
    matrix = [[0.0] * 4 for _ in range(3)]
    for _zone, signal, distance, magnitude, _identity in rows:
        vector = (1.0, signal, distance)
        for row in range(3):
            for column in range(3):
                matrix[row][column] += vector[row] * vector[column]
            matrix[row][3] += vector[row] * magnitude
    for pivot in range(3):
        best = max(range(pivot, 3), key=lambda row: abs(matrix[row][pivot]))
        if abs(matrix[best][pivot]) < 1e-12:
            raise ValueError("Observaciones de sombra sin variación suficiente")
        matrix[pivot], matrix[best] = matrix[best], matrix[pivot]
        divisor = matrix[pivot][pivot]
        matrix[pivot] = [value / divisor for value in matrix[pivot]]
        for row in range(3):
            if row == pivot:
                continue
            factor = matrix[row][pivot]
            matrix[row] = [
                value - factor * pivot_value
                for value, pivot_value in zip(matrix[row], matrix[pivot], strict=True)
            ]
    return matrix[0][3], matrix[1][3], matrix[2][3]
