"""Compara perfiles STA/LTA contra el corpus Sprint 1."""

from __future__ import annotations

import argparse
import itertools
import json
import logging
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from eew.config import Settings
from eew.evaluation import evaluate_case, summarize
from eew.replay import MiniSeedReplay


def _paths(manifest_path: Path, case: dict[str, Any]) -> list[Path]:
    return [manifest_path.parent / item["path"] for item in case["waveforms"]]


def _profile_grid() -> list[dict[str, Any]]:
    windows = ((0.5, 10.0), (0.8, 15.0), (1.0, 20.0))
    return [
        {
            "sta_seconds": sta,
            "lta_seconds": lta,
            "trigger_on": trigger_on,
            "trigger_off": 1.2,
            "minimum_stations": minimum_stations,
            "coincidence_window_seconds": coincidence_window,
        }
        for (sta, lta), trigger_on, minimum_stations, coincidence_window in itertools.product(
            windows, (4.0, 5.0, 6.0), (2, 3, 4), (10.0, 15.0)
        )
    ]


def evaluate_profile(
    settings: Settings,
    manifest_path: Path,
    manifest: dict[str, Any],
    profile: dict[str, Any],
    chunk_seconds: float,
) -> dict[str, Any]:
    logging.getLogger("eew.processor").setLevel(logging.ERROR)
    detection_overrides = {
        "sta_seconds": profile["sta_seconds"],
        "lta_seconds": profile["lta_seconds"],
        "trigger_on": profile["trigger_on"],
        "trigger_off": profile["trigger_off"],
    }
    detection = replace(
        settings.detection,
        network_profiles={"CM.HHZ": detection_overrides},
    )
    coincidence = replace(
        settings.coincidence,
        minimum_stations=profile["minimum_stations"],
        minimum_located_stations=profile["minimum_stations"],
        window_seconds=profile["coincidence_window_seconds"],
    )
    subscriptions = tuple(
        station
        for provider in settings.seedlink.providers
        if provider.enabled
        for station in provider.stations
        if station.network == "CM"
    )
    cases = []
    for case in manifest["cases"]:
        replay = MiniSeedReplay(subscriptions, detection, coincidence).run(
            _paths(manifest_path, case), chunk_seconds
        )
        cases.append(evaluate_case(case, replay))
    return {
        "profile": profile,
        "cases": cases,
        "summary": summarize(cases),
    }


def main() -> None:
    logging.getLogger("eew.processor").setLevel(logging.ERROR)
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("config.json"))
    parser.add_argument("--manifest", type=Path, default=Path("data/replay/manifest.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--chunk-seconds", type=float, default=5.0)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--only-minimum-stations", type=int)
    args = parser.parse_args()
    settings = Settings.load(args.config)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    profiles = _profile_grid()
    if args.only_minimum_stations is not None:
        profiles = [
            item
            for item in profiles
            if item["minimum_stations"] == args.only_minimum_stations
        ]
    if args.limit:
        profiles = profiles[: args.limit]
    with ProcessPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = [
            executor.submit(
                evaluate_profile,
                settings,
                args.manifest,
                manifest,
                profile,
                args.chunk_seconds,
            )
            for profile in profiles
        ]
        evaluations = [future.result() for future in futures]
    evaluations.sort(key=lambda item: item["summary"]["engineering_score"])
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "mode": "shadow_engineering_calibration",
        "not_scientifically_validated": True,
        "ranking_policy": {
            "missed_historical_weight": 10000,
            "noise_false_candidate_weight": 1000,
            "historical_out_of_window_weight": 100,
            "duplicate_in_window_weight": 50,
            "tie_breaker": "mean detection latency seconds",
        },
        "base_detection": asdict(settings.detection),
        "evaluated_profiles": len(evaluations),
        "recommended_for_shadow_review": evaluations[0] if evaluations else None,
        "ranked_results": evaluations,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
