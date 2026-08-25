from __future__ import annotations

import logging
import random
import threading
from collections.abc import Callable

from obspy import Trace  # type: ignore[import-untyped]
from obspy.clients.seedlink.easyseedlink import (  # type: ignore[import-untyped]
    EasySeedLinkClient,
    create_client,
)

from eew.alerts import AlertDispatcher
from eew.coincidence import ZoneCoincidenceRouter
from eew.config import DetectionSettings, SeedLinkProvider, SeedLinkSettings, Settings
from eew.models import EarthquakeCandidate
from eew.processor import StationProcessor

LOGGER = logging.getLogger(__name__)


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
        client_factory: Callable[..., EasySeedLinkClient] = create_client,
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
                    detection_settings,
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
        self._stop.wait()
        for thread in self._threads:
            thread.join(timeout=5)

    def stop(self) -> None:
        self._stop.set()
        for worker in self.workers:
            worker.stop()
