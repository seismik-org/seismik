from __future__ import annotations

import json
import logging
import math
import random
import threading
from collections.abc import Callable
from datetime import datetime, timezone

from obspy import Trace  # type: ignore[import-untyped]
from obspy.clients.seedlink.easyseedlink import (  # type: ignore[import-untyped]
    EasySeedLinkClient,
)

from eew.alerts import AlertDispatcher
from eew.coincidence import ZoneCoincidenceRouter
from eew.config import (
    DetectionSettings,
    SeedLinkProvider,
    SeedLinkSettings,
    Settings,
    StationSubscription,
)
from eew.models import EarthquakeCandidate
from eew.processor import StationProcessor

LOGGER = logging.getLogger(__name__)


def create_seedlink_client(
    server_url: str,
    *,
    on_data: Callable[[Trace], None],
    on_seedlink_error: Callable[[], None],
    on_terminate: Callable[[], None],
    network_timeout_seconds: float,
) -> EasySeedLinkClient:
    """Construye el cliente y fija el timeout antes de abrir el socket.

    ``obspy.create_client()`` conecta internamente antes de devolver el objeto.
    En algunas versiones de ObsPy el timeout inicial queda en ``None`` y la
    conexión falla al compararlo con el reloj. Crear el cliente sin autoconexión
    permite configurar tanto el timeout de conexión como el de lectura primero.
    """

    client = EasySeedLinkClient(server_url, autoconnect=False)
    client.on_data = on_data
    client.on_seedlink_error = on_seedlink_error
    client.on_terminate = on_terminate
    client.conn.timeout = network_timeout_seconds
    client.conn.set_net_timeout(network_timeout_seconds)
    client.connect()
    return client


class SeedLinkProviderWorker:
    """Una conexión y ciclo de reconexión aislado para un proveedor nacional."""

    def __init__(
        self,
        provider: SeedLinkProvider,
        seedlink_settings: SeedLinkSettings,
        detection_settings: DetectionSettings,
        coincidence: ZoneCoincidenceRouter,
        dispatcher: AlertDispatcher,
        on_candidate: Callable[[EarthquakeCandidate], None] | None = None,
        client_factory: Callable[..., EasySeedLinkClient] = create_seedlink_client,
        jitter_source: Callable[[float, float], float] = random.uniform,
    ):
        self.provider = provider
        self.seedlink_settings = seedlink_settings
        self.coincidence = coincidence
        self.dispatcher = dispatcher
        self.on_candidate = on_candidate
        self._client_factory = client_factory
        self._jitter_source = jitter_source
        self.processors = {
            self._processor_key(station.network, station.station, station.channel, station.location):
                StationProcessor(
                    station,
                    detection_settings.for_stream(station.network, station.channel),
                    provider_id=provider.id,
                    country_code=station.country_code or "ZZ",
                    zone_id=station.zone_id or station.country_code or "ZZ",
                )
            for station in provider.stations
        }
        self._stop = threading.Event()
        self._client: EasySeedLinkClient | None = None
        self._received_since_connect = False
        self._consecutive_failures = 0

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    def run_forever(self) -> None:
        delay = self.seedlink_settings.reconnect_initial_seconds
        while not self._stop.is_set():
            try:
                LOGGER.info(
                    "Conectando provider=%s server=%s",
                    self.provider.id,
                    self.provider.server,
                )
                self._received_since_connect = False
                client = self._client_factory(
                    self.provider.server,
                    on_data=self._on_data,
                    on_seedlink_error=self._on_seedlink_error,
                    on_terminate=self._on_terminate,
                    network_timeout_seconds=self.seedlink_settings.network_timeout_seconds,
                )
                self._client = client
                if hasattr(client.conn, "set_net_timeout"):
                    client.conn.set_net_timeout(self.seedlink_settings.network_timeout_seconds)
                for station in self.provider.stations:
                    selector = station.selector or station.channel
                    client.select_stream(station.network, station.station, selector)
                    LOGGER.info(
                        "Suscripción provider=%s country=%s zone=%s network=%s station=%s selector=%s",
                        self.provider.id,
                        station.country_code,
                        station.zone_id,
                        station.network,
                        station.station,
                        selector,
                    )
                client.run()
                if not self._stop.is_set():
                    LOGGER.warning("SeedLink terminó provider=%s; se reconectará", self.provider.id)
            except Exception:
                level = logging.CRITICAL if self.provider.required else logging.ERROR
                LOGGER.log(level, "Conexión SeedLink falló provider=%s", self.provider.id, exc_info=True)
            finally:
                client = self._client
                if client is not None:
                    try:
                        client.conn.terminate()
                    except Exception:
                        LOGGER.debug(
                            "No fue posible cerrar provider=%s limpiamente",
                            self.provider.id,
                            exc_info=True,
                        )
                self._client = None

            if self._stop.is_set():
                break
            if self._received_since_connect:
                delay = self.seedlink_settings.reconnect_initial_seconds
                self._consecutive_failures = 0
            else:
                self._consecutive_failures += 1
            jitter = delay * self.seedlink_settings.reconnect_jitter_fraction
            wait_seconds = self._jitter_source(max(0.0, delay - jitter), delay + jitter)
            LOGGER.info(
                "Reintentando provider=%s en %.1f s failures=%d",
                self.provider.id,
                wait_seconds,
                self._consecutive_failures,
            )
            if not self._stop.wait(wait_seconds):
                delay = min(delay * 2, self.seedlink_settings.reconnect_max_seconds)

    def stop(self) -> None:
        self._stop.set()
        client = self._client
        if client is None:
            return
        try:
            client.conn.terminate()
        except Exception:
            LOGGER.debug("No fue posible terminar provider=%s limpiamente", self.provider.id, exc_info=True)

    def _on_data(self, trace: Trace) -> None:
        self._received_since_connect = True
        try:
            key = self._processor_key(
                trace.stats.network,
                trace.stats.station,
                trace.stats.channel,
                trace.stats.location,
            )
            processor = self.processors.get(key)
            if processor is None:
                key = self._processor_key(
                    trace.stats.network, trace.stats.station, trace.stats.channel, None
                )
                processor = self.processors.get(key)
            if processor is None:
                return
            station_trigger = processor.process(trace)
            if station_trigger is None:
                return
            event = self.coincidence.add(station_trigger)
            if event is not None:
                self.dispatcher.submit(event)
                if self.on_candidate is not None:
                    self.on_candidate(event)
        except Exception:
            LOGGER.exception(
                "Error procesando paquete provider=%s stream=%s",
                self.provider.id,
                getattr(trace, "id", "unknown"),
            )

    def _on_seedlink_error(self) -> None:
        LOGGER.error("El servidor devolvió SeedLink ERROR provider=%s", self.provider.id)

    def _on_terminate(self) -> None:
        LOGGER.warning("El servidor terminó SeedLink provider=%s", self.provider.id)

    def health_snapshot(
        self,
        now: datetime | None = None,
    ) -> dict[str, dict[str, object]]:
        """Estado por stream para logs y metricas del modo sombra."""

        result: dict[str, dict[str, object]] = {}
        current = now or datetime.now(timezone.utc)
        for key, processor in self.processors.items():
            stats = processor.stats
            lag = stats.last_packet_lag_seconds
            age = None
            if stats.last_received_at:
                received = datetime.fromisoformat(stats.last_received_at.replace("Z", "+00:00"))
                age = max(0.0, (current - received).total_seconds())
            healthy = (
                lag is not None
                and lag <= self.coincidence.settings.max_station_lag_seconds
                and age is not None
                and age <= self.seedlink_settings.station_stale_after_seconds
            )
            reason = "ok"
            if stats.last_received_at is None:
                reason = "never_received"
            elif age is not None and age > self.seedlink_settings.station_stale_after_seconds:
                reason = "stale"
            elif lag is not None and lag > self.coincidence.settings.max_station_lag_seconds:
                reason = "high_packet_lag"
            result[key] = {
                "packets": stats.packets,
                "accepted_samples": stats.accepted_samples,
                "last_received_at": stats.last_received_at,
                "last_packet_end": stats.last_packet_end,
                "packet_lag_seconds": lag,
                "last_received_age_seconds": round(age, 3) if age is not None else None,
                "healthy": healthy,
                "reason": reason,
                "resets": stats.reset_count,
                "non_finite_samples": stats.non_finite_samples,
            }
        return result

    @staticmethod
    def _processor_key(network: str, station: str, channel: str, location: str | None) -> str:
        return f"{network}.{station}.{location if location is not None else '*'}.{channel}"


class SeedLinkDetectionService:
    """Orquesta proveedores sin que la caída de uno detenga a los demás."""

    def __init__(
        self,
        settings: Settings,
        dispatcher: AlertDispatcher,
        on_candidate: Callable[[EarthquakeCandidate], None] | None = None,
    ):
        self.settings = settings
        self.dispatcher = dispatcher
        self.coincidence = ZoneCoincidenceRouter(settings.coincidence)
        self.workers = tuple(
            SeedLinkProviderWorker(
                provider,
                settings.seedlink,
                settings.detection,
                self.coincidence,
                dispatcher,
                on_candidate,
            )
            for provider in settings.seedlink.providers
            if provider.enabled
        )
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    def run_forever(self) -> None:
        self._threads = [
            threading.Thread(
                target=worker.run_forever,
                name=f"seedlink-{worker.provider.id}",
                daemon=True,
            )
            for worker in self.workers
        ]
        for thread in self._threads:
            thread.start()
        while not self._stop.wait(self.settings.seedlink.health_log_interval_seconds):
            LOGGER.info(
                "seedlink_health=%s",
                json.dumps(self.health_snapshot(), separators=(",", ":")),
            )
            LOGGER.info(
                "seedlink_coverage=%s",
                json.dumps(self.coverage_snapshot(), separators=(",", ":")),
            )
        for thread in self._threads:
            thread.join(timeout=5)

    def stop(self) -> None:
        self._stop.set()
        for worker in self.workers:
            worker.stop()

    def health_snapshot(self) -> dict[str, dict[str, dict[str, object]]]:
        return {worker.provider.id: worker.health_snapshot() for worker in self.workers}

    def coverage_snapshot(self, now: datetime | None = None) -> dict[str, object]:
        """Describe cobertura *operativa*, no sólo un socket conectado.

        Un proveedor puede estar accesible aunque la mayoría de sus streams no
        entregue paquetes. Exponer ambas cosas evita presentar una red parcial
        como cobertura nacional y no cambia ni relaja el criterio de alarma.
        """

        current = now or datetime.now(timezone.utc)
        zones: dict[str, list[tuple[StationSubscription, dict[str, object]]]] = {}
        for worker in self.workers:
            health = worker.health_snapshot(current)
            for station in worker.provider.stations:
                key = worker._processor_key(
                    station.network, station.station, station.channel, station.location
                )
                zones.setdefault(station.zone_id or station.country_code or "ZZ", []).append(
                    (station, health[key])
                )

        zone_summary: dict[str, object] = {}
        configured_total = healthy_total = 0
        for zone_id, rows in zones.items():
            configured_total += len(rows)
            healthy = [station for station, row in rows if row["healthy"] is True]
            healthy_total += len(healthy)
            located = [station for station in healthy if station.latitude is not None and station.longitude is not None]
            aperture = _station_aperture_km(located)
            quorum = len(healthy) >= self.settings.coincidence.minimum_stations
            location_ready = (
                len(located) >= self.settings.coincidence.minimum_located_stations
                and aperture >= self.settings.coincidence.minimum_network_aperture_km
            )
            ratio = len(healthy) / len(rows) if rows else 0.0
            # Two thirds is an observability threshold, never an alarm rule.
            coverage = "ready" if quorum and location_ready and ratio >= 2 / 3 else "degraded"
            zone_summary[zone_id] = {
                "configured_stations": len(rows),
                "healthy_stations": len(healthy),
                "healthy_ratio": round(ratio, 3),
                "healthy_station_ids": [station.station_id for station in healthy],
                "unhealthy_station_ids": [
                    station.station_id for station, row in rows if row["healthy"] is not True
                ],
                "candidate_quorum_ready": quorum,
                "located_healthy_stations": len(located),
                "network_aperture_km": round(aperture, 3),
                "location_ready": location_ready,
                "coverage": coverage,
            }

        ratio = healthy_total / configured_total if configured_total else 0.0
        return {
            "status": "ready" if zone_summary and all(
                isinstance(row, dict) and row.get("coverage") == "ready"
                for row in zone_summary.values()
            ) else "degraded",
            "configured_stations": configured_total,
            "healthy_stations": healthy_total,
            "healthy_ratio": round(ratio, 3),
            "minimum_stations": self.settings.coincidence.minimum_stations,
            "zones": zone_summary,
        }


def _station_aperture_km(stations: list[StationSubscription]) -> float:
    """Mayor separación entre estaciones sanas con coordenadas."""

    maximum = 0.0
    for index, first in enumerate(stations):
        assert first.latitude is not None and first.longitude is not None
        for second in stations[index + 1 :]:
            assert second.latitude is not None and second.longitude is not None
            lat1, lat2 = math.radians(first.latitude), math.radians(second.latitude)
            delta_lat = lat2 - lat1
            delta_lon = math.radians(second.longitude - first.longitude)
            value = math.sin(delta_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
            maximum = max(maximum, 2 * 6371.0088 * math.atan2(math.sqrt(value), math.sqrt(1 - value)))
    return maximum
