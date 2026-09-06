from __future__ import annotations

import hashlib
import hmac
import json
import logging
import queue
import threading
import time
from typing import Any

import requests

from eew.config import AlertSettings
from eew.delivery import (
    DeliveryMetrics,
    DeliveryOutcome,
    DeliverySpool,
    DurableEventDelivery,
)
from eew.models import EarthquakeCandidate, OfficialReportUpdate

AlertEvent = EarthquakeCandidate | OfficialReportUpdate

LOGGER = logging.getLogger(__name__)

CANDIDATE_PATH = "/v1/events/candidate"
OFFICIAL_PATH = "/v1/events/official-update"
# 408 y 429 son transitorios; el resto de los 4xx indica un contrato inválido y
# reintentarlo sólo repetiría el rechazo.
RETRYABLE_STATUS = frozenset({408, 429})


class AlertDispatcher:
    """Saca I/O de alertas del hilo que recibe paquetes SeedLink."""

    def __init__(self, settings: AlertSettings):
        self.settings = settings
        self.metrics = DeliveryMetrics()
        self._queue: queue.Queue[AlertEvent | None] = queue.Queue(maxsize=100)
        self._worker = threading.Thread(target=self._run, name="alert-dispatcher", daemon=True)
        self._stop = threading.Event()
        self._retry_worker = threading.Thread(
            target=self._retry_loop, name="alert-retry", daemon=True
        )
        self._delivery: DurableEventDelivery | None = None
        self._delivery_lock = threading.Lock()

    def start(self) -> None:
        self._worker.start()
        if self._configured_target and self.settings.spool_directory:
            self._retry_worker.start()

    def submit(self, event: AlertEvent) -> None:
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            LOGGER.critical("Cola de alertas llena; evento descartado event_id=%s", event.event_id)

    def close(self) -> None:
        self._stop.set()
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
        self._worker.join(timeout=5)
        if self._retry_worker.is_alive():
            self._retry_worker.join(timeout=5)

    def health(self) -> dict[str, Any]:
        """Estado del enlace detector → API para la sonda de salud."""

        snapshot = self.metrics.snapshot()
        snapshot["pending"] = self._delivery.pending_count() if self._delivery else 0
        snapshot["target"] = self._configured_target
        return snapshot

    def _run(self) -> None:
        while True:
            event = self._queue.get()
            if event is None:
                return
            self.trigger_alert(event)

    def _retry_loop(self) -> None:
        while not self._stop.is_set():
            self._stop.wait(self.settings.retry_interval_seconds)
            if self._stop.is_set():
                return
            delivery = self._delivery
            if delivery is None:
                continue
            try:
                delivery.drain()
            except Exception:  # noqa: BLE001 - el reintento nunca tumba el detector
                LOGGER.exception("Fallo drenando el spool de eventos")

    def trigger_alert(self, event: AlertEvent) -> None:
        """Publica el evento en stdout y lo entrega a la API de eventos."""

        payload = event.to_dict()
        print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), flush=True)
        if not self._configured_target:
            return
        if not self.settings.webhook_hmac_secret:
            LOGGER.error("Webhook configured without WEBHOOK_HMAC_SECRET; refusing unsigned delivery")
            return

        event_type = (
            "earthquake_candidate"
            if isinstance(event, EarthquakeCandidate)
            else "official_report_update"
        )
        delivery = self._ensure_delivery()
        if delivery is None:
            self._deliver_once(event_type, payload)
            return
        delivery.submit(payload, event_type=event_type, event_id=event.event_id)

    # --- Entrega HTTP -----------------------------------------------------

    def _ensure_delivery(self) -> DurableEventDelivery | None:
        """Crea la cola durable la primera vez que hace falta."""

        if not self.settings.spool_directory:
            return None
        with self._delivery_lock:
            if self._delivery is None:
                self._delivery = DurableEventDelivery(
                    self._send,
                    DeliverySpool(
                        self.settings.spool_directory,
                        max_entries=self.settings.spool_max_entries,
                    ),
                    self.metrics,
                    retry_interval_seconds=self.settings.retry_interval_seconds,
                    max_age_seconds=self.settings.spool_max_age_seconds,
                )
            return self._delivery

    def _deliver_once(self, event_type: str, payload: dict[str, Any]) -> None:
        """Ruta sin spool: reintentos en memoria como en el Sprint 1."""

        self.metrics.record(queued=1)
        for attempt in range(self.settings.webhook_retries + 1):
            try:
                outcome = self._send(event_type, payload)
            except requests.RequestException as exc:
                LOGGER.error("Falló webhook attempt=%d error=%s", attempt + 1, exc)
                self.metrics.mark_error(str(exc))
                outcome = DeliveryOutcome(delivered=False, detail=str(exc))
            if outcome.delivered:
                self.metrics.mark_delivered(duplicate=outcome.duplicate)
                return
            if not outcome.retryable:
                return
            if attempt < self.settings.webhook_retries:
                time.sleep(min(2**attempt, 5))

    def _send(self, event_type: str, payload: dict[str, Any]) -> DeliveryOutcome:
        target_url = self._url_for(event_type)
        if target_url is None:
            return DeliveryOutcome(delivered=False, retryable=False, detail="sin destino")
        secret = self.settings.webhook_hmac_secret
        if not secret:
            return DeliveryOutcome(delivered=False, retryable=False, detail="sin secreto HMAC")

        body = json.dumps(
            payload, ensure_ascii=False, separators=(",", ":"), default=str
        ).encode("utf-8")
        timestamp = str(int(time.time()))
        signature = hmac.new(
            secret.encode("utf-8"),
            timestamp.encode("ascii") + b"." + body,
            hashlib.sha256,
        ).hexdigest()
        try:
            response = requests.post(
                target_url,
                data=body,
                timeout=self.settings.webhook_timeout_seconds,
                headers={
                    "User-Agent": "seismik-detector/0.7",
                    "Content-Type": "application/json",
                    "X-Seismik-Timestamp": timestamp,
                    "X-Seismik-Signature": signature,
                },
            )
        except requests.RequestException as exc:
            self.metrics.mark_error(str(exc))
            raise
        status_code = getattr(response, "status_code", 0)
        if 200 <= status_code < 300:
            LOGGER.info(
                "Evento aceptado por la API event_type=%s status=%d", event_type, status_code
            )
            return DeliveryOutcome(delivered=True, duplicate=_is_duplicate(response))
        detail = f"HTTP {status_code}"
        self.metrics.mark_error(detail)
        retryable = status_code >= 500 or status_code in RETRYABLE_STATUS or status_code == 0
        LOGGER.error(
            "La API rechazó el evento event_type=%s status=%d retryable=%s",
            event_type,
            status_code,
            retryable,
        )
        return DeliveryOutcome(delivered=False, retryable=retryable, detail=detail)

    @property
    def _configured_target(self) -> str | None:
        return self.settings.webhook_base_url or self.settings.webhook_url

    def _url_for(self, event_type: str) -> str | None:
        if self.settings.webhook_base_url:
            path = CANDIDATE_PATH if event_type == "earthquake_candidate" else OFFICIAL_PATH
            return self.settings.webhook_base_url.rstrip("/") + path
        return self.settings.webhook_url

    def _target_url(self, event: AlertEvent) -> str | None:
        """Compatibilidad con el Sprint 1: destino calculado desde el evento."""

        event_type = (
            "earthquake_candidate"
            if isinstance(event, EarthquakeCandidate)
            else "official_report_update"
        )
        return self._url_for(event_type)


def _is_duplicate(response: object) -> bool:
    """La API responde 202 con duplicate=true cuando el bus ya vio el evento."""

    try:
        decoded = response.json()  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 - un cuerpo no JSON no invalida la entrega
        return False
    return isinstance(decoded, dict) and bool(decoded.get("duplicate"))
