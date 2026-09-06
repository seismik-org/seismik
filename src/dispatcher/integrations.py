"""Entrega durable de webhooks de organizaciones, separada del push móvil."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from typing import Any, cast

import httpx
from redis.asyncio import Redis
from redis.exceptions import ResponseError

from api.config import AppSettings, get_settings
from integrations.security import derive_webhook_secret
from runtime_health import start_health_server

LOGGER = logging.getLogger(__name__)


def _wire_event(event: dict[str, Any]) -> dict[str, Any]:
    """Contrato mínimo, explícitamente no apto para control físico."""
    return {
        "version": "2026-09-03",
        "safety_mode": "simulation_only",
        "action_prohibited": "Do not use this event to control physical equipment or life-safety systems.",
        "event": event,
    }


class IntegrationConsumer:
    def __init__(self, redis: Redis, settings: AppSettings, client: httpx.AsyncClient | None = None) -> None:
        self.redis = redis
        self.settings = settings
        self.client = client or httpx.AsyncClient(timeout=settings.integration_delivery_timeout_seconds, follow_redirects=False)
        self._owns_client = client is None
        self._stop = asyncio.Event()
        self._semaphore = asyncio.Semaphore(settings.integration_delivery_concurrency)

    async def ensure_group(self) -> None:
        try:
            await self.redis.xgroup_create(self.settings.integration_stream, self.settings.integration_dispatcher_group, id="0-0", mkstream=True)
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def run(self) -> None:
        await self.ensure_group()
        try:
            while not self._stop.is_set():
                items = cast(list[tuple[str, list[tuple[str, dict[str, str]]]]], await self.redis.xreadgroup(
                    self.settings.integration_dispatcher_group, self.settings.integration_consumer_name,
                    {self.settings.integration_stream: ">"}, count=self.settings.consumer_batch_size,
                    block=self.settings.consumer_block_ms,
                ))
                for _stream, entries in items:
                    for message_id, fields in entries:
                        await self._handle(message_id, fields)
        finally:
            if self._owns_client:
                await self.client.aclose()

    def stop(self) -> None:
        self._stop.set()

    async def _handle(self, message_id: str, fields: dict[str, str]) -> None:
        try:
            event = json.loads(fields["payload"])
            await self._deliver_all(event, message_id)
            await self.redis.xack(self.settings.integration_stream, self.settings.integration_dispatcher_group, message_id)
            await self.redis.delete(self._failure_key(message_id))
        except Exception as exc:
            LOGGER.warning("Integration delivery failed id=%s error=%s", message_id, type(exc).__name__)
            await self._retry_or_dead_letter(message_id, fields)

    async def _deliver_all(self, event: dict[str, Any], delivery_id: str) -> None:
        ids = cast(set[str], await self.redis.smembers("seismik:webhooks:active"))
        records = [
            cast(dict[str, str], record)
            for record in await asyncio.gather(
                *(self.redis.hgetall(f"seismik:webhook:{item}") for item in ids)
            )
        ]
        matching = [
            record
            for record in records
            if record
            and record.get("status") == "active"
            and event.get("type") in set(record.get("event_types", "").split(","))
        ]
        await asyncio.gather(*(self._deliver(record, event, delivery_id) for record in matching))

    async def _deliver(self, record: dict[str, str], event: dict[str, Any], delivery_id: str) -> None:
        payload = _wire_event(event)
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        secret = derive_webhook_secret(
            self.settings.integration_webhook_master_secret.get_secret_value(),
            record["webhook_id"],
        )
        signature = hmac.new(secret.encode(), f"{timestamp}.".encode() + raw, hashlib.sha256).hexdigest()
        async with self._semaphore:
            response = await self.client.post(record["endpoint"], content=raw, headers={
                "Content-Type": "application/json",
                "User-Agent": "Seismik-Webhook/0.1",
                "X-Seismik-Event-Id": str(event["event_id"]),
                "X-Seismik-Delivery-Id": delivery_id,
                "X-Seismik-Timestamp": timestamp,
                "X-Seismik-Signature": f"sha256={signature}",
                "X-Seismik-Safety-Mode": "simulation_only",
            })
        if not 200 <= response.status_code < 300:
            raise httpx.HTTPStatusError("Webhook rejected", request=response.request, response=response)
        await self.redis.hset(f"seismik:webhook:{record['webhook_id']}", mapping={"last_delivered_at": timestamp, "last_error": ""})
        await self.redis.xadd(self.settings.integration_audit_stream, {"action": "webhook.delivered", "webhook_id": record["webhook_id"], "event_id": str(event["event_id"]), "at": timestamp}, maxlen=self.settings.stream_maxlen, approximate=True)

    async def _retry_or_dead_letter(self, message_id: str, fields: dict[str, str]) -> None:
        key = self._failure_key(message_id)
        attempts = await self.redis.incr(key)
        await self.redis.expire(key, 86_400)
        if int(attempts) < self.settings.integration_delivery_max_attempts:
            return
        await self.redis.xadd(self.settings.integration_dead_letter_stream, {"source_id": message_id, "payload": fields.get("payload", ""), "attempts": str(attempts)}, maxlen=self.settings.stream_maxlen, approximate=True)
        await self.redis.xack(self.settings.integration_stream, self.settings.integration_dispatcher_group, message_id)
        await self.redis.delete(key)

    @staticmethod
    def _failure_key(message_id: str) -> str:
        return f"seismik:integration:failures:{message_id}"


async def run_integrations() -> None:
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    worker = IntegrationConsumer(redis, settings)
    health_server = start_health_server()
    try:
        await worker.run()
    finally:
        health_server.shutdown()
        await redis.aclose()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)sZ %(levelname)s %(name)s %(message)s")
    asyncio.run(run_integrations())


if __name__ == "__main__":
    main()
