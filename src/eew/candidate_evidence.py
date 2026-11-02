"""Conservative candidate metadata and retrospective catalogue consistency.

Passing a travel-time screen is not scientific validation or an alert policy.
STA/LTA peaks may follow P or S; they are never re-labelled as first P picks.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

from eew.models import EarthquakeCandidate, OfficialReport


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError, OverflowError):
        return None


def public_candidate_location(payload: dict[str, Any]) -> dict[str, Any]:
    """Never publish the station centroid as an earthquake epicentre."""
    latitude = _number(payload.get("estimated_latitude"))
    longitude = _number(payload.get("estimated_longitude"))
    centroid = None
    if latitude is not None and longitude is not None and -90 <= latitude <= 90 and -180 <= longitude <= 180:
        centroid = {"latitude": latitude, "longitude": longitude,
                    "method": "triggering_station_centroid", "is_epicenter": False}
    # There is currently no validated regional solution in the deployed beta.
    # Keep the raw hypothesis separately; a catalogue has its own official event.
    return {"latitude": None, "longitude": None, "depth_km": None,
            "location_method": "unlocated", "confirmation_status": "unconfirmed",
            "time_reference": "detection_not_origin", "station_centroid": centroid,
            "place": "Señal multiestación sin epicentro confirmado",
            "review_status": "candidato técnico · sismo no confirmado"}


@lru_cache(maxsize=1)
def _travel_model() -> Any:
    from obspy.taup import TauPyModel

    return TauPyModel(model="iasp91")


@lru_cache(maxsize=4096)
def _arrival_times(depth: float, distance: float) -> tuple[float, ...]:
    arrivals = _travel_model().get_travel_times(
        source_depth_in_km=depth, distance_in_degree=distance,
        phase_list=["P", "p", "Pn", "Pg", "S", "s", "Sn", "Sg",
                    "Pdiff", "PKP", "PKIKP", "SKS", "SKIKS"],
    )
    return tuple(float(item.time) for item in arrivals if math.isfinite(float(item.time)))


def _epoch(value: Any) -> float:
    date = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if date.tzinfo is None:
        date = date.replace(tzinfo=timezone.utc)
    return date.timestamp()


def catalogue_phase_consistent(candidate: EarthquakeCandidate, report: OfficialReport) -> bool:
    """Veto temporal/centroid coincidences that do not explain the whole quorum.

    A 15 s retrospective peak tolerance is a necessary consistency check, not
    a calibrated classifier. Missing evidence fails closed. No network calls.
    """
    stations = {station.station_id: station for station in candidate.stations}
    if len(stations) != len(candidate.stations) or len(stations) < max(3, candidate.required_stations):
        return False
    depth = _number(report.depth_km)
    lat, lon = _number(report.latitude), _number(report.longitude)
    if depth is None or not 0 <= depth <= 800 or lat is None or lon is None:
        return False
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return False
    try:
        origin = _epoch(report.origin_time)
        for station in stations.values():
            slat, slon = _number(station.latitude), _number(station.longitude)
            if slat is None or slon is None or not (-90 <= slat <= 90 and -180 <= slon <= 180):
                return False
            a, b = math.radians(lat), math.radians(slat)
            hav = math.sin((b - a) / 2) ** 2 + math.cos(a) * math.cos(b) * math.sin(math.radians(slon - lon) / 2) ** 2
            distance = math.degrees(2 * math.asin(math.sqrt(min(1.0, max(0.0, hav)))))
            observed = _epoch(station.trigger_time) - origin
            arrivals = _arrival_times(round(depth, 1), round(distance, 3))
            if observed < 0 or not arrivals or min(abs(observed - arrival) for arrival in arrivals) > 15:
                return False
    except (ValueError, TypeError, OverflowError, OSError):
        return False
    return True
