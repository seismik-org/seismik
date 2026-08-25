from __future__ import annotations

import hashlib
import hmac
import json
import logging
import queue
import threading
import time

import requests

from eew.config import AlertSettings
from eew.models import EarthquakeCandidate, OfficialReportUpdate

AlertEvent = EarthquakeCandidate | OfficialReportUpdate

LOGGER = logging.getLogger(__name__)


class AlertDispatcher:
    """Saca I/O de alertas del hilo que recibe paquetes SeedLink."""

    def __init__(self, settings: AlertSettings):
        self.settings = settings
        self._queue: queue.Queue[AlertEvent | None] = queue.Queue(maxsize=100)
        self._worker = threading.Thread(target=self._run, name="alert-dispatcher", daemon=True)

    def start(self) -> None:
        self._worker.start()

    def submit(self, event: AlertEvent) -> None:
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            LOGGER.critical("Cola de alertas llena; evento descartado event_id=%s", event.event_id)

    def close(self) -> None:
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
        self._worker.join(timeout=5)

    def _run(self) -> None:
        while True:
            event = self._queue.get()
            if event is None:
                return
            self.trigger_alert(event)

    def trigger_alert(self, event: AlertEvent) -> None:
        """Hook de Fase 2: hoy imprime JSON y opcionalmente hace POST webhook."""
        payload = event.to_dict()
        print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), flush=True)
        target_url = self._target_url(event)
        if not target_url:
            return
        if not self.settings.webhook_hmac_secret:
            LOGGER.error("Webhook configured without WEBHOOK_HMAC_SECRET; refusing unsigned delivery")
            return

        body = json.dumps(
            payload, ensure_ascii=False, separators=(",", ":"), default=str
        ).encode("utf-8")

        for attempt in range(self.settings.webhook_retries + 1):
            try:
                timestamp = str(int(time.time()))
                signature = hmac.new(
                    self.settings.webhook_hmac_secret.encode("utf-8"),
                    timestamp.encode("ascii") + b"." + body,
                    hashlib.sha256,
                ).hexdigest()
                response = requests.post(
                    target_url,
                    data=body,
                    timeout=self.settings.webhook_timeout_seconds,
                    headers={
                        "User-Agent": "seismik-detector/0.3",
                        "Content-Type": "application/json",
                        "X-Seismik-Timestamp": timestamp,
                        "X-Seismik-Signature": signature,
                    },
                )
                response.raise_for_status()
                LOGGER.info("Webhook aceptado event_id=%s status=%d", event.event_id, response.status_code)
                return
            except requests.RequestException as exc:
                LOGGER.error("Falló webhook attempt=%d error=%s", attempt + 1, exc)
                if attempt < self.settings.webhook_retries:
                    time.sleep(min(2**attempt, 5))

    def _target_url(self, event: AlertEvent) -> str | None:
        if self.settings.webhook_base_url:
            path = (
                "/v1/events/candidate"
                if isinstance(event, EarthquakeCandidate)
                else "/v1/events/official-update"
            )
            return self.settings.webhook_base_url.rstrip("/") + path
        return self.settings.webhook_url
