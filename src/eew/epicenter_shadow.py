"""Bounded experimental P/S location. Results cannot authorize public alerts.

Coordinates are hypotheses, never catalogue inputs. Spread and station-removal
stability are diagnostics, not calibrated confidence intervals. No network,
dispatcher, API publication or magnitude calibration is involved.
"""
from __future__ import annotations

import math
from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

import numpy as np
from scipy.interpolate import RegularGridInterpolator  # type: ignore[import-untyped]
from scipy.optimize import least_squares  # type: ignore[import-untyped]


def distance_deg(lat: Any, lon: Any, slat: Any, slon: Any) -> Any:
    a, b = np.radians(lat), np.radians(slat)
    x = np.sin((a-b)/2)**2 + np.cos(a)*np.cos(b)*np.sin(np.radians(lon-slon)/2)**2
    return np.degrees(2*np.arcsin(np.sqrt(np.clip(x, 0, 1))))


@dataclass(frozen=True)
class PhaseArrival:
    station_id: str
    latitude: float
    longitude: float
    time: float
    phase: str  # P/S hypotheses must be identified upstream, never STA/LTA peaks.
    sigma_seconds: float = 0.5


@dataclass(frozen=True)
class LocationSettings:
    bounds: tuple[float, float, float, float] = (-5., 14.5, -83., -66.)
    minimum_stations: int = 5
    maximum_stations: int = 16
    maximum_depth_km: float = 200.
    maximum_rms_seconds: float = 1.5
    maximum_gap_deg: float = 240.
    maximum_stability_km: float = 30.
    coarse_step_deg: float = 0.5
    seed_count: int = 6

    def __post_init__(self) -> None:
        a,b,c,d = self.bounds
        if (not all(math.isfinite(x) for x in self.bounds)
                or not -90 <= a < b <= 90 or not -180 <= c < d <= 180
                or not 5 <= self.minimum_stations <= self.maximum_stations <= 16
                or not 150 <= self.maximum_depth_km <= 200
                or not 0.2 <= self.coarse_step_deg <= 1
                or (b-a)*(d-c)/self.coarse_step_deg**2 > 10000
                or not 0 < self.maximum_rms_seconds <= 5
                or not 0 < self.maximum_gap_deg <= 360
                or not 0 < self.maximum_stability_km <= 100
                or not 1 <= self.seed_count <= 8):
            raise ValueError('invalid bounded location settings')


@dataclass(frozen=True)
class LocationReview:
    status: str
    reasons: tuple[str, ...]
    validation_status: str = "experimental_unvalidated"
    public_alert_eligible: bool = False
    latitude: float | None = None
    longitude: float | None = None
    depth_km: float | None = None
    origin_time: float | None = None
    rms_seconds: float | None = None
    station_count: int = 0
    phase_count: int = 0
    azimuthal_gap_deg: float | None = None
    alternative_spread_km: float | None = None
    station_removal_shift_km: float | None = None
    plane_wave_rms_seconds: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TravelTimes(Protocol):
    def predict(self, depth: Any, distance: Any, phases: np.ndarray) -> np.ndarray: ...


class TabulatedTravelTimes:
    def __init__(self, path: Path):
        with np.load(path, allow_pickle=False) as table:
            self._p = RegularGridInterpolator((table['depths_km'], table['distances_deg']),
                                             table['p_seconds'], bounds_error=False, fill_value=np.nan)
            self._s = RegularGridInterpolator((table['depths_km'], table['distances_deg']),
                                             table['s_seconds'], bounds_error=False, fill_value=np.nan)

    def predict(self, depth: Any, distance: Any, phases: np.ndarray) -> np.ndarray:
        z, d = np.broadcast_arrays(depth, distance)
        points = np.stack([z, d], axis=-1)
        return np.where(phases == 'P', self._p(points), self._s(points))


def _gap(lat: float, lon: float, stations: Sequence[PhaseArrival]) -> float:
    bearings = []
    for s in {p.station_id: p for p in stations}.values():
        a,b,dl = math.radians(lat), math.radians(s.latitude), math.radians(s.longitude-lon)
        bearings.append(math.degrees(math.atan2(math.sin(dl)*math.cos(b),
                        math.cos(a)*math.sin(b)-math.sin(a)*math.cos(b)*math.cos(dl))) % 360)
    bearings.sort()
    return max(b-a for a,b in zip(bearings, bearings[1:]+[bearings[0]+360], strict=True))


class ShadowLocator:
    def __init__(self, table: TravelTimes, settings: LocationSettings = LocationSettings()):
        self.table, self.settings = table, settings

    def review(self, observations: Sequence[PhaseArrival]) -> LocationReview:
        settings = self.settings
        if len(observations) > settings.maximum_stations*2:
            return LocationReview('rejected', ('observation_limit',))
        picks = sorted(observations, key=lambda p: (p.station_id, p.phase))
        keys = {(p.station_id, p.phase) for p in picks}
        if len(keys) != len(picks):
            return LocationReview('rejected', ('duplicate_station_phase',))
        if any(p.phase not in {'P', 'S'} or not p.station_id or
               not all(math.isfinite(v) for v in (p.latitude,p.longitude,p.time,p.sigma_seconds))
               or not (-90 <= p.latitude <= 90 and -180 <= p.longitude <= 180)
               or not 0.05 <= p.sigma_seconds <= 5 for p in picks):
            return LocationReview('rejected', ('invalid_arrival',))
        stations = {p.station_id for p in picks}
        if len(stations) > settings.maximum_stations:
            return LocationReview('rejected', ('station_limit',))
        if len(stations) < settings.minimum_stations:
            return LocationReview('insufficient_data', ('need_more_independent_stations',),
                                  station_count=len(stations), phase_count=len(picks))
        for station in stations:
            pair = {p.phase: p for p in picks if p.station_id == station}
            if len({(p.latitude,p.longitude) for p in pair.values()}) > 1:
                return LocationReview('rejected', ('inconsistent_station_coordinates',))
            if 'S' in pair and ('P' not in pair or pair['S'].time <= pair['P'].time):
                return LocationReview('rejected', ('unpaired_or_reversed_s',))
        reference = min(p.time for p in picks)
        fits = self._fits(picks, reference)
        if not fits:
            return LocationReview('rejected', ('no_finite_solution',))
        best, rms = fits[0]
        gap = _gap(best[0], best[1], picks)
        alternatives = [fit for fit, error in fits if error <= rms+0.5]
        spread = max(float(distance_deg(best[0],best[1],x[0],x[1]))*111.195 for x in alternatives)
        shifts = []
        # Four stations leave no residual redundancy in a P-only 4-parameter fit.
        # Refuse to call such a station-removal check stable.
        if len(stations) >= settings.minimum_stations+1:
            for station in sorted(stations):
                reduced = [p for p in picks if p.station_id != station]
                trials = self._fits(reduced, reference)
                if not trials or trials[0][1] > settings.maximum_rms_seconds:
                    shifts.append(float('inf'))
                else:
                    x = trials[0][0]
                    shifts.append(float(distance_deg(best[0],best[1],x[0],x[1]))*111.195)
        shift = max(shifts) if shifts else None
        p_picks = [p for p in picks if p.phase == 'P']
        plane = self._plane_rms(p_picks)
        reasons = []
        if rms > settings.maximum_rms_seconds:
            reasons.append('incoherent_arrivals')
        if gap > settings.maximum_gap_deg:
            reasons.append('poor_azimuthal_coverage')
        a,b,c,d = settings.bounds
        if min(best[0]-a,b-best[0],best[1]-c,d-best[1]) < 0.1:
            reasons.append('search_boundary')
        if best[2] < 1 or best[2] > settings.maximum_depth_km-1:
            reasons.append('depth_search_boundary')
        if spread > settings.maximum_stability_km:
            reasons.append('multiple_location_solutions')
        if shift is None:
            reasons.append('insufficient_station_removal_redundancy')
        elif shift > settings.maximum_stability_km:
            reasons.append('unstable_without_one_station')
        if len(p_picks) == len(picks):
            reasons.append('p_only_depth_ambiguous')
            # A flat wavefront may be distant; this veto is deliberately
            # conservative and is not a calibrated teleseism classifier.
            if plane is not None and plane <= max(1., rms*1.25):
                reasons.append('distant_wavefront_not_excluded')
        return LocationReview(
            'ambiguous' if reasons else 'experimental_consistent', tuple(reasons),
            latitude=float(best[0]), longitude=float(best[1]), depth_km=float(best[2]),
            origin_time=float(best[3]+reference), rms_seconds=rms,
            station_count=len(stations), phase_count=len(picks), azimuthal_gap_deg=gap,
            alternative_spread_km=spread,
            station_removal_shift_km=shift if shift is not None and math.isfinite(shift) else None,
            plane_wave_rms_seconds=plane,
        )

    @staticmethod
    def _plane_rms(picks: Sequence[PhaseArrival]) -> float | None:
        if len(picks) < 5:
            return None
        lat, lon = np.array([p.latitude for p in picks]), np.array([p.longitude for p in picks])
        design = np.column_stack([np.ones(len(picks)), (lon-lon.mean())*math.cos(math.radians(float(lat.mean()))), lat-lat.mean()])
        times = np.array([p.time-picks[0].time for p in picks])
        fit = np.linalg.lstsq(design, times, rcond=None)[0]
        return float(np.sqrt(np.mean((design@fit-times)**2)))

    def _fits(self, picks: Sequence[PhaseArrival], reference: float) -> list[tuple[np.ndarray, float]]:
        s = self.settings
        a,b,c,d = s.bounds
        slat,slon = np.array([p.latitude for p in picks]), np.array([p.longitude for p in picks])
        phases = np.array([p.phase for p in picks])
        observed = np.array([p.time-reference for p in picks])
        sigma = np.array([p.sigma_seconds for p in picks])
        lat,lon,depth = np.meshgrid(np.arange(a,b+1e-6,s.coarse_step_deg),
            np.arange(c,d+1e-6,s.coarse_step_deg), [5.,30.,90.,150.,s.maximum_depth_km], indexing='ij')
        nodes = np.column_stack([lat.ravel(),lon.ravel(),depth.ravel()])
        travel = self.table.predict(nodes[:,2,None], distance_deg(nodes[:,0,None],nodes[:,1,None],slat,slon), phases)
        finite = np.isfinite(travel).all(axis=1)
        origins = np.median(np.where(np.isfinite(travel), observed-travel, 0), axis=1)
        loss = np.where(finite, np.mean(((observed-travel-origins[:,None])/sigma)**2,axis=1), np.inf)
        seeds: list[np.ndarray] = []
        for i in np.argsort(loss):
            if not np.isfinite(loss[i]):
                break
            node = nodes[i]
            if any(float(distance_deg(node[0],node[1],x[0],x[1])) < 1 and abs(node[2]-x[2]) < 40 for x in seeds):
                continue
            seeds.append(np.r_[node, origins[i]])
            if len(seeds) >= s.seed_count:
                break

        def residual(x: np.ndarray) -> np.ndarray:
            predicted = self.table.predict(x[2], distance_deg(x[0],x[1],slat,slon), phases)
            return np.nan_to_num((predicted+x[3]-observed)/sigma, nan=1e6, posinf=1e6, neginf=-1e6)

        results = []
        for seed in seeds:
            fitted = least_squares(residual, seed, bounds=([a,c,0.,-1800.],[b,d,s.maximum_depth_km,120.]),
                                   loss='soft_l1', max_nfev=100, x_scale=[1.,1.,50.,10.])
            predicted = self.table.predict(fitted.x[2],distance_deg(fitted.x[0],fitted.x[1],slat,slon),phases)
            rms = float(np.sqrt(np.mean((predicted+fitted.x[3]-observed)**2)))
            if fitted.success and math.isfinite(rms):
                results.append((fitted.x, rms))
        return sorted(results, key=lambda item: item[1])


@dataclass
class _Pending:
    created_at: float
    picks: dict[tuple[str, str], PhaseArrival]
    last_review_at: float = float('-inf')
    review: LocationReview | None = None
    dirty: bool = False


class ProgressiveLocationReview:
    """Bounded event-local updates, called by an existing background worker.

    No 270 s magnitude timer, threads, alert dispatch, catalogue coordinates or
    cross-event pooling. The caller associates phases with an event and keeps
    this CPU work off the SeedLink reader. Revisions remain experimental.
    """
    def __init__(self, locator: ShadowLocator, *, maximum_events: int = 16,
                 ttl_seconds: float = 240., minimum_interval_seconds: float = 5.):
        if not 1 <= maximum_events <= 64 or ttl_seconds <= 0 or minimum_interval_seconds <= 0:
            raise ValueError('invalid bounded review settings')
        self.locator = locator
        self.maximum_events = maximum_events
        self.ttl = ttl_seconds
        self.interval = minimum_interval_seconds
        self._events: OrderedDict[str, _Pending] = OrderedDict()

    @property
    def pending_count(self) -> int:
        return len(self._events)

    def update(self, event_id: str, arrivals: Sequence[PhaseArrival], *, now: float) -> LocationReview:
        if not event_id or not math.isfinite(now):
            return LocationReview('rejected', ('invalid_event_clock',))
        for key in list(self._events):
            if now-self._events[key].created_at > self.ttl:
                del self._events[key]
        if len(arrivals) > self.locator.settings.maximum_stations*2:
            return LocationReview('rejected', ('observation_limit',))
        if any(not math.isfinite(p.time) or not -5 <= now-p.time <= self.ttl for p in arrivals):
            return LocationReview('rejected', ('stale_or_future_arrival',))
        if len({(p.station_id,p.phase) for p in arrivals}) != len(arrivals):
            return LocationReview('rejected', ('duplicate_station_phase',))
        pending = self._events.get(event_id)
        if pending is None:
            if len(self._events) >= self.maximum_events:
                self._events.popitem(last=False)
            pending = _Pending(now, {})
            self._events[event_id] = pending
        updated = dict(pending.picks)
        updated.update({(p.station_id,p.phase):p for p in arrivals})
        if len(updated) > self.locator.settings.maximum_stations*2:
            return LocationReview('rejected', ('observation_limit',))
        changed = updated != pending.picks
        pending.picks = updated
        pending.dirty = pending.dirty or changed
        if pending.review is not None and not pending.dirty:
            return pending.review
        if now-pending.last_review_at < self.interval:
            return LocationReview('pending', ('review_rate_limited',))
        pending.review = self.locator.review(list(pending.picks.values()))
        pending.last_review_at = now
        pending.dirty = False
        return pending.review
