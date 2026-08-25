"""Genera evidencia fechada de canales colombianos y transporte EarthScope."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import socket
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
from obspy import read  # type: ignore[import-untyped]

STATION_URL = "https://service.earthscope.org/fdsnws/station/1/query"
DATASELECT_URL = "https://service.earthscope.org/fdsnws/dataselect/1/query"
SEEDLINK_HOST = "rtserve.earthscope.org"
STATIONS = ("ARGC", "CRJC", "HEL", "LCBC", "RUS", "SMAR")


def _utc(value: str | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _tcp_probe(port: int, timeout: float) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        with socket.create_connection((SEEDLINK_HOST, port), timeout=timeout):
            return {
                "port": port,
                "reachable": True,
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            }
    except OSError as exc:
        return {
            "port": port,
            "reachable": False,
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            "error": type(exc).__name__,
        }


def _active_channels(session: requests.Session, timeout: float) -> dict[str, dict[str, Any]]:
    response = session.get(
        STATION_URL,
        params={
            "net": "CM",
            "sta": ",".join(STATIONS),
            "loc": "00",
            "cha": "HHZ",
            "level": "channel",
            "format": "text",
            "includecomments": "false",
            "nodata": "404",
        },
        timeout=timeout,
    )
    response.raise_for_status()
    active: dict[str, dict[str, Any]] = {}
    for line in response.text.splitlines():
        if not line or line.startswith("#"):
            continue
        fields = line.split("|")
        if len(fields) < 17 or fields[16].strip():
            continue
        station = fields[1]
        active[station] = {
            "network": fields[0],
            "station": station,
            "location": fields[2],
            "channel": fields[3],
            "latitude": float(fields[4]),
            "longitude": float(fields[5]),
            "elevation_m": float(fields[6]),
            "sample_rate_hz": float(fields[14]),
            "epoch_start": fields[15],
            "epoch_end": None,
        }
    return active


def _recent_data(
    session: requests.Session,
    station: str,
    start: datetime,
    end: datetime,
    observed_at: datetime,
    timeout: float,
) -> dict[str, Any]:
    response = session.get(
        DATASELECT_URL,
        params={
            "net": "CM",
            "sta": station,
            "loc": "00",
            "cha": "HHZ",
            "start": _iso(start),
            "end": _iso(end),
            "nodata": "204",
        },
        timeout=timeout,
    )
    result: dict[str, Any] = {
        "http_status": response.status_code,
        "requested_start": _iso(start),
        "requested_end": _iso(end),
        "bytes": len(response.content),
        "has_recent_data": response.status_code == 200 and bool(response.content),
    }
    if not result["has_recent_data"]:
        return result
    stream = read(io.BytesIO(response.content), format="MSEED")
    latest_end = max(trace.stats.endtime.datetime.replace(tzinfo=timezone.utc) for trace in stream)
    result.update(
        {
            "trace_count": len(stream),
            "latest_sample_time": _iso(latest_end),
            "archive_freshness_seconds": round((observed_at - latest_end).total_seconds(), 3),
            "latest_vs_requested_end_seconds": round((end - latest_end).total_seconds(), 3),
            "sha256": hashlib.sha256(response.content).hexdigest(),
        }
    )
    return result


def build_report(observed_at: datetime, timeout: float) -> dict[str, Any]:
    query_end = observed_at - timedelta(minutes=2)
    query_start = query_end - timedelta(minutes=5)
    with requests.Session() as session:
        channels = _active_channels(session, timeout)
        stations = []
        for station in STATIONS:
            station_report = channels.get(station, {"station": station, "metadata_active": False})
            station_report["metadata_active"] = station in channels
            station_report["archive_probe"] = _recent_data(
                session, station, query_start, query_end, observed_at, timeout
            )
            stations.append(station_report)
    return {
        "schema_version": 1,
        "observed_at": _iso(observed_at),
        "purpose": "Sprint 1 station/channel and acquisition-lag evidence",
        "network": "CM",
        "provider": "EarthScope",
        "seedlink_server": f"{SEEDLINK_HOST}:18000",
        "archive_probe_delay_seconds": 120,
        "sources": {
            "station_metadata": STATION_URL,
            "recent_waveforms": DATASELECT_URL,
            "seedlink_documentation": "https://docs.earthscope.org/service/seedlink",
        },
        "transport_probes": [_tcp_probe(port, timeout) for port in (18000, 18500, 443)],
        "stations": stations,
        "limitations": [
            "FDSN recent-data presence verifies archive arrival, not SeedLink packet latency.",
            "TCP reachability is a point-in-time probe and does not guarantee continuity.",
            "Station selection must be revalidated before every field or public pilot.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--at", help="UTC ISO timestamp; defaults to now")
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build_report(_utc(args.at), args.timeout)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
