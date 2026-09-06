"""Generador de sismos simulados para simulacros y pruebas de extremo a extremo.

Los eventos producidos aquí cumplen el mismo contrato que los del detector real,
de modo que atraviesan la API, el bus Redis y el dispatcher sin rutas especiales.
Todo identificador empieza por ``drill-`` para que la evidencia de un simulacro
nunca se confunda con una detección real.
"""
from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

DRILL_PREFIX = "drill-"
EARTH_RADIUS_KM = 6371.0088


def is_drill(event_id: str) -> bool:
    """Un simulacro se reconoce por su identificador, no por un campo extra."""

    return event_id.startswith(DRILL_PREFIX)


def utc_iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class SimulatedStation:
    station_id: str
    latitude: float
    longitude: float
    provider_id: str = "simulation"
    network: str = "XX"
    channel: str = "HHZ"

    @property
    def stream_id(self) -> str:
        return f"{self.station_id}.00.{self.channel}"


@dataclass(frozen=True)
class SimulationProfile:
    """Escenario reproducible de simulacro."""

    name: str
    zone_id: str
    country_code: str
    latitude: float
    longitude: float
    magnitude: float
    depth_km: float
    place: str
    stations: tuple[SimulatedStation, ...] = field(default_factory=tuple)

    def with_stations(self, count: int) -> "SimulationProfile":
        if self.stations:
            return self
        return SimulationProfile(
            **{**self.__dict__, "stations": _ring_of_stations(self, count)}
        )


def _ring_of_stations(
    profile: SimulationProfile, count: int, radius_km: float = 60.0
) -> tuple[SimulatedStation, ...]:
    """Estaciones repartidas alrededor del epicentro, con apertura realista."""

    stations = []
    for index in range(count):
        bearing = 2 * math.pi * index / max(1, count)
        delta_lat = (radius_km / 111.32) * math.cos(bearing)
        delta_lon = (radius_km / (111.32 * math.cos(math.radians(profile.latitude)))) * math.sin(
            bearing
        )
        stations.append(
            SimulatedStation(
                station_id=f"XX.SIM{index + 1}",
                latitude=round(profile.latitude + delta_lat, 5),
                longitude=round(profile.longitude + delta_lon, 5),
            )
        )
    return tuple(stations)


PROFILES: dict[str, SimulationProfile] = {
    "bogota": SimulationProfile(
        name="bogota",
        zone_id="andes",
        country_code="CO",
        latitude=4.65,
        longitude=-74.05,
        magnitude=5.2,
        depth_km=25.0,
        place="Simulacro — Sabana de Bogotá",
    ),
    "pacifico": SimulationProfile(
        name="pacifico",
        zone_id="pacifico",
        country_code="CO",
        latitude=2.85,
        longitude=-78.20,
        magnitude=6.4,
        depth_km=18.0,
        place="Simulacro — costa pacífica",
    ),
    "atacama": SimulationProfile(
        name="atacama",
        zone_id="CL",
        country_code="CL",
        latitude=-21.80,
        longitude=-69.60,
        magnitude=6.9,
        depth_km=45.0,
        place="Simulacro — norte de Chile",
    ),
}


def simulated_candidate(
    profile: SimulationProfile,
    *,
    station_count: int = 3,
    detected_at: datetime | None = None,
    event_id: str | None = None,
    located: bool = True,
) -> dict[str, Any]:
    """Candidato equivalente al que emitiría el detector SeedLink/STA-LTA."""

    resolved = profile.with_stations(station_count)
    stations = resolved.stations[:station_count]
    if len(stations) < 2:
        raise ValueError("Un candidato requiere al menos dos estaciones")
    moment = detected_at or datetime.now(timezone.utc)
    triggers = []
    for index, station in enumerate(stations):
        trigger_time = moment - timedelta(seconds=len(stations) - index)
        triggers.append(
            {
                "provider_id": station.provider_id,
                "country_code": resolved.country_code,
                "zone_id": resolved.zone_id,
                "station_id": station.station_id,
                "stream_id": station.stream_id,
                "trigger_time": utc_iso(trigger_time),
                "received_at": utc_iso(trigger_time + timedelta(milliseconds=350)),
                "sta_lta_ratio": round(6.5 - index * 0.4, 2),
                "latitude": station.latitude,
                "longitude": station.longitude,
                "packet_lag_seconds": 0.35,
            }
        )
    return {
        "event_id": event_id or f"{DRILL_PREFIX}{uuid.uuid4()}",
        "type": "earthquake_candidate",
        "status": "unlocated_unreviewed",
        "zone_id": resolved.zone_id,
        "country_code": resolved.country_code,
        "country_codes": [resolved.country_code],
        "detected_at": utc_iso(moment),
        "coincidence_window_seconds": 10.0,
        "required_stations": len(triggers),
        "station_count": len(triggers),
        "stations": triggers,
        "estimated_latitude": resolved.latitude if located else None,
        "estimated_longitude": resolved.longitude if located else None,
    }


def simulated_official_update(
    profile: SimulationProfile,
    candidate_event_id: str,
    *,
    magnitude: float | None = None,
    matched_at: datetime | None = None,
    event_id: str | None = None,
) -> dict[str, Any]:
    """Actualización oficial asociada a un candidato simulado."""

    moment = matched_at or datetime.now(timezone.utc)
    report = {
        "source_id": "simulation",
        "agency": "Simulacro Seismik",
        "jurisdiction": profile.country_code,
        "official_event_id": f"{DRILL_PREFIX}{profile.name}",
        "origin_time": utc_iso(moment - timedelta(seconds=45)),
        "updated_at": utc_iso(moment),
        "latitude": profile.latitude,
        "longitude": profile.longitude,
        "depth_km": profile.depth_km,
        "magnitude": magnitude if magnitude is not None else profile.magnitude,
        "magnitude_type": "Mw",
        "place": profile.place,
        "review_status": "simulacro",
        "official_url": "https://seismik.org/simulacro",
        "attribution": "Evento simulado; no corresponde a un sismo real",
        "tsunami": False,
    }
    return {
        "event_id": event_id or f"{DRILL_PREFIX}{uuid.uuid4()}",
        "candidate_event_id": candidate_event_id,
        "type": "official_report_update",
        "status": "official_report_available",
        "matched_at": utc_iso(moment),
        "preferred_report": report,
        "reports": [report],
    }


def drill_sequence(
    profile_name: str,
    *,
    station_count: int = 3,
    magnitude: float | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Par candidato → actualización oficial usado por el simulacro completo."""

    try:
        profile = PROFILES[profile_name]
    except KeyError as error:
        raise KeyError(
            f"Perfil desconocido: {profile_name}. Disponibles: {sorted(PROFILES)}"
        ) from error
    candidate = simulated_candidate(profile, station_count=station_count)
    official = simulated_official_update(
        profile, str(candidate["event_id"]), magnitude=magnitude
    )
    return candidate, official
