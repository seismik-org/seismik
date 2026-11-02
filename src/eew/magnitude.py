"""Estimación de magnitud preliminar basada en calibración, no en IA opaca.

SeedLink entrega cuentas del digitalizador. Por sí solas no son desplazamiento
del suelo ni permiten declarar una magnitud. Este módulo aplica una regresión
regional *únicamente* después de entrenarla con candidatos de Seismik asociados
a informes oficiales y de comprobar su error. No se activa ninguna calibración
en producción hasta completar esa validación.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from eew.models import StationTrigger


@dataclass(frozen=True)
class MagnitudeCalibration:
    """Modelo regional auditado contra magnitudes oficiales."""

    zone_id: str
    intercept: float
    slope: float
    validation_sample_count: int
    validation_mae: float
    max_validation_mae: float = 0.5
    minimum_validation_samples: int = 50

    @property
    def is_validated(self) -> bool:
        return (
            all(
                math.isfinite(value)
                for value in (
                    self.intercept,
                    self.slope,
                    self.validation_mae,
                    self.max_validation_mae,
                )
            )
            and self.slope > 0
            and self.validation_mae >= 0
            and self.minimum_validation_samples >= 50
            and self.max_validation_mae <= 0.5
            and self.validation_sample_count >= self.minimum_validation_samples
            and self.validation_mae <= self.max_validation_mae
        )


def estimate_preliminary_magnitude(
    stations: tuple[StationTrigger, ...], calibration: MagnitudeCalibration | None
) -> float | None:
    """Devuelve M~ solo con una calibración regional ya validada.

    La mediana reduce el peso de un sensor anómalo. En ausencia de respuesta
    instrumental/calibración, devolver ``None`` es deliberado y seguro.
    """

    if calibration is None or not calibration.is_validated:
        return None
    ratios = [
        math.log10(trigger.peak_amplitude_counts / trigger.noise_rms_counts)
        for trigger in stations
        if trigger.peak_amplitude_counts is not None
        and trigger.noise_rms_counts is not None
        and trigger.peak_amplitude_counts > 0
        and trigger.noise_rms_counts > 0
        and math.isfinite(trigger.peak_amplitude_counts)
        and math.isfinite(trigger.noise_rms_counts)
    ]
    if len(ratios) < 3:
        return None
    ratios.sort()
    midpoint = len(ratios) // 2
    median = ratios[midpoint] if len(ratios) % 2 else (ratios[midpoint - 1] + ratios[midpoint]) / 2
    estimate = calibration.intercept + calibration.slope * median
    return round(estimate, 1) if math.isfinite(estimate) and -2 <= estimate <= 10 else None
