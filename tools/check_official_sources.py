#!/usr/bin/env python3
"""Smoke test en vivo de las fuentes configuradas (no forma parte de pytest)."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from eew.official import OfficialApiClient, load_sources  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Valida APIs oficiales configuradas")
    parser.add_argument("--sources", default=str(PROJECT_ROOT / "official_sources.json"))
    parser.add_argument("--hours", type=float, default=24)
    parser.add_argument("--timeout", type=float, default=20)
    args = parser.parse_args()

    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=args.hours)
    failures = 0
    for source in load_sources(args.sources):
        if not source.enabled:
            continue
        try:
            reports = OfficialApiClient(source, args.timeout).fetch(start, end)
            newest = max(reports, key=lambda item: item.origin_time, default=None)
            suffix = (
                f" newest={newest.official_event_id} time={newest.origin_time}"
                if newest else ""
            )
            print(f"OK   {source.id}: reports={len(reports)}{suffix}")
        except Exception as exc:
            failures += 1
            print(f"FAIL {source.id}: {type(exc).__name__}: {exc}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
