"""Synthetic gate inputs for software tests; never scientific validation evidence."""
from datetime import datetime, timezone


def eligible_candidate(event_id="candidate-1", zone_id="andes"):
    return {
        "event_id": event_id, "type": "earthquake_candidate", "zone_id": zone_id,
        "estimated_latitude": 5.65, "estimated_longitude": -74.05,
        "magnitude_estimate": 6.5, "magnitude_estimate_status": "validated_preliminary",
        "association_quality": {
            "status": "validated_consistent", "validation_status": "validated",
            "latitude": 5.65, "longitude": -74.05, "depth_km": 20,
            "origin_time": datetime.now(timezone.utc).isoformat(),
            "rms_seconds": 1, "horizontal_uncertainty_km": 20, "azimuthal_gap_deg": 180,
            "used_station_ids": ["XX.A", "XX.B", "XX.C", "XX.D"],
        },
    }
