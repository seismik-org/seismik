"""Entrega de candidatos SeedLink a una cola durable de Pub/Sub."""
from __future__ import annotations

import json
from typing import Any

from google.cloud import pubsub_v1

from eew.delivery import DeliveryOutcome


class PubSubEventPublisher:
    """Publica una envoltura mínima; Pub/Sub conserva el mensaje hasta su ACK."""

    def __init__(self, topic: str, timeout_seconds: float = 10.0) -> None:
        self.topic = topic
        self.timeout_seconds = timeout_seconds
        self.client = pubsub_v1.PublisherClient()

    def publish(self, event_type: str, payload: dict[str, Any]) -> DeliveryOutcome:
        body = json.dumps(
            {"event_type": event_type, "payload": payload},
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        try:
            self.client.publish(self.topic, body, event_type=event_type).result(
                timeout=self.timeout_seconds
            )
        except Exception as exc:  # el llamador mantiene su métrica de fallo
            return DeliveryOutcome(delivered=False, detail=f"Pub/Sub: {type(exc).__name__}: {exc}")
        return DeliveryOutcome(delivered=True)
