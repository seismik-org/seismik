"""Descarga fixtures MiniSEED publicos y genera su manifiesto verificable."""

from __future__ import annotations

import hashlib
import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
from obspy import Stream, read  # type: ignore[import-untyped]

DATASELECT_URLS = (
    "https://service.earthscope.org/fdsnws/dataselect/1/query",
    "https://sismo.sgc.gov.co:8443/fdsnws/dataselect/1/query",
)
STATIONS = (
    "ARGC", "CAP2", "CRJC", "FLO2", "HEL", "LCBC", "MAP", "OCA",
    "PRA", "PRV", "RUS", "SJC", "SMAR", "TUM", "URI",
)
OUTPUT_DIR = Path("data/replay")
CASES: tuple[dict[str, Any], ...] = (
    {
        "id": "co-2026-08-10-m7.4",
        "kind": "historical_earthquake",
        "origin_time": "2026-08-10T12:34:28.125Z",
        "magnitude": 7.4,
        "place": "5 km S of San Jose del Palmar, Colombia",
        "official_event_id": "us6000tjl2",
        "official_url": "https://earthquake.usgs.gov/earthquakes/eventpage/us6000tjl2",
        "seconds_before": 120,
        "seconds_after": 360,
    },
    {
        "id": "co-2023-08-17-m6.1",
        "kind": "historical_earthquake",
        "origin_time": "2023-08-17T17:04:48.770Z",
        "magnitude": 6.1,
        "place": "10 km E of El Calvario, Colombia",
        "official_event_id": "us7000kp2i",
        "official_url": "https://earthquake.usgs.gov/earthquakes/eventpage/us7000kp2i",
        "seconds_before": 120,
        "seconds_after": 360,
    },
    {
        "id": "co-2023-08-27-m5.7",
        "kind": "historical_earthquake",
        "origin_time": "2023-08-27T21:45:00.683Z",
        "magnitude": 5.7,
        "place": "5 km E of El Canton de San Pablo, Colombia",
        "official_event_id": "us7000kre0",
        "official_url": "https://earthquake.usgs.gov/earthquakes/eventpage/us7000kre0",
        "seconds_before": 120,
        "seconds_after": 360,
    },
    {
        "id": "co-2026-08-24-ambient",
        "kind": "ambient_noise",
        "origin_time": "2026-08-24T12:00:00.000Z",
        "magnitude": None,
        "place": "Colombian CM network ambient interval",
        "official_event_id": None,
        "official_url": None,
        "seconds_before": 0,
        "seconds_after": 300,
    },
)


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def download_case(session: requests.Session, definition: dict[str, Any]) -> dict[str, Any]:
    origin = _parse(definition["origin_time"])
    start = origin - timedelta(seconds=definition["seconds_before"])
    end = origin + timedelta(seconds=definition["seconds_after"])
    stream = Stream()
    station_results = []
    for station in STATIONS:
        response = None
        selected_url = None
        for dataselect_url in DATASELECT_URLS:
            candidate = session.get(
                dataselect_url,
                params={
                    "net": "CM",
                    "sta": station,
                    "loc": "00",
                    "cha": "HHZ",
                    "start": _iso(start),
                    "end": _iso(end),
                    "nodata": "204",
                },
                timeout=30,
            )
            if candidate.status_code == 200 and candidate.content:
                response = candidate
                selected_url = dataselect_url
                break
            response = candidate
        assert response is not None
        if response.status_code == 200 and response.content:
            station_stream = read(io.BytesIO(response.content), format="MSEED")
            stream += station_stream
            station_results.append(
                {
                    "station": station,
                    "status": 200,
                    "traces": len(station_stream),
                    "source": selected_url,
                }
            )
        else:
            station_results.append({"station": station, "status": response.status_code})
    available = sum(result["status"] == 200 for result in station_results)
    if available < 3:
        raise RuntimeError(f"{definition['id']}: solo {available} estaciones disponibles")

    fixtures = OUTPUT_DIR / "fixtures"
    fixtures.mkdir(parents=True, exist_ok=True)
    path = fixtures / f"{definition['id']}.mseed"
    stream.sort(keys=["starttime", "network", "station", "location", "channel"])
    stream.write(path, format="MSEED", reclen=4096)
    content = path.read_bytes()
    return {
        **{key: value for key, value in definition.items() if not key.startswith("seconds_")},
        "window_start": _iso(start),
        "window_end": _iso(end),
        "data_provider": "EarthScope FDSN with SGC FDSN fallback",
        "network_operator": "Servicio Geologico Colombiano (network CM)",
        "station_results": station_results,
        "waveforms": [
            {
                "path": f"fixtures/{path.name}",
                "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        ],
    }


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with requests.Session() as session:
        cases = [download_case(session, definition) for definition in CASES]
    manifest = {
        "schema_version": 1,
        "generated_at": _iso(datetime.now(timezone.utc)),
        "waveform_sources": list(DATASELECT_URLS),
        "event_catalog_source": "https://earthquake.usgs.gov/fdsnws/event/1/",
        "cases": cases,
        "license_note": (
            "Waveform and catalog data retain their source terms and attribution; "
            "the repository Apache-2.0 license does not relicense third-party data."
        ),
    }
    manifest_path = OUTPUT_DIR / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(manifest_path)


if __name__ == "__main__":
    main()
