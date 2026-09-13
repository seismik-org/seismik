"""Publicador seguro de boletines de Seismik en X.

Sólo publica eventos oficiales. Las detecciones sin confirmación se auditan,
pero no salen a la cuenta pública: una detección no es un boletín oficial.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

import requests
from requests_oauthlib import OAuth1
from redis.asyncio import Redis
from redis.exceptions import ResponseError

from api.config import AppSettings, get_settings
from runtime_health import start_health_server

LOGGER = logging.getLogger(__name__)
X_POST_URL = "https://api.x.com/2/tweets"


def eligible(event: dict[str, Any], minimum_magnitude: float) -> bool:
    """Conservador: sólo informe oficial con magnitud suficiente y fuente URL."""
    report = event.get("preferred_report") or event.get("report") or {}
    return (
        event.get("type") in {"official_report_available", "official_report_update"}
        and float(report.get("magnitude") or event.get("magnitude") or 0) >= minimum_magnitude
        and bool(report.get("official_url"))
    )


def bulletin_text(event: dict[str, Any]) -> str:
    report = event.get("preferred_report") or event.get("report") or {}
    magnitude = float(report.get("magnitude") or event.get("magnitude"))
    place = str(report.get("place") or report.get("title") or "ubicación en evaluación")
    source = str(report.get("source") or "fuente oficial")
    origin = str(report.get("origin_time") or event.get("occurred_at") or "")
    text = f"Boletín sísmico Seismik · M{magnitude:.1f}\n{place}\nFuente: {source}\n{origin}".strip()
    return text[:280]


class XPublisher:
    def __init__(self, redis: Redis, settings: AppSettings) -> None:
        self.redis, self.settings = redis, settings
        self.stop_event = asyncio.Event()

    async def ensure_group(self) -> None:
        try:
            await self.redis.xgroup_create(self.settings.integration_stream, self.settings.x_publisher_group, id="0-0", mkstream=True)
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def run(self) -> None:
        await self.ensure_group()
        while not self.stop_event.is_set():
            rows = await self.redis.xreadgroup(self.settings.x_publisher_group, self.settings.x_publisher_consumer_name, {self.settings.integration_stream: ">"}, count=10, block=1000)
            for _stream, items in rows:
                for message_id, fields in items:
                    await self._handle(message_id, fields)

    async def _handle(self, message_id: str, fields: dict[str, str]) -> None:
        event = json.loads(fields["payload"])
        event_id = str(event.get("event_id", ""))
        if not eligible(event, self.settings.x_publisher_minimum_magnitude):
            await self._audit(event_id, "skipped_not_official_or_below_threshold")
        elif await self.redis.set(f"seismik:x:published:{event_id}", "1", nx=True, ex=2_592_000):
            await self._publish(event)
        await self.redis.xack(self.settings.integration_stream, self.settings.x_publisher_group, message_id)

    async def _publish(self, event: dict[str, Any]) -> None:
        event_id = str(event["event_id"])
        text = bulletin_text(event)
        if not self.settings.x_publisher_enabled or self.settings.x_publisher_dry_run:
            await self._audit(event_id, "dry_run", text=text)
            return
        auth = OAuth1(
            self.settings.x_consumer_key.get_secret_value(),
            self.settings.x_consumer_secret.get_secret_value(),
            self.settings.x_access_token.get_secret_value(),
            self.settings.x_access_token_secret.get_secret_value(),
        )
        response = await asyncio.to_thread(requests.post, X_POST_URL, json={"text": text}, auth=auth, timeout=10)
        if not response.ok:
            await self.redis.delete(f"seismik:x:published:{event_id}")
            response.raise_for_status()
        await self._audit(event_id, "published", post_id=str(response.json().get("data", {}).get("id", "")))

    async def _audit(self, event_id: str, action: str, **extra: str) -> None:
        await self.redis.xadd("stream:seismik:x-audit", {"event_id": event_id, "action": action, "at": datetime.now(timezone.utc).isoformat(), **extra}, maxlen=self.settings.stream_maxlen, approximate=True)


async def run_x_publisher() -> None:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    health = start_health_server()
    try:
        await XPublisher(redis, settings).run()
    finally:
        health.shutdown()
        await redis.aclose()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_x_publisher())


if __name__ == "__main__":
    main()
