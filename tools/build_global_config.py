"""Genera una configuración mundial acotada desde inventarios FDSN oficiales.

El inventario FDSN indica que el canal está vigente, no garantiza telemetría
SeedLink en el instante de ejecución. Por eso el resultado conserva procedencia
y fecha, y debe validarse antes de un despliegue operativo.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

COUNTRIES_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
    "v5.1.2/geojson/ne_110m_admin_0_countries.geojson"
)

PROVIDERS = (
    {
        "id": "orfeus_global",
        "server": "eida.orfeus-eu.org:18000",
        "metadata_url": "https://orfeus-eu.org/fdsnws/station/1/query",
        "priority": 10,
    },
    {
        "id": "geofon_global",
        "server": "geofon.gfz.de:18000",
        "metadata_url": "https://geofon.gfz.de/fdsnws/station/1/query",
        "priority": 20,
    },
    {
        "id": "earthscope_global",
        "server": "rtserve.earthscope.org:18000",
        "metadata_url": "https://service.earthscope.org/fdsnws/station/1/query",
        "priority": 30,
    },
)


@dataclass(frozen=True)
class Candidate:
    provider_id: str
    provider_priority: int
    network: str
    station: str
    location: str
    channel: str
    latitude: float
    longitude: float
    sample_rate: float
    country_code: str
    zone_id: str

    @property
    def physical_id(self) -> str:
        return f"{self.network}.{self.station}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Construye config.global.json")
    parser.add_argument("--output", default="config.global.json")
    parser.add_argument("--coverage", default="data/global_coverage.json")
    parser.add_argument("--zone-degrees", type=float, default=3.0)
    parser.add_argument("--stations-per-zone", type=int, default=6)
    parser.add_argument("--minimum-stations", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=90.0)
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def fetch_json(url: str, timeout: float) -> dict[str, Any]:
    response = requests.get(url, timeout=timeout, headers={"User-Agent": "seismik-catalog/0.3"})
    response.raise_for_status()
    return response.json()


def point_in_ring(lon: float, lat: float, ring: list[list[float]]) -> bool:
    inside = False
    previous = ring[-1]
    for current in ring:
        x1, y1 = previous[:2]
        x2, y2 = current[:2]
        if (y1 > lat) != (y2 > lat):
            crossing = (x2 - x1) * (lat - y1) / (y2 - y1) + x1
            if lon < crossing:
                inside = not inside
        previous = current
    return inside


def point_in_geometry(lon: float, lat: float, geometry: dict[str, Any]) -> bool:
    polygons = geometry["coordinates"]
    if geometry["type"] == "Polygon":
        polygons = [polygons]
    for polygon in polygons:
        if point_in_ring(lon, lat, polygon[0]) and not any(
            point_in_ring(lon, lat, hole) for hole in polygon[1:]
        ):
            return True
    return False


def country_for(lon: float, lat: float, features: list[dict[str, Any]]) -> str:
    for feature in features:
        if point_in_geometry(lon, lat, feature["geometry"]):
            properties = feature["properties"]
            code = properties.get("ISO_A2_EH") or properties.get("ISO_A2")
            return code if code and code != "-99" else "ZZ"
    return "ZZ"


def zone_for(lon: float, lat: float, size: float) -> str:
    lat_bin = math.floor((lat + 90.0) / size)
    lon_bin = math.floor((lon + 180.0) / size)
    return f"grid_{size:g}_{lat_bin}_{lon_bin}"


def fetch_channels(provider: dict[str, Any], at_time: str, timeout: float) -> list[dict[str, str]]:
    params = {
        "level": "channel",
        "channel": "HHZ,BHZ",
        "format": "text",
        "includerestricted": "false",
        "startbefore": at_time,
        "endafter": at_time,
    }
    response = requests.get(
        provider["metadata_url"],
        params=params,
        timeout=timeout,
        headers={"User-Agent": "seismik-catalog/0.3"},
    )
    response.raise_for_status()
    rows = []
    for line in response.text.splitlines():
        if not line or line.startswith("#"):
            continue
        fields = [field.strip() for field in line.split("|")]
        if len(fields) < 15:
            continue
        rows.append({
            "network": fields[0],
            "station": fields[1],
            "location": "" if fields[2] in ("", "--") else fields[2],
            "channel": fields[3],
            "latitude": fields[4],
            "longitude": fields[5],
            "sample_rate": fields[14],
        })
    return rows


def prefer_channel(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    priority = {"HHZ": 0, "BHZ": 1}
    best: dict[str, dict[str, str]] = {}
    for row in rows:
        key = f"{row['network']}.{row['station']}"
        rank = (priority.get(row["channel"], 99), row["location"] not in ("00", ""), row["location"])
        current = best.get(key)
        if current is None:
            best[key] = row
            continue
        current_rank = (
            priority.get(current["channel"], 99),
            current["location"] not in ("00", ""),
            current["location"],
        )
        if rank < current_rank:
            best[key] = row
    return list(best.values())


def distance_squared(a: Candidate, b: Candidate) -> float:
    lon_scale = math.cos(math.radians((a.latitude + b.latitude) / 2.0))
    return (a.latitude - b.latitude) ** 2 + ((a.longitude - b.longitude) * lon_scale) ** 2


def spread_sample(candidates: list[Candidate], limit: int) -> list[Candidate]:
    """Muestreo de punto más lejano para evitar elegir estaciones colocalizadas."""
    ordered = sorted(candidates, key=lambda item: (item.provider_priority, item.physical_id))
    selected = [ordered[0]]
    remaining = ordered[1:]
    while remaining and len(selected) < limit:
        candidate = max(
            remaining,
            key=lambda item: min(distance_squared(item, chosen) for chosen in selected),
        )
        selected.append(candidate)
        remaining.remove(candidate)
    return selected


def build(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any]]:
    generated_at = utc_now()
    countries = fetch_json(COUNTRIES_URL, args.timeout)
    features = countries["features"]
    all_candidates: list[Candidate] = []
    errors: list[dict[str, str]] = []

    for provider in PROVIDERS:
        try:
            rows = prefer_channel(fetch_channels(provider, generated_at, args.timeout))
        except requests.RequestException as exc:
            errors.append({"provider_id": provider["id"], "error": str(exc)})
            continue
        for row in rows:
            lat = float(row["latitude"])
            lon = float(row["longitude"])
            all_candidates.append(Candidate(
                provider_id=provider["id"],
                provider_priority=provider["priority"],
                network=row["network"],
                station=row["station"],
                location=row["location"],
                channel=row["channel"],
                latitude=lat,
                longitude=lon,
                sample_rate=float(row["sample_rate"]),
                country_code=country_for(lon, lat, features),
                zone_id=zone_for(lon, lat, args.zone_degrees),
            ))

    # Una estación redistribuida por varios centros solo se solicita al proveedor
    # prioritario y solo cuenta una vez para coincidencia.
    deduplicated: dict[str, Candidate] = {}
    for candidate in sorted(all_candidates, key=lambda item: item.provider_priority):
        deduplicated.setdefault(candidate.physical_id, candidate)

    by_zone: dict[str, list[Candidate]] = defaultdict(list)
    for candidate in deduplicated.values():
        by_zone[candidate.zone_id].append(candidate)
    selected = [
        item
        for zone_candidates in by_zone.values()
        if len(zone_candidates) >= args.minimum_stations
        for item in spread_sample(zone_candidates, args.stations_per_zone)
    ]

    stations_by_provider: dict[str, list[Candidate]] = defaultdict(list)
    for station in selected:
        stations_by_provider[station.provider_id].append(station)

    provider_configs = []
    for provider in PROVIDERS:
        stations = sorted(
            stations_by_provider.get(provider["id"], []),
            key=lambda item: (item.country_code, item.zone_id, item.network, item.station),
        )
        if not stations:
            continue
        provider_configs.append({
            "id": provider["id"],
            "server": provider["server"],
            "metadata_url": provider["metadata_url"],
            "enabled": True,
            "required": False,
            "stations": [
                {
                    "network": item.network,
                    "station": item.station,
                    "location": item.location,
                    "channel": item.channel,
                    "selector": f"{item.location}{item.channel}" if item.location else item.channel,
                    "country_code": item.country_code,
                    "zone_id": item.zone_id,
                    "latitude": round(item.latitude, 6),
                    "longitude": round(item.longitude, 6),
                }
                for item in stations
            ],
        })

    country_counts = Counter(item.country_code for item in selected)
    zone_counts = Counter(item.zone_id for item in selected)
    config = {
        "schema_version": 2,
        "generated_at": generated_at,
        "catalog": {
            "method": "active FDSN metadata; SeedLink availability must be checked at runtime",
            "zone_degrees": args.zone_degrees,
            "stations_per_zone": args.stations_per_zone,
            "source_country_geometry": COUNTRIES_URL,
        },
        "seedlink": {
            "reconnect_initial_seconds": 2.0,
            "reconnect_max_seconds": 60.0,
            "providers": provider_configs,
        },
        "detection": {
            "buffer_seconds": 60.0,
            "sta_seconds": 0.5,
            "lta_seconds": 10.0,
            "trigger_on": 3.5,
            "trigger_off": 1.0,
            "station_cooldown_seconds": 20.0,
            "filter_enabled": True,
            "filter_low_hz": 1.0,
            "filter_high_hz": 10.0,
            "filter_corners": 4,
            "max_interpolated_gap_seconds": 0.25,
        },
        "coincidence": {
            "minimum_stations": args.minimum_stations,
            "window_seconds": 30.0,
            "alert_cooldown_seconds": 60.0,
        },
        "alert": {
            "webhook_url": None,
            "webhook_base_url": None,
            "webhook_hmac_secret": None,
            "webhook_timeout_seconds": 3.0,
            "webhook_retries": 2,
        },
        "official_reports": {
            "enabled": True,
            "sources_file": "official_sources.json",
            "initial_delay_seconds": 20,
            "poll_intervals_seconds": [30, 60, 120, 300, 600],
            "request_timeout_seconds": 10,
            "max_origin_time_delta_seconds": 600,
            "max_distance_km": 1200,
            "max_concurrent_candidates": 4,
        },
    }
    coverage = {
        "generated_at": generated_at,
        "limitations": [
            "FDSN active metadata is not proof of a currently flowing SeedLink stream.",
            "Countries without at least one selected dense zone are not covered.",
            "This is a technical candidate catalog, not a certified EEW network.",
        ],
        "providers": {key: len(value) for key, value in sorted(stations_by_provider.items())},
        "selected_stations": len(selected),
        "covered_countries": len([code for code in country_counts if code != "ZZ"]),
        "countries": dict(sorted(country_counts.items())),
        "zones": len(zone_counts),
        "provider_errors": errors,
    }
    return config, coverage


def main() -> None:
    args = parse_args()
    config, coverage = build(args)
    output = Path(args.output)
    coverage_output = Path(args.coverage)
    output.parent.mkdir(parents=True, exist_ok=True)
    coverage_output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    coverage_output.write_text(
        json.dumps(coverage, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(coverage, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
