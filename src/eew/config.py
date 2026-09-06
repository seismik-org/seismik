from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class StationSubscription:
    network: str
    station: str
    channel: str
    location: str | None = None
    selector: str | None = None
    country_code: str | None = None
    zone_id: str | None = None
    latitude: float | None = None
    longitude: float | None = None

    @property
    def station_id(self) -> str:
        return f"{self.network}.{self.station}"


@dataclass(frozen=True)
class SeedLinkSettings:
    providers: tuple["SeedLinkProvider", ...]
    reconnect_initial_seconds: float = 2.0
    reconnect_max_seconds: float = 60.0
    reconnect_jitter_fraction: float = 0.2
    network_timeout_seconds: float = 30.0
    health_log_interval_seconds: float = 30.0
    station_stale_after_seconds: float = 60.0


@dataclass(frozen=True)
class SeedLinkProvider:
    id: str
    server: str
    stations: tuple[StationSubscription, ...]
    enabled: bool = True
    required: bool = False
    country_code: str | None = None
    metadata_url: str | None = None


@dataclass(frozen=True)
class DetectionSettings:
    buffer_seconds: float = 60.0
    sta_seconds: float = 0.5
    lta_seconds: float = 10.0
    trigger_on: float = 3.5
    trigger_off: float = 1.0
    station_cooldown_seconds: float = 20.0
    filter_enabled: bool = True
    filter_low_hz: float = 1.0
    filter_high_hz: float = 10.0
    filter_corners: int = 4
    max_interpolated_gap_seconds: float = 0.25
    # Overrides por "NETWORK.CHANNEL" (por ejemplo "CM.HHZ"). Cada valor
    # conserva las mismas unidades del perfil base.
    network_profiles: dict[str, dict[str, Any]] = field(default_factory=dict)

    def for_stream(self, network: str, channel: str) -> "DetectionSettings":
        overrides = self.network_profiles.get(f"{network}.{channel}")
        if overrides is None:
            overrides = self.network_profiles.get(f"{network}.*", {})
        allowed = {name for name in self.__dataclass_fields__ if name != "network_profiles"}
        unknown = set(overrides) - allowed
        if unknown:
            raise ValueError(f"Parametros DSP desconocidos para {network}.{channel}: {sorted(unknown)}")
        return replace(self, network_profiles={}, **overrides)


@dataclass(frozen=True)
class CoincidenceSettings:
    minimum_stations: int = 3
    window_seconds: float = 15.0
    alert_cooldown_seconds: float = 60.0
    max_station_lag_seconds: float = 15.0
    minimum_located_stations: int = 0
    minimum_network_aperture_km: float = 0.0


@dataclass(frozen=True)
class AlertSettings:
    webhook_url: str | None = None
    webhook_base_url: str | None = None
    webhook_hmac_secret: str | None = None
    webhook_timeout_seconds: float = 3.0
    webhook_retries: int = 2
    # Cola durable del enlace detector → API. Sin directorio el detector
    # conserva el comportamiento en memoria del Sprint 1.
    spool_directory: str | None = None
    spool_max_entries: int = 500
    spool_max_age_seconds: float = 900.0
    retry_interval_seconds: float = 5.0


@dataclass(frozen=True)
class OfficialReportsSettings:
    enabled: bool = True
    sources_file: str = "official_sources.json"
    initial_delay_seconds: float = 20.0
    poll_intervals_seconds: tuple[float, ...] = (30.0, 60.0, 120.0, 300.0, 600.0)
    request_timeout_seconds: float = 10.0
    max_origin_time_delta_seconds: float = 600.0
    max_distance_km: float = 1200.0
    max_concurrent_candidates: int = 4


@dataclass(frozen=True)
class Settings:
    seedlink: SeedLinkSettings
    detection: DetectionSettings
    coincidence: CoincidenceSettings
    alert: AlertSettings
    official_reports: OfficialReportsSettings

    @classmethod
    def load(cls, path: str | Path) -> "Settings":
        with Path(path).open("r", encoding="utf-8") as handle:
            raw: dict[str, Any] = json.load(handle)

        seedlink_input = raw["seedlink"]
        providers = []
        for provider_raw in seedlink_input["providers"]:
            provider_country = provider_raw.get("country_code")
            if provider_country:
                provider_country = provider_country.upper()
            subscriptions = tuple(
                StationSubscription(**{
                    **station,
                    "country_code": (
                        (station.get("country_code") or provider_country).upper()
                        if (station.get("country_code") or provider_country)
                        else None
                    ),
                    "zone_id": (
                        station.get("zone_id")
                        or station.get("country_code")
                        or provider_country
                    ),
                })
                for station in provider_raw["stations"]
            )
            env_key = "SEEDLINK_SERVER_" + provider_raw["id"].upper().replace("-", "_")
            provider = SeedLinkProvider(**{
                **provider_raw,
                "country_code": provider_country,
                "server": os.getenv(env_key, provider_raw["server"]),
                "stations": subscriptions,
            })
            providers.append(provider)

        active_countries = _csv_env("SEISMIK_ACTIVE_COUNTRIES", uppercase=True)
        active_zones = _csv_env("SEISMIK_ACTIVE_ZONES", uppercase=False)
        shard_count = int(os.getenv("SEISMIK_SHARD_COUNT", "1"))
        shard_index = int(os.getenv("SEISMIK_SHARD_INDEX", "0"))
        if shard_count < 1 or not 0 <= shard_index < shard_count:
            raise ValueError("Se requiere 0 <= SEISMIK_SHARD_INDEX < SEISMIK_SHARD_COUNT")

        filtering = bool(active_countries or active_zones or shard_count > 1)
        filtered_providers = []
        for provider in providers:
            stations = tuple(
                station
                for station in provider.stations
                if (not active_countries or station.country_code in active_countries)
                and (not active_zones or station.zone_id in active_zones)
                and _belongs_to_shard(station.zone_id or "", shard_index, shard_count)
            )
            if stations:
                filtered_providers.append(
                    SeedLinkProvider(**{**provider.__dict__, "stations": stations})
                )

        if filtering:
            minimum = int(raw.get("coincidence", {}).get("minimum_stations", 3))
            counts: dict[str, set[str]] = {}
            for provider in filtered_providers:
                for station in provider.stations:
                    counts.setdefault(station.zone_id or "", set()).add(station.station_id)
            valid_zones = {zone for zone, stations in counts.items() if len(stations) >= minimum}
            filtered_providers = [
                SeedLinkProvider(**{
                    **provider.__dict__,
                    "stations": tuple(
                        station for station in provider.stations if station.zone_id in valid_zones
                    ),
                })
                for provider in filtered_providers
            ]
            filtered_providers = [provider for provider in filtered_providers if provider.stations]

        max_stations = int(os.getenv("SEISMIK_MAX_STATIONS", "0"))
        selected_count = sum(len(provider.stations) for provider in filtered_providers)
        if max_stations and selected_count > max_stations:
            raise ValueError(
                f"Configuración selecciona {selected_count} estaciones; excede SEISMIK_MAX_STATIONS={max_stations}"
            )
        seedlink = SeedLinkSettings(
            providers=tuple(filtered_providers),
            reconnect_initial_seconds=seedlink_input.get("reconnect_initial_seconds", 2.0),
            reconnect_max_seconds=seedlink_input.get("reconnect_max_seconds", 60.0),
            reconnect_jitter_fraction=seedlink_input.get("reconnect_jitter_fraction", 0.2),
            network_timeout_seconds=seedlink_input.get("network_timeout_seconds", 30.0),
            health_log_interval_seconds=seedlink_input.get("health_log_interval_seconds", 30.0),
            station_stale_after_seconds=seedlink_input.get("station_stale_after_seconds", 60.0),
        )

        alert_raw = raw.get("alert", {})
        webhook_from_env = os.getenv("WEBHOOK_URL")
        if webhook_from_env:
            alert_raw = {**alert_raw, "webhook_url": webhook_from_env}
        webhook_base_from_env = os.getenv("WEBHOOK_BASE_URL")
        webhook_secret_from_env = os.getenv("WEBHOOK_HMAC_SECRET")
        if webhook_base_from_env:
            alert_raw = {**alert_raw, "webhook_base_url": webhook_base_from_env}
        if webhook_secret_from_env:
            alert_raw = {**alert_raw, "webhook_hmac_secret": webhook_secret_from_env}
        spool_from_env = os.getenv("SEISMIK_ALERT_SPOOL_DIR")
        if spool_from_env:
            alert_raw = {**alert_raw, "spool_directory": spool_from_env}

        official_raw = raw.get("official_reports", {})
        intervals = official_raw.get("poll_intervals_seconds")
        if intervals is not None:
            official_raw = {**official_raw, "poll_intervals_seconds": tuple(intervals)}
        sources_file = official_raw.get("sources_file", "official_sources.json")
        sources_path = Path(sources_file)
        if not sources_path.is_absolute():
            sources_path = Path(path).resolve().parent / sources_path
        official_raw = {**official_raw, "sources_file": str(sources_path)}

        settings = cls(
            seedlink=seedlink,
            detection=DetectionSettings(**raw.get("detection", {})),
            coincidence=CoincidenceSettings(**raw.get("coincidence", {})),
            alert=AlertSettings(**alert_raw),
            official_reports=OfficialReportsSettings(**official_raw),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        d = self.detection
        c = self.coincidence
        enabled_providers = tuple(provider for provider in self.seedlink.providers if provider.enabled)
        if not enabled_providers:
            raise ValueError("Debe configurarse al menos un proveedor SeedLink habilitado")
        if self.seedlink.reconnect_initial_seconds <= 0:
            raise ValueError("reconnect_initial_seconds debe ser positivo")
        if self.seedlink.reconnect_max_seconds < self.seedlink.reconnect_initial_seconds:
            raise ValueError("reconnect_max_seconds debe ser mayor o igual al inicial")
        if not 0 <= self.seedlink.reconnect_jitter_fraction <= 1:
            raise ValueError("reconnect_jitter_fraction debe estar entre 0 y 1")
        if self.seedlink.network_timeout_seconds <= 0:
            raise ValueError("network_timeout_seconds debe ser positivo")
        if (
            self.seedlink.health_log_interval_seconds <= 0
            or self.seedlink.station_stale_after_seconds <= 0
        ):
            raise ValueError("Los intervalos de salud SeedLink deben ser positivos")
        provider_ids = [provider.id for provider in self.seedlink.providers]
        if len(provider_ids) != len(set(provider_ids)):
            raise ValueError("Los id de proveedor deben ser únicos")
        for provider in enabled_providers:
            if not provider.stations:
                raise ValueError(f"Proveedor {provider.id} sin estaciones")
            for station in provider.stations:
                if not station.country_code or not station.zone_id:
                    raise ValueError(
                        f"Estación {station.station_id} de {provider.id} sin country_code/zone_id"
                    )
        _validate_detection(d)
        for provider in enabled_providers:
            for station in provider.stations:
                _validate_detection(d.for_stream(station.network, station.channel))
        if c.minimum_located_stations < 0 or c.minimum_located_stations > c.minimum_stations:
            raise ValueError("minimum_located_stations debe estar entre 0 y minimum_stations")
        if c.max_station_lag_seconds <= 0 or c.minimum_network_aperture_km < 0:
            raise ValueError("Los limites de salud/geometria deben ser validos")
        official = self.official_reports
        if official.enabled and not Path(official.sources_file).is_file():
            raise ValueError(f"No existe sources_file oficial: {official.sources_file}")
        if official.max_origin_time_delta_seconds <= 0 or official.max_distance_km <= 0:
            raise ValueError("Los límites de asociación oficial deben ser positivos")
        if self.alert.webhook_url and self.alert.webhook_base_url:
            raise ValueError("Use webhook_url o webhook_base_url, no ambos")
        if (self.alert.webhook_url or self.alert.webhook_base_url) and not self.alert.webhook_hmac_secret:
            raise ValueError("Un webhook configurado requiere webhook_hmac_secret")
        if self.alert.spool_max_entries < 1:
            raise ValueError("spool_max_entries debe ser positivo")
        if self.alert.spool_max_age_seconds <= 0 or self.alert.retry_interval_seconds <= 0:
            raise ValueError("Los tiempos del spool de alertas deben ser positivos")
        stations_by_zone: dict[str, set[str]] = {}
        for provider in enabled_providers:
            for station in provider.stations:
                assert station.zone_id is not None
                stations_by_zone.setdefault(station.zone_id, set()).add(station.station_id)
        undersized = {
            zone: len(stations)
            for zone, stations in stations_by_zone.items()
            if len(stations) < c.minimum_stations
        }
        if undersized:
            raise ValueError(
                "minimum_stations excede estaciones únicas por zona: " + str(undersized)
            )


def _csv_env(name: str, uppercase: bool) -> set[str]:
    values = {item.strip() for item in os.getenv(name, "").split(",") if item.strip()}
    return {item.upper() for item in values} if uppercase else values


def _validate_detection(settings: DetectionSettings) -> None:
    if settings.sta_seconds <= 0 or settings.lta_seconds <= settings.sta_seconds:
        raise ValueError("Se requiere 0 < sta_seconds < lta_seconds")
    if settings.buffer_seconds < settings.lta_seconds * 1.5:
        raise ValueError("buffer_seconds debe ser al menos 1.5 * lta_seconds")
    if not 0 < settings.trigger_off < settings.trigger_on:
        raise ValueError("Se requiere 0 < trigger_off < trigger_on")


def _belongs_to_shard(zone_id: str, shard_index: int, shard_count: int) -> bool:
    digest = hashlib.sha256(zone_id.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % shard_count == shard_index
