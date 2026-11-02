"""Experimental P-hypothesis association, never a validated earthquake solution.

The STA/LTA peak is NOT a P pick. Only explicit onset hypotheses participate.
IASP91 is a global 1-D model: a small residual is necessary, not sufficient,
to identify an earthquake. This module does not estimate magnitude.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
from obspy import UTCDateTime  # type: ignore[import-untyped]
from scipy.interpolate import RegularGridInterpolator  # type: ignore[import-untyped]

from eew.models import StationTrigger


@dataclass(frozen=True)
class AssociationQuality:
    status: str
    reason: str
    validation_status: str = "experimental_unvalidated"
    latitude: float | None = None
    longitude: float | None = None
    depth_km: float | None = None
    origin_time: str | None = None
    rms_seconds: float | None = None
    horizontal_uncertainty_km: float | None = None
    azimuthal_gap_deg: float | None = None
    used_station_ids: tuple[str, ...] = ()
    rejected_station_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def onset_hypothesis(data: np.ndarray, rate: float, crossing: int) -> int | None:
    """Variance-change onset before a crossing; not proof of phase identity.

    AIC is bounded to the preceding 4 s with 10 s of preceding noise. Reject
    low SNR, flat and non-finite data. The caller preserves the original peak.
    """
    begin = max(0, crossing - round(4 * rate))
    end = min(len(data), crossing + round(rate))
    noise = data[max(0, begin - round(10 * rate)):begin]
    segment = data[begin:end]
    if len(noise) < round(5 * rate) or len(segment) < round(2 * rate):
        return None
    if not np.isfinite(noise).all() or not np.isfinite(segment).all():
        return None
    baseline = float(np.std(noise))
    if baseline <= 0 or float(np.std(segment)) < 3 * baseline:
        return None
    margin = max(2, round(0.25 * rate))
    scores = [
        k * math.log(max(float(np.var(segment[:k])), 1e-30))
        + (len(segment) - k) * math.log(max(float(np.var(segment[k:])), 1e-30))
        for k in range(margin, len(segment) - margin)
    ]
    index = margin + int(np.argmin(scores))
    if index in {margin, len(segment) - margin - 1}:
        return None
    return begin + index


def _distance(lat: Any, lon: Any, slat: Any, slon: Any) -> Any:
    a, b = np.radians(lat), np.radians(slat)
    value = np.sin((b - a) / 2) ** 2 + np.cos(a) * np.cos(b) * np.sin(
        np.radians(slon - lon) / 2
    ) ** 2
    return np.degrees(2 * np.arcsin(np.sqrt(np.clip(value, 0, 1))))


class PhaseAssociator:
    def __init__(self, table_path: Path):
        # Missing calibration fails visibly, never substitutes a made-up speed.
        with np.load(table_path, allow_pickle=False) as table:
            self.travel = RegularGridInterpolator(
                (table["depths_km"], table["distances_deg"]), table["p_seconds"],
                bounds_error=False, fill_value=np.nan,
            )

    def assess(self, triggers: tuple[StationTrigger, ...]) -> AssociationQuality:
        unique = eligible_onsets(triggers)
        # Bound memory/CPU independently of the total configured station count.
        # Retain recent observations; do not let a large public network allocate
        # an unbounded [grid x stations] travel-time array.
        stations = sorted(unique.values(), key=lambda s: str(s.p_onset_time), reverse=True)[:16]
        if len(stations) < 4:
            return AssociationQuality("insufficient_data", "need_four_independent_onsets")
        observed = np.array([float(UTCDateTime(s.p_onset_time)) for s in stations])
        observed -= observed.min()
        slat = np.array([s.latitude for s in stations], dtype=float)
        slon = np.array([s.longitude for s in stations], dtype=float)
        # Scope is Colombia only. Never force Chile or a teleseism into this grid.
        if any(s.country_code != "CO" for s in stations):
            return AssociationQuality("unsupported_region", "colombia_model_only")
        lat, lon, depth = np.meshgrid(
            np.arange(-5, 14.51, 0.2), np.arange(-83, -65.99, 0.2),
            [5., 15., 30., 50., 90., 150., 200.], indexing="ij",
        )
        lat, lon, depth = lat.ravel(), lon.ravel(), depth.ravel()
        distance = _distance(lat[:, None], lon[:, None], slat, slon)
        points = np.stack([np.broadcast_to(depth[:, None], distance.shape), distance], axis=-1)
        times = self.travel(points)
        origins = observed - times
        center = np.median(origins, axis=1)
        residual = np.abs(origins - center[:, None])
        # Regional neighborhoods; an outlier must not borrow a distant quorum.
        inliers = (residual <= 2.5) & (distance * 111.195 <= 500)
        count = inliers.sum(axis=1)
        valid = (count >= 4) & np.isfinite(times).all(axis=1)
        if not valid.any():
            return AssociationQuality("incoherent", "no_common_regional_p_origin")
        loss = np.where(valid, np.where(inliers, residual ** 2, 0).sum(axis=1) / np.maximum(count, 1), np.inf)
        # Prefer greater support; minimize residual only within that support.
        loss[count < count[valid].max()] = np.inf
        best = int(np.argmin(loss))
        used = inliers[best]
        near = (loss <= loss[best] + 1.0) & np.isfinite(loss)
        uncertainty = float(np.max(_distance(lat[best], lon[best], lat[near], lon[near])) * 111.195)
        bearings = []
        for a, b in zip(slat[used], slon[used], strict=True):
            dl = math.radians(b - lon[best])
            x = math.sin(dl) * math.cos(math.radians(a))
            y = math.cos(math.radians(lat[best])) * math.sin(math.radians(a)) - math.sin(
                math.radians(lat[best])
            ) * math.cos(math.radians(a)) * math.cos(dl)
            bearings.append(math.degrees(math.atan2(x, y)) % 360)
        bearings.sort()
        gap = max(b - a for a, b in zip(bearings, bearings[1:] + [bearings[0] + 360], strict=True))
        edge = lat[best] <= -5 or lat[best] >= 14.4 or lon[best] <= -83 or lon[best] >= -66.1
        reason = "regional_p_hypothesis_only"
        if edge or uncertainty > 40 or gap > 240:
            reason = "poor_geometry_or_ambiguous_location"
        first = min(float(UTCDateTime(s.p_onset_time)) for s in stations)
        return AssociationQuality(
            "experimental_consistent" if reason == "regional_p_hypothesis_only" else "ambiguous",
            reason, latitude=float(lat[best]), longitude=float(lon[best]),
            depth_km=float(depth[best]), origin_time=str(UTCDateTime(first + center[best])),
            rms_seconds=float(np.sqrt(loss[best])), horizontal_uncertainty_km=uncertainty,
            azimuthal_gap_deg=gap,
            used_station_ids=tuple(s.station_id for s, use in zip(stations, used, strict=True) if use),
            rejected_station_ids=tuple(s.station_id for s, use in zip(stations, used, strict=True) if not use),
        )


def eligible_onsets(triggers: tuple[StationTrigger, ...]) -> dict[str, StationTrigger]:
    unique: dict[str, StationTrigger] = {}
    for s in triggers:
        if (s.p_onset_time is None or s.latitude is None or s.longitude is None
                or not math.isfinite(s.latitude) or not math.isfinite(s.longitude)
                or not s.stream_id.endswith("Z") or s.packet_lag_seconds is None
                or not 0 <= s.packet_lag_seconds <= 15
                or s.pick_method != "aic_onset_hypothesis_v1"):
            continue
        old = unique.get(s.station_id)
        if old is None or UTCDateTime(s.p_onset_time) > UTCDateTime(old.p_onset_time):
            unique[s.station_id] = s
    return unique
