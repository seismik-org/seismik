"""Evidence requirements for user-facing SeedLink alarms, not personal diagnostics."""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any


def candidate_alarm_reason(event: dict[str, Any], *, now: datetime | None = None) -> str:
    if event.get("type") != "earthquake_candidate":
        return "not_seedlink"
    quality = event.get("association_quality")
    if not isinstance(quality, dict):
        return "missing_physical_association"
    if quality.get("status") not in {"experimental_consistent", "validated_consistent"}:
        return "association_" + str(quality.get("reason", "inconsistent"))[:128]
    if quality.get("validation_status") != "validated":
        return "association_not_validated"
    if quality.get("status") != "validated_consistent":
        return "inconsistent_association"
    if event.get("magnitude_estimate_status") != "validated_preliminary":
        return "missing_validated_rapid_magnitude"
    try:
        magnitude = float(event["magnitude_estimate"])
        lat, lon, depth = (float(quality[key]) for key in ("latitude", "longitude", "depth_km"))
        rms = float(quality["rms_seconds"])
        uncertainty = float(quality["horizontal_uncertainty_km"])
        gap = float(quality["azimuthal_gap_deg"])
        origin = datetime.fromisoformat(str(quality["origin_time"]).replace("Z", "+00:00"))
        if origin.tzinfo is None:
            return "invalid_origin_time"
        age = ((now or datetime.now(timezone.utc)) - origin).total_seconds()
    except (ValueError, TypeError, KeyError):
        return "incomplete_source_solution"
    if not all(math.isfinite(v) for v in (magnitude, lat, lon, depth, rms, uncertainty, gap, age)):
        return "non_finite_source_solution"
    if not (-2 <= magnitude <= 10 and -90 <= lat <= 90 and -180 <= lon <= 180 and 0 <= depth <= 800):
        return "invalid_source_solution"
    if not (0 <= rms <= 2.5 and 0 <= uncertainty <= 40 and 0 <= gap <= 240):
        return "source_uncertainty_too_large"
    used = quality.get("used_station_ids", [])
    if not isinstance(used, (list, tuple)) or len(set(used)) < 4:
        return "insufficient_independent_stations"
    if not 0 <= age <= 60:
        return "source_solution_not_fresh"
    return "eligible"
