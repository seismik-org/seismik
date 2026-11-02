"""Picks de la onda P y localización del hipocentro con incertidumbre.

El detector STA/LTA dice *cuándo* varias estaciones se activaron; no dice dónde
fue el sismo. El centroide de las estaciones no es un epicentro y no se usa
aquí. Este módulo estima un hipocentro a partir de los tiempos de llegada de la
onda P en las estaciones, con un modelo 1D tabulado (`build_travel_time_table`).

Límites que el resultado declara en lugar de ocultar:

- Sólo hay P, sin S: con la profundidad y el tiempo origen acoplados, la
  profundidad se resuelve mal. Se devuelve el rango de profundidades que los
  datos no distinguen, no un valor con falsa precisión.
- Con pocas estaciones o un hueco azimutal grande, la solución se marca como
  no fiable y quien la use debe devolver ``null``.
- El modelo es 1D: el error del modelo no está en la incertidumbre formal y se
  mide aparte contra localizaciones independientes.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from scipy.interpolate import RegularGridInterpolator  # type: ignore[import-untyped]

EARTH_RADIUS_KM = 6371.0088
KM_PER_DEGREE = math.pi * EARTH_RADIUS_KM / 180.0
DEFAULT_TABLE = Path(__file__).resolve().parents[2] / "data/calibration/traveltime-iasp91-regional.npz"

# Región de búsqueda: Colombia, sus mares y la franja fronteriza cercana.
SEARCH_BOUNDS = (-5.0, 14.5, -83.0, -66.0)  # lat_min, lat_max, lon_min, lon_max
COARSE_STEP_DEG = 0.25
FINE_STEP_DEG = 0.05
COARSE_DEPTHS_KM = (5.0, 15.0, 30.0, 50.0, 90.0, 150.0, 200.0)


class TravelTimeTable:
    """Primeras llegadas P y S, interpoladas bilinealmente."""

    def __init__(self, distances_deg: np.ndarray, depths_km: np.ndarray, p: np.ndarray, s: np.ndarray) -> None:
        self.distances_deg = distances_deg
        self.depths_km = depths_km
        self._p = RegularGridInterpolator((depths_km, distances_deg), p, bounds_error=False, fill_value=np.nan)
        self._s = RegularGridInterpolator((depths_km, distances_deg), s, bounds_error=False, fill_value=np.nan)

    @classmethod
    def load(cls, path: Path = DEFAULT_TABLE) -> TravelTimeTable:
        with np.load(path) as data:
            return cls(data["distances_deg"], data["depths_km"], data["p_seconds"], data["s_seconds"])

    @property
    def max_depth_km(self) -> float:
        return float(self.depths_km[-1])

    def _evaluate(self, interpolator: RegularGridInterpolator, depth_km: np.ndarray, distance_deg: np.ndarray) -> np.ndarray:
        depth, distance = np.broadcast_arrays(np.asarray(depth_km, dtype=float), np.asarray(distance_deg, dtype=float))
        return interpolator(np.stack([depth.ravel(), distance.ravel()], axis=-1)).reshape(depth.shape)

    def p(self, depth_km: np.ndarray, distance_deg: np.ndarray) -> np.ndarray:
        return self._evaluate(self._p, depth_km, distance_deg)

    def s(self, depth_km: np.ndarray, distance_deg: np.ndarray) -> np.ndarray:
        return self._evaluate(self._s, depth_km, distance_deg)


@dataclass(frozen=True)
class StationPick:
    station_id: str
    latitude: float
    longitude: float
    time: float  # segundos desde la época Unix
    snr: float | None = None


@dataclass(frozen=True)
class Hypocenter:
    latitude: float
    longitude: float
    depth_km: float
    origin_time: float
    rms_seconds: float
    pick_count: int
    used_station_ids: tuple[str, ...]
    rejected_station_ids: tuple[str, ...]
    azimuthal_gap_deg: float
    horizontal_uncertainty_km: float
    depth_range_km: tuple[float, float]
    nearest_station_km: float
    flags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def depth_resolved(self) -> bool:
        low, high = self.depth_range_km
        return (high - low) <= 40.0


def haversine_deg(lat1: Any, lon1: Any, lat2: Any, lon2: Any) -> Any:
    """Distancia angular en grados, vectorizada."""

    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp, dl = p2 - p1, np.radians(lon2 - lon1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return np.degrees(2 * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0))))


def azimuthal_gap_deg(latitude: float, longitude: float, stations: Sequence[tuple[float, float]]) -> float:
    if len(stations) < 2:
        return 360.0
    azimuths = []
    for station_lat, station_lon in stations:
        d_lon = math.radians(station_lon - longitude)
        lat1, lat2 = math.radians(latitude), math.radians(station_lat)
        y = math.sin(d_lon) * math.cos(lat2)
        x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(d_lon)
        azimuths.append((math.degrees(math.atan2(y, x)) + 360.0) % 360.0)
    azimuths.sort()
    gaps = [b - a for a, b in zip(azimuths, azimuths[1:], strict=False)]
    gaps.append(360.0 - azimuths[-1] + azimuths[0])
    return max(gaps)


def _misfit(
    table: TravelTimeTable,
    lat: np.ndarray,
    lon: np.ndarray,
    depth: np.ndarray,
    station_lat: np.ndarray,
    station_lon: np.ndarray,
    observed: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Suma de cuadrados de residuos y tiempo origen óptimo para cada nodo.

    El tiempo origen es la media de ``observado - predicho``: se resuelve en
    forma cerrada, no se busca en la malla.
    """

    distance = haversine_deg(lat[..., None], lon[..., None], station_lat, station_lon)
    predicted = table.p(depth[..., None], distance)
    residual = observed - predicted
    # Un nodo sólo es válido si TODAS las estaciones tienen tiempo de viaje
    # tabulado. Ignorar las que quedan fuera del rango deja nodos lejanos con una
    # sola estación y residuo cero, que ganarían la búsqueda sin ser solución.
    valid = np.isfinite(predicted).all(axis=-1)
    residual = np.where(valid[..., None], residual, 0.0)
    origin = residual.mean(axis=-1)
    sum_squares = ((residual - origin[..., None]) ** 2).sum(axis=-1)
    sum_squares = np.where(valid, sum_squares, np.inf)
    origin = np.where(valid, origin, np.nan)
    return sum_squares, origin


def locate_hypocenter(
    picks: Sequence[StationPick],
    table: TravelTimeTable,
    *,
    pick_sigma_seconds: float = 0.5,
    minimum_picks: int = 5,
    max_residual_seconds: float = 2.5,
    bounds: tuple[float, float, float, float] = SEARCH_BOUNDS,
) -> Hypocenter | None:
    """Estima el hipocentro y su incertidumbre; ``None`` si no hay datos para ello.

    Rechaza iterativamente la pick con peor residuo mientras supere
    ``max_residual_seconds`` y queden más de ``minimum_picks`` estaciones. Una
    estación ruidosa que "dispara" por una causa ajena no debe arrastrar la
    solución, pero tampoco se descartan datos sin dejar rastro.
    """

    active = list(picks)
    if len(active) < minimum_picks:
        return None
    rejected: list[str] = []
    while True:
        solution = _solve(active, table, pick_sigma_seconds, bounds)
        if solution is None:
            return None
        residuals = solution["residuals"]
        worst = int(np.argmax(np.abs(residuals)))
        if abs(residuals[worst]) <= max_residual_seconds or len(active) <= minimum_picks:
            break
        rejected.append(active[worst].station_id)
        del active[worst]
    stations = [(p.latitude, p.longitude) for p in active]
    flags: list[str] = []
    if rejected:
        flags.append("picks_rejected_by_residual")
    nearest_km = float(
        np.min(haversine_deg(solution["lat"], solution["lon"], np.array([s[0] for s in stations]), np.array([s[1] for s in stations])))
        * KM_PER_DEGREE
    )
    return Hypocenter(
        latitude=solution["lat"],
        longitude=solution["lon"],
        depth_km=solution["depth"],
        origin_time=solution["origin"],
        rms_seconds=solution["rms"],
        pick_count=len(active),
        used_station_ids=tuple(p.station_id for p in active),
        rejected_station_ids=tuple(rejected),
        azimuthal_gap_deg=azimuthal_gap_deg(solution["lat"], solution["lon"], stations),
        horizontal_uncertainty_km=solution["horizontal_uncertainty_km"],
        depth_range_km=solution["depth_range"],
        nearest_station_km=nearest_km,
        flags=tuple(flags),
    )


def _solve(
    picks: list[StationPick],
    table: TravelTimeTable,
    sigma: float,
    bounds: tuple[float, float, float, float],
) -> dict[str, Any] | None:
    station_lat = np.array([p.latitude for p in picks])
    station_lon = np.array([p.longitude for p in picks])
    observed = np.array([p.time for p in picks])
    reference = float(np.min(observed))
    observed = observed - reference  # evita perder precisión con segundos Unix

    lat_min, lat_max, lon_min, lon_max = bounds
    lats = np.arange(lat_min, lat_max + 1e-9, COARSE_STEP_DEG)
    lons = np.arange(lon_min, lon_max + 1e-9, COARSE_STEP_DEG)
    depths = np.array(COARSE_DEPTHS_KM)
    grid_lat, grid_lon, grid_depth = np.meshgrid(lats, lons, depths, indexing="ij")
    sum_squares, _ = _misfit(table, grid_lat, grid_lon, grid_depth, station_lat, station_lon, observed)
    best = np.unravel_index(np.argmin(sum_squares), sum_squares.shape)
    lat0, lon0 = float(lats[best[0]]), float(lons[best[1]])

    half = 1.5
    fine_lats = np.arange(max(lat_min, lat0 - half), min(lat_max, lat0 + half) + 1e-9, FINE_STEP_DEG)
    fine_lons = np.arange(max(lon_min, lon0 - half), min(lon_max, lon0 + half) + 1e-9, FINE_STEP_DEG)
    fine_depths = table.depths_km[table.depths_km <= 200.0]
    f_lat, f_lon, f_depth = np.meshgrid(fine_lats, fine_lons, fine_depths, indexing="ij")
    fine, origins = _misfit(table, f_lat, f_lon, f_depth, station_lat, station_lon, observed)
    index = np.unravel_index(np.argmin(fine), fine.shape)
    best_sum = float(fine[index])
    if not np.isfinite(best_sum):
        return None

    count = len(picks)
    rms = math.sqrt(best_sum / count)
    degrees_of_freedom = max(count - 4, 1)
    # La incertidumbre formal usa la mayor entre la sigma supuesta de las picks
    # y la dispersión observada: un ajuste malo no puede declararse preciso.
    effective_sigma = max(sigma, math.sqrt(best_sum / degrees_of_freedom))
    chi_square = fine / effective_sigma**2
    region = chi_square <= (chi_square[index] + 7.78)  # 90 % de confianza, 4 parámetros
    region_lat, region_lon = f_lat[region], f_lon[region]
    centre_lat, centre_lon = float(f_lat[index]), float(f_lon[index])
    spread_km = (
        haversine_deg(centre_lat, centre_lon, region_lat, region_lon) * KM_PER_DEGREE
        if region_lat.size
        else np.array([0.0])
    )
    depth_values = f_depth[region] if region.any() else np.array([f_depth[index]])
    residuals = observed - (
        table.p(
            np.full(count, f_depth[index]),
            haversine_deg(centre_lat, centre_lon, station_lat, station_lon),
        )
        + origins[index]
    )
    return {
        "lat": centre_lat,
        "lon": centre_lon,
        "depth": float(f_depth[index]),
        "origin": float(origins[index]) + reference,
        "rms": rms,
        "horizontal_uncertainty_km": float(np.max(spread_km)),
        "depth_range": (float(np.min(depth_values)), float(np.max(depth_values))),
        "residuals": residuals,
    }
