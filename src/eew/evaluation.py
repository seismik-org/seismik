"""Metricas reproducibles para replay en modo sombra."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def evaluate_case(
    case: dict[str, Any],
    replay: dict[str, Any],
    detection_window_seconds: float = 120.0,
) -> dict[str, Any]:
    candidates = replay["candidates"]
    is_event = case["kind"] == "historical_earthquake"
    if not is_event:
        return {
            "case_id": case["id"],
            "kind": case["kind"],
            "detected": False,
            "detection_latency_seconds": None,
            "candidate_count": len(candidates),
            "false_candidate_count": len(candidates),
            "duplicate_candidate_count": 0,
        }

    origin = parse_utc(case["origin_time"])
    deltas = [
        (parse_utc(candidate["detected_at"]) - origin).total_seconds()
        for candidate in candidates
    ]
    in_window = [delta for delta in deltas if 0 <= delta <= detection_window_seconds]
    outside = [delta for delta in deltas if delta < 0 or delta > detection_window_seconds]
    return {
        "case_id": case["id"],
        "kind": case["kind"],
        "detected": bool(in_window),
        "detection_latency_seconds": round(min(in_window), 3) if in_window else None,
        "candidate_count": len(candidates),
        "false_candidate_count": len(outside),
        "duplicate_candidate_count": max(0, len(in_window) - 1),
    }


def summarize(case_results: list[dict[str, Any]]) -> dict[str, Any]:
    events = [item for item in case_results if item["kind"] == "historical_earthquake"]
    noise = [item for item in case_results if item["kind"] != "historical_earthquake"]
    latencies = [
        item["detection_latency_seconds"]
        for item in events
        if item["detection_latency_seconds"] is not None
    ]
    missed = sum(not item["detected"] for item in events)
    noise_false = sum(item["false_candidate_count"] for item in noise)
    event_false = sum(item["false_candidate_count"] for item in events)
    duplicates = sum(item["duplicate_candidate_count"] for item in events)
    mean_latency = sum(latencies) / len(latencies) if latencies else 999.0
    score = missed * 10_000 + noise_false * 1_000 + event_false * 100 + duplicates * 50
    score += mean_latency
    return {
        "historical_cases": len(events),
        "historical_detected": len(events) - missed,
        "missed_historical": missed,
        "noise_false_candidates": noise_false,
        "historical_out_of_window_candidates": event_false,
        "duplicate_in_window_candidates": duplicates,
        "mean_detection_latency_seconds": round(mean_latency, 3) if latencies else None,
        "engineering_score": round(score, 3),
    }
