#!/usr/bin/env python3
"""Contrasta los candidatos de replay con el reporte oficial rapido del SGC."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from eew.config import Settings  # noqa: E402
from eew.models import EarthquakeCandidate, StationTrigger  # noqa: E402
from eew.official import OfficialApiClient, load_sources, match_report  # noqa: E402


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", default=str(PROJECT_ROOT / "data/replay/results-sprint2"))
    parser.add_argument(
        "--output", default=str(PROJECT_ROOT / "data/calibration/sgc-association.json")
    )
    parser.add_argument("--timeout", type=float, default=20)
    args = parser.parse_args()

    settings = Settings.load(PROJECT_ROOT / "config.json")
    manifest = json.loads((PROJECT_ROOT / "data/replay/manifest.json").read_text("utf-8"))
    cases = {item["id"]: item for item in manifest["cases"]}
    coordinates = {
        f"{station.network}.{station.station}": (station.latitude, station.longitude)
        for provider in settings.seedlink.providers
        for station in provider.stations
    }
    source = next(item for item in load_sources(PROJECT_ROOT / settings.official_reports.sources_file)
                  if item.id == "sgc_colombia")
    rows: list[dict[str, Any]] = []
    for path in sorted(Path(args.results).glob("*.json")):
        case = cases[path.stem]
        if case["kind"] != "historical_earthquake":
            continue
        replay = json.loads(path.read_text("utf-8"))
        candidate_data = replay["candidates"][0] if replay["candidates"] else None
        if candidate_data is None:
            rows.append({"case_id": path.stem, "status": "no_candidate"})
            continue
        detected = parse_time(candidate_data["detected_at"])
        station_rows = []
        for station_id in candidate_data["stations"]:
            matching = [item for item in replay["triggers"] if item["station_id"] == station_id
                        and parse_time(item["trigger_time"]) <= detected]
            trigger = max(matching, key=lambda item: item["trigger_time"])
            lat, lon = coordinates[station_id]
            station_rows.append(StationTrigger(
                provider_id="sgc-colombia", country_code="CO", zone_id="CO",
                station_id=station_id, stream_id=trigger["stream_id"],
                trigger_time=trigger["trigger_time"], received_at=trigger["trigger_time"],
                sta_lta_ratio=trigger["sta_lta_ratio"], latitude=lat, longitude=lon,
                packet_lag_seconds=0.0,
            ))
        latitude = sum(item.latitude or 0 for item in station_rows) / len(station_rows)
        longitude = sum(item.longitude or 0 for item in station_rows) / len(station_rows)
        candidate = EarthquakeCandidate(
            event_id=candidate_data["replay_event_id"], type="earthquake_candidate",
            status="unlocated_unreviewed", zone_id="CO", country_code="CO",
            country_codes=("CO",), detected_at=candidate_data["detected_at"],
            coincidence_window_seconds=settings.coincidence.window_seconds,
            required_stations=settings.coincidence.minimum_stations,
            station_count=len(station_rows), stations=tuple(station_rows),
            estimated_latitude=latitude, estimated_longitude=longitude,
        )
        origin = parse_time(case["origin_time"])
        reports = OfficialApiClient(source, args.timeout).fetch(
            origin - timedelta(minutes=5), origin + timedelta(minutes=5)
        )
        matches = [matched for report in reports
                   if (matched := match_report(candidate, report, settings.official_reports))]
        preferred = min(matches, key=lambda item: (
            item.origin_time_delta_seconds or 0,
            item.distance_from_station_centroid_km or 0,
        ), default=None)
        rows.append({
            "case_id": path.stem,
            "candidate_detected_at": candidate.detected_at,
            "expected_origin_time": case["origin_time"],
            "expected_magnitude": case["magnitude"],
            "queried_reports": len(reports),
            "status": "matched" if preferred else "not_in_rapid_feed",
            "matched_report": asdict(preferred) if preferred else None,
            "note": None if preferred else (
                "El feed quincenal rapido del SGC no es un catalogo historico permanente."
            ),
        })
    output = {
        "schema_version": 1,
        "mode": "offline_replay_to_live_official_feed_validation",
        "scientific_validation": False,
        "source_id": source.id,
        "source_endpoint": source.endpoint,
        "association_limits": {
            "origin_time_seconds": settings.official_reports.max_origin_time_delta_seconds,
            "station_centroid_km": settings.official_reports.max_distance_km,
        },
        "cases": rows,
    }
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", "utf-8")
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
