"""Reenvía eventos Pub/Sub a la API firmada, conservando su contrato HTTP."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import signal
import threading
import time
from typing import Any

import requests
from google.cloud import pubsub_v1

from runtime_health import start_health_server

LOGGER = logging.getLogger(__name__)
_STOP = threading.Event()


def _endpoint(base_url: str, event_type: str) -> str:
    suffix = "/candidate" if event_type == "earthquake_candidate" else "/official-update"
    return base_url.rstrip("/") + "/v1/events" + suffix


def _deliver(message: pubsub_v1.subscriber.message.Message, *, base_url: str, secret: str) -> None:
    try:
        envelope: dict[str, Any] = json.loads(message.data)
        event_type = str(envelope["event_type"])
        if event_type not in {"earthquake_candidate", "official_report_update"}:
            raise ValueError("unsupported event type")
        body = json.dumps(envelope["payload"], ensure_ascii=False, separators=(",", ":")).encode()
        timestamp = str(int(time.time()))
        signature = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
        response = requests.post(
            _endpoint(base_url, event_type),
            data=body,
            timeout=10,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "seismik-pubsub-forwarder/1",
                "X-Seismik-Timestamp": timestamp,
                "X-Seismik-Signature": signature,
            },
        )
        if 200 <= response.status_code < 300:
            message.ack()
            return
        if 400 <= response.status_code < 500 and response.status_code not in {408, 429}:
            LOGGER.error("Evento descartado por API status=%s", response.status_code)
            message.ack()
            return
        raise RuntimeError(f"API status={response.status_code}")
    except Exception as exc:  # Pub/Sub controla reintento y DLQ
        LOGGER.warning("Reintento Pub/Sub: %s", type(exc).__name__)
        message.nack()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)sZ %(levelname)s %(name)s %(message)s")
    subscription = os.environ["SEISMIK_PUBSUB_SUBSCRIPTION"]
    base_url = os.environ["SEISMIK_EVENT_FORWARD_URL"]
    secret = os.environ["SEISMIK_WEBHOOK_HMAC_SECRET"]
    health_server = start_health_server()
    subscriber = pubsub_v1.SubscriberClient()
    future = subscriber.subscribe(
        subscription,
        lambda message: _deliver(message, base_url=base_url, secret=secret),
    )
    for name in (signal.SIGINT, signal.SIGTERM):
        signal.signal(name, lambda *_args: _STOP.set())
    try:
        while not _STOP.wait(1):
            if future.done():
                future.result()
    finally:
        future.cancel()
        health_server.shutdown()
        subscriber.close()


if __name__ == "__main__":
    main()
