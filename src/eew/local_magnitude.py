"""Magnitud local ML (Richter) a partir de las horizontales, no de la vertical.

Qué es y qué no es:

- Es **ML**: amplitud máxima de la señal simulada en un sismógrafo Wood-
  Anderson, con corrección por distancia. No es mb (onda P de periodo corto) ni
  Mw (momento sísmico) y se etiqueta siempre como ML.
- Usa HHN/HHE de estaciones banda ancha con la respuesta instrumental de la
  época del registro (StationXML). Las cuentas crudas nunca se convierten
  directamente en magnitud.
- La corrección por distancia ``-logA0(R)`` es de la forma de Hutton y Boore
  (1987) con coeficientes **ajustados a la escala ML del SGC** en la evaluación
  (`tools/evaluate_local_magnitude.py`). Por eso el resultado es "ML calibrada a
  la escala del SGC", no una ML independiente del SGC: se declara así.
- Sólo vale dentro del dominio donde la evaluación lo respalda (distancia,
  profundidad y magnitud). Fuera de él devuelve ``None`` con una razón.
- Una estación cuenta una vez, aunque aporte dos horizontales: las horizontales
  no añaden estaciones al quórum del detector.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from obspy import Inventory, Stream, Trace  # type: ignore[import-untyped]

# Wood-Anderson según IASPEI (ganancia 2080, T0 = 0.8 s, h = 0.7). La entrada es
# DESPLAZAMIENTO del suelo (remove_response(output="DISP")), por eso lleva dos
# ceros en el origen: con uno solo (la forma para entrada en velocidad) la
# amplitud sale dividida por 2*pi*f. `test_local_magnitude` fija la ganancia.
WOOD_ANDERSON = {
    "poles": [-6.283185 - 4.712389j, -6.283185 + 4.712389j],
    "zeros": [0j, 0j],
    "gain": 1.0,
    "sensitivity": 2080.0,
}
# Pre-filtro de la deconvolución: evita amplificar ruido de periodo largo fuera
# de la banda útil del STS-2 sin tocar las frecuencias de una ML local (~0.5-10 Hz).
PRE_FILTER_HZ = (0.1, 0.25, 30.0, 40.0)
DEFAULT_CALIBRATION = Path(__file__).resolve().parents[2] / "data/calibration/ml-calibration.json"
# Cuentas de un Q330 de 24 bits: cerca del tope el registro puede estar recortado.
SATURATION_COUNTS = 0.9 * 2**23


@dataclass(frozen=True)
class AttenuationModel:
    """``ML = log10(A_mm) + a*log10(R/100) + b*(R-100) + c + corrección``."""

    a: float
    b: float
    c: float
    station_corrections: Mapping[str, float] = field(default_factory=dict)

    def distance_term(self, hypocentral_km: float) -> float:
        return self.a * math.log10(hypocentral_km / 100.0) + self.b * (hypocentral_km - 100.0) + self.c

    def station_magnitude(self, amplitude_mm: float, hypocentral_km: float, station_id: str) -> float:
        return (
            math.log10(amplitude_mm)
            + self.distance_term(hypocentral_km)
            + self.station_corrections.get(station_id, 0.0)
        )


# Hutton y Boore (1987), California: punto de partida físico, NO calibración colombiana.
HUTTON_BOORE = AttenuationModel(a=1.110, b=0.00189, c=3.0)


@dataclass(frozen=True)
class LocalMagnitudeCalibration:
    version: str
    status: str  # "validated" | "failed_validation" | "insufficient_events" | "not_evaluated"
    publication_enabled: bool
    model: AttenuationModel
    residual_sigma: float
    distance_range_km: tuple[float, float]
    depth_range_km: tuple[float, float]
    magnitude_range: tuple[float, float]
    minimum_stations: int = 3
    evaluation_sha256: str | None = None
    aggregation: str = "mean"  # cómo se combinan las dos horizontales de una estación
    # (lat_min, lat_max, lon_min, lon_max) donde la evaluación tiene eventos; None = sin restricción
    epicentre_box: tuple[float, float, float, float] | None = None
    beta_authorized: bool = False

    @classmethod
    def load(cls, path: Path = DEFAULT_CALIBRATION) -> LocalMagnitudeCalibration:
        data = json.loads(path.read_text(encoding="utf-8"))
        attenuation = data["attenuation"]
        try:
            authorization = json.loads(path.with_name("ml-beta-authorization.json").read_text(encoding="utf-8"))
            beta_authorized = (
                authorization.get("scope") == "beta"
                and authorization.get("version") == data["version"]
                and isinstance(data.get("evaluation_sha256"), str)
                and authorization.get("evaluation_sha256") == data["evaluation_sha256"]
            )
        except (OSError, ValueError, AttributeError):
            beta_authorized = False
        return cls(
            version=data["version"],
            status=data["status"],
            publication_enabled=(data["status"] == "validated" and bool(data["publication_enabled"])) or beta_authorized,
            beta_authorized=beta_authorized,
            model=AttenuationModel(
                a=float(attenuation["a"]),
                b=float(attenuation["b"]),
                c=float(attenuation["c"]),
                station_corrections={k: float(v) for k, v in attenuation.get("station_corrections", {}).items()},
            ),
            residual_sigma=float(data["residual_sigma"]),
            distance_range_km=tuple(data["domain"]["hypocentral_distance_km"]),  # type: ignore[arg-type]
            depth_range_km=tuple(data["domain"]["depth_km"]),  # type: ignore[arg-type]
            magnitude_range=tuple(data["domain"]["magnitude"]),  # type: ignore[arg-type]
            minimum_stations=int(data.get("minimum_stations", 3)),
            evaluation_sha256=data.get("evaluation_sha256"),
            aggregation=data.get("aggregation", "mean"),
            epicentre_box=tuple(data["domain"]["epicentre_box"]) if data["domain"].get("epicentre_box") else None,  # type: ignore[arg-type]
        )

    @property
    def is_publishable(self) -> bool:
        return self.publication_enabled and (self.status == "validated" or self.beta_authorized)

    @property
    def validation_status(self) -> str:
        if self.status == "validated":
            return "validated"
        return "beta_unvalidated" if self.beta_authorized else self.status


@dataclass(frozen=True)
class ChannelAmplitude:
    channel: str
    peak_mm: float
    noise_peak_mm: float
    saturated: bool


def revoke_beta_authorization(calibration_path: Path) -> None:
    """Re-evaluation revokes beta even if the input measurements have the same hash."""
    path = calibration_path.with_name("ml-beta-authorization.json")
    if not path.exists():
        return
    try:
        authorization = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        authorization = {}
    if not isinstance(authorization, dict):
        authorization = {}
    authorization["scope"] = "revoked"
    authorization["revocation_reason"] = "re_evaluation_requires_new_owner_authorization"
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(authorization, indent=2), encoding="utf-8")
    temporary.replace(path)


@dataclass(frozen=True)
class StationMagnitude:
    station_id: str
    hypocentral_km: float
    amplitude_mm: float
    snr: float
    magnitude: float
    channels: tuple[str, ...]


@dataclass(frozen=True)
class MagnitudeEstimate:
    """Resultado de una estimación; ``value`` es ``None`` si no es publicable."""

    value: float | None
    scale: str
    method: str
    status: str  # "preliminary" | "unavailable"
    reason: str | None
    uncertainty: float | None
    station_count: int
    stations: tuple[StationMagnitude, ...]
    calibration_version: str | None
    hypocentral_range_km: tuple[float, float] | None = None
    internal_value: float | None = None  # sólo evaluación en sombra; nunca se publica
    validation_status: str = "not_evaluated"

    def to_payload(self) -> dict[str, object]:
        return {
            "magnitude": self.value,
            "validation_status": self.validation_status,
            "magnitude_scale": self.scale,
            "magnitude_method": self.method,
            "magnitude_status": self.status,
            "magnitude_unavailable_reason": self.reason,
            "magnitude_uncertainty": self.uncertainty,
            "magnitude_station_count": self.station_count,
            "magnitude_stations": [
                {
                    "station_id": s.station_id,
                    "channels": list(s.channels),
                    "hypocentral_km": round(s.hypocentral_km, 1),
                    "amplitude_mm": float(f"{s.amplitude_mm:.4g}"),
                    "snr": round(s.snr, 1),
                    "magnitude": round(s.magnitude, 2),
                }
                for s in self.stations
            ],
            "magnitude_calibration_version": self.calibration_version,
        }


METHOD_DESCRIPTION = (
    "ML Wood-Anderson simulada en HHN/HHE con respuesta instrumental por época; "
    "corrección por distancia ajustada a la escala ML del SGC"
)


def unavailable(reason: str, calibration: LocalMagnitudeCalibration | None, *, internal: float | None = None,
                stations: Sequence[StationMagnitude] = ()) -> MagnitudeEstimate:
    return MagnitudeEstimate(
        value=None,
        scale="ML",
        method=METHOD_DESCRIPTION,
        status="unavailable",
        reason=reason,
        uncertainty=None,
        station_count=len(stations),
        stations=tuple(stations),
        calibration_version=calibration.version if calibration else None,
        internal_value=internal,
        validation_status=calibration.validation_status if calibration else "not_evaluated",
    )


def wood_anderson_amplitudes(
    stream: Stream,
    inventory: Inventory,
    station: str,
    *,
    window_start: float,
    window_end: float,
    noise_start: float,
    noise_end: float,
    horizontal_codes: tuple[str, ...] = ("HHN", "HHE"),
) -> list[ChannelAmplitude]:
    """Amplitud pico (mm, Wood-Anderson) y pico de ruido por horizontal.

    Los tiempos son segundos Unix. Devuelve sólo las componentes con datos
    completos y finitos en ambas ventanas; una ventana incompleta o con huecos
    se descarta en lugar de medirse a medias.
    """

    result: list[ChannelAmplitude] = []
    for code in horizontal_codes:
        traces = stream.select(station=station, channel=code)
        if len(traces) != 1:  # ausente, o partida por huecos
            continue
        trace: Trace = traces[0].copy()
        start = float(trace.stats.starttime.timestamp)
        end = float(trace.stats.endtime.timestamp)
        if noise_start < start or window_end > end:
            continue
        raw = np.asarray(trace.data, dtype=np.float64)
        if not np.isfinite(raw).all():
            continue
        first = int((window_start - start) * trace.stats.sampling_rate)
        last = int((window_end - start) * trace.stats.sampling_rate)
        saturated = bool(np.max(np.abs(raw[max(first, 0) : max(last, 1)])) >= SATURATION_COUNTS)
        # Margen para que el taper de la deconvolución no toque las ventanas medidas.
        margin = 20.0
        trace.trim(
            starttime=trace.stats.starttime + max(0.0, noise_start - margin - start),
            endtime=trace.stats.starttime + min(end - start, window_end + margin - start),
        )
        trace.detrend("demean")
        try:
            trace.remove_response(inventory=inventory, output="DISP", pre_filt=PRE_FILTER_HZ, water_level=None,
                                  zero_mean=True, taper=True, taper_fraction=0.05)
        except Exception:  # noqa: BLE001 - sin respuesta válida para la época: no hay medida
            continue
        trace.simulate(paz_remove=None, paz_simulate=WOOD_ANDERSON, simulate_sensitivity=True)
        data = np.asarray(trace.data, dtype=np.float64) * 1000.0  # m -> mm
        times = trace.times("timestamp")
        in_window = (times >= window_start) & (times <= window_end)
        in_noise = (times >= noise_start) & (times <= noise_end)
        if not in_window.any() or in_noise.sum() < int(10 * trace.stats.sampling_rate) or not np.isfinite(data).all():
            continue
        result.append(
            ChannelAmplitude(
                channel=code,
                peak_mm=float(np.max(np.abs(data[in_window]))),
                noise_peak_mm=float(np.max(np.abs(data[in_noise]))),
                saturated=saturated,
            )
        )
    return result


def station_amplitude(channels: Sequence[ChannelAmplitude], aggregation: str = "mean") -> tuple[float, float] | None:
    """Combina las horizontales de una estación: (amplitud, SNR) o ``None``."""

    if not channels:
        return None
    peaks = [c.peak_mm for c in channels]
    noise = max(max(c.noise_peak_mm for c in channels), 1e-12)
    amplitude = max(peaks) if aggregation == "max" else float(np.mean(peaks))
    return amplitude, amplitude / noise
