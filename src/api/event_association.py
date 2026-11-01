"""Conservative catalogue association, never an alert or magnitude policy."""

from __future__ import annotations

import math
from collections import Counter
from datetime import datetime, timezone
from typing import Any

MAX_TIME_SECONDS = 45
MAX_DISTANCE_KM = 40
MAX_DEPTH_DIFFERENCE_KM = 60


def _time(value: Any) -> float | None:
    try:
        date = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        return date.timestamp()
    except (ValueError, TypeError, OverflowError):
        return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (ValueError, TypeError):
        return None


def _matches(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if not left.get("source_id") or not right.get("source_id"):
        return False
    if left["source_id"] == right["source_id"]:
        return False
    if any(
        e.get("preliminary")
        or e.get("type") != "official_report_update"
        or str(e.get("event_id", "")).startswith("drill-")
        for e in (left, right)
    ):
        return False
    times = [_time(e.get("origin_time")) for e in (left, right)]
    if any(t is None for t in times):
        return False
    if abs(float(times[0]) - float(times[1])) > MAX_TIME_SECONDS:  # type: ignore[arg-type]
        return False
    coords = [_number(e.get(k)) for e in (left, right) for k in ("latitude", "longitude")]
    if any(c is None for c in coords):
        return False
    lat1, lon1, lat2, lon2 = [float(c) for c in coords]  # type: ignore[arg-type]
    if not all(abs(lat) <= 90 for lat in (lat1, lat2)) or not all(
        abs(lon) <= 180 for lon in (lon1, lon2)
    ):
        return False
    a = math.sin(math.radians(lat2 - lat1) / 2) ** 2 + (
        math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    )
    if 6371 * 2 * math.asin(math.sqrt(min(1, max(0, a)))) > MAX_DISTANCE_KM:
        return False
    depths = [_number(e.get("depth_km")) for e in (left, right)]
    return not (
        depths[0] is not None
        and depths[1] is not None
        and abs(depths[0] - depths[1]) > MAX_DEPTH_DIFFERENCE_KM
    )


def associate_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Complete-link, unique-source groups; ambiguous components stay separate.

    Keep a source ID as canonical ID for backwards compatibility, never average
    incompatible magnitude scales. No persistent scientific event identity implied.
    """
    latest: dict[str, dict[str, Any]] = {}
    for event in events:
        event_id = str(event.get("event_id") or "")
        if not event_id:
            continue
        previous = latest.get(event_id)
        if previous is None or (_time(event.get("updated_at")) or 0) > (
            _time(previous.get("updated_at")) or 0
        ):
            latest[event_id] = event
    ordered = sorted(
        latest.values(), key=lambda e: (_time(e.get("origin_time")) or 0, str(e["event_id"]))
    )
    adjacency: list[set[int]] = [set() for _ in ordered]
    for i, left in enumerate(ordered):
        left_time = _time(left.get("origin_time"))
        for j in range(i + 1, len(ordered)):
            right_time = _time(ordered[j].get("origin_time"))
            if left_time is not None and right_time is not None:
                if right_time - left_time > MAX_TIME_SECONDS:
                    break
            if _matches(left, ordered[j]):
                adjacency[i].add(j)
                adjacency[j].add(i)
    seen: set[int] = set()
    groups: list[list[dict[str, Any]]] = []
    for i in range(len(ordered)):
        if i in seen:
            continue
        component: set[int] = set()
        pending = [i]
        while pending:
            node = pending.pop()
            if node in component:
                continue
            component.add(node)
            pending.extend(adjacency[node] - component)
        seen.update(component)
        sources = Counter(ordered[n].get("source_id") for n in component)
        unambiguous = max(sources.values()) == 1 and all(
            component - {n} <= adjacency[n] for n in component
        )
        if unambiguous:
            groups.append([ordered[n] for n in sorted(component)])
        else:
            groups.extend([[ordered[n]] for n in sorted(component)])
    result: list[dict[str, Any]] = []
    priority = {"sgc_colombia": 0, "usgs_global": 1, "emsc_global": 2}
    for group in groups:
        reports = sorted(
            group, key=lambda e: (priority.get(str(e.get("source_id")), 10), str(e["event_id"]))
        )
        primary = dict(reports[0])
        # Preserve full original reports, including attribution, time and scales.
        primary["source_reports"] = [dict(r) for r in reports]
        primary["related_event_ids"] = [r["event_id"] for r in reports]
        primary["association_method"] = (
            "time_distance_depth_v1" if len(reports) > 1 else "single_source"
        )
        result.append(primary)
    return sorted(
        result, key=lambda e: (_time(e.get("origin_time")) or 0, str(e["event_id"])), reverse=True
    )
