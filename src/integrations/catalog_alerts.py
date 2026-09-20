"""Alertas por perímetro para los sismos de los catálogos oficiales.

El dispatcher sólo recibía reportes oficiales de sismos que la red propia
(SeedLink) había detectado antes: un sismo fuerte fuera de su cobertura nunca
llegaba a los teléfonos. Este lazo consulta cada minuto los catálogos de
official_sources.json y deja en el stream oficial cada sismo que alguien pudo
sentir. El dispatcher decide a quién le suena la alarma y a quién le llega un
aviso según el perímetro de sacudida (api/felt_area.py, dispatcher/policy.py),
y descarta el mismo sismo reportado por otra agencia.

Corre dentro de seismik-integrations y está apagado hasta
``SEISMIK_CATALOG_ALERTS_ENABLED=true``.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from redis.asyncio import Redis

from api.bus import RedisEventBus
from api.config import AppSettings
from api.felt_area import FELT, radius_km
from dispatcher.policy import CATALOG_ORIGIN
from eew.models import OfficialReport
from eew.official import OfficialApiClient, OfficialSource, load_sources
from eew.simulation import is_drill
from integrations.bulletin_card import is_withdrawn

LOGGER = logging.getLogger(__name__)
# Un sismo ya entregado al stream no se vuelve a entregar durante este tiempo.
SEEN_SECONDS = 86_400

Fetch = Callable[[OfficialSource, datetime, datetime, float], list[OfficialReport]]


def fetch_catalog(
    source: OfficialSource, start: datetime, end: datetime, timeout: float
) -> list[OfficialReport]:
    return OfficialApiClient(source, timeout).fetch(start, end)


def _origin(report: OfficialReport) -> datetime | None:
    try:
        moment = datetime.fromisoformat(str(report.origin_time).replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def alertable(
    report: OfficialReport, start: datetime, now: datetime, minimum_intensity: float = FELT
) -> bool:
    """Un sismo real y reciente que sacude al menos `minimum_intensity`.

    El filtro es el perímetro de sacudida, no la magnitud: un M4 somero bajo
    una ciudad sacude más que un M6 profundo y lejano. `radius_km` devuelve
    `None` cuando ni en el epicentro se alcanza esa intensidad.
    """

    origin = _origin(report)
    if origin is None or not start <= origin <= now + timedelta(minutes=5):
        return False
    if report.magnitude is None:
        return False
    if report.source_id == "simulation" or is_drill(report.official_event_id):
        return False
    if is_withdrawn({"preferred_report": {"review_status": report.review_status}}):
        return False
    threshold = max(FELT, minimum_intensity)
    return radius_km(report.magnitude, report.depth_km, threshold) is not None


def catalog_alert_event(
    source: OfficialSource, report: OfficialReport, now: datetime
) -> dict[str, Any]:
    payload = report.to_dict()
    magnitude = report.magnitude or 0.0
    return {
        "type": "official_report_update",
        "status": "official_report_available",
        # Cada magnitud publicada es un evento distinto: si la agencia la revisa
        # al alza, el dispatcher decide si vuelve a avisar.
        "event_id": f"catalog:{source.id}:{report.official_event_id}:m{round(magnitude * 10)}",
        "origin": CATALOG_ORIGIN,
        "matched_at": now.isoformat().replace("+00:00", "Z"),
        "preferred_report": payload,
        "reports": [payload],
    }


class CatalogAlertFeed:
    def __init__(self, redis: Redis, settings: AppSettings, fetch: Fetch = fetch_catalog) -> None:
        self.redis, self.settings, self.fetch = redis, settings, fetch
        self.bus = RedisEventBus(redis, settings.stream_maxlen, SEEN_SECONDS)
        self.stop_event = asyncio.Event()

    async def run(self) -> None:
        if not self.settings.catalog_alerts_enabled:
            LOGGER.info("Alertas por catálogo apagadas (SEISMIK_CATALOG_ALERTS_ENABLED=false)")
            return
        sources = self.watched_sources()
        LOGGER.info("Alertas por catálogo vigilan %s catálogos oficiales", len(sources))
        while not self.stop_event.is_set():
            try:
                await self.poll(sources, datetime.now(timezone.utc))
            except asyncio.CancelledError:
                raise
            except Exception:
                LOGGER.exception("Catalog alert poll failed")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(
                    self.stop_event.wait(), timeout=self.settings.catalog_alerts_poll_seconds
                )

    def watched_sources(self) -> tuple[OfficialSource, ...]:
        """Catálogos que entran al ciclo automático de alertas.

        Una agencia puede quedar fuera sin salir del catálogo público: la API
        la sigue sirviendo y la app la sigue mostrando.
        """

        excluded = set(self.settings.catalog_alerts_excluded_source_ids)
        return tuple(
            source
            for source in load_sources(self.settings.official_sources_path)
            if source.enabled and source.id not in excluded
        )

    async def poll(self, sources: tuple[OfficialSource, ...], now: datetime) -> int:
        """Entrega al dispatcher los sismos nuevos; devuelve cuántos entregó."""

        start = now - timedelta(minutes=self.settings.catalog_alerts_max_age_minutes)
        timeout = self.settings.official_history_timeout_seconds
        results = await asyncio.gather(
            *(asyncio.to_thread(self.fetch, source, start, now, timeout) for source in sources),
            return_exceptions=True,
        )
        found: list[tuple[OfficialSource, OfficialReport]] = []
        for source, result in zip(sources, results, strict=True):
            if isinstance(result, BaseException):
                LOGGER.warning(
                    "Catálogo oficial falló source=%s error=%s", source.id, type(result).__name__
                )
                continue
            found.extend((source, report) for report in result)
        # Si una agencia local y el USGS traen el mismo sismo en la misma
        # consulta, llega primero el reporte local y el otro se descarta.
        found.sort(key=lambda item: (-item[0].priority, item[1].origin_time))
        delivered = 0
        for source, report in found:
            if not alertable(
                report, start, now, self.settings.catalog_alerts_minimum_intensity
            ):
                continue
            outcome = await self.bus.publish_once(
                self.settings.official_stream, catalog_alert_event(source, report, now)
            )
            delivered += int(outcome.accepted)
        return delivered
