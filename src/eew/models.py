from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class StationTrigger:
    provider_id: str
    country_code: str
    zone_id: str
    station_id: str
    stream_id: str
    trigger_time: str
    received_at: str
    sta_lta_ratio: float
    latitude: float | None = None
    longitude: float | None = None
    packet_lag_seconds: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EarthquakeCandidate:
    event_id: str
    type: str
    status: str
    zone_id: str
    country_code: str | None
    country_codes: tuple[str, ...]
    detected_at: str
    coincidence_window_seconds: float
    required_stations: int
    station_count: int
    stations: tuple[StationTrigger, ...]
    estimated_latitude: float | None = None
    estimated_longitude: float | None = None

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["stations"] = [station.to_dict() for station in self.stations]
        return result


@dataclass(frozen=True)
class OfficialReport:
    source_id: str
    agency: str
    jurisdiction: str
    official_event_id: str
    origin_time: str
    updated_at: str | None
    latitude: float
    longitude: float
    depth_km: float | None
    magnitude: float | None
    magnitude_type: str | None
    place: str | None
    review_status: str | None
    official_url: str
    attribution: str | None = None
    tsunami: bool | None = None
    felt: str | None = None
    distance_from_station_centroid_km: float | None = None
    origin_time_delta_seconds: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OfficialReportUpdate:
    event_id: str
    candidate_event_id: str
    type: str
    status: str
    matched_at: str
    preferred_report: OfficialReport
    reports: tuple[OfficialReport, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["preferred_report"] = self.preferred_report.to_dict()
        result["reports"] = [report.to_dict() for report in self.reports]
        return result
