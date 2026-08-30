from __future__ import annotations

import asyncio
import json
import logging
import signal
from typing import Any, cast

from redis.asyncio import Redis
from redis.exceptions import ResponseError

from api.config import AppSettings, get_settings
from api.devices_store import DeviceRepository
from dispatcher.push import PushDispatcher, PushResult, notification_content
from runtime_health import start_health_server

LOGGER = logging.getLogger(__name__)


class StreamConsumer:
    def __init__(
        self,
        redis: Redis,
        settings: AppSettings,
        devices: DeviceRepository,
        push: PushDispatcher,
    ):
        self.redis = redis
        self.settings = settings
        self.devices = devices
        self.push = push
        self.streams = (settings.candidate_stream, settings.official_stream)
        self._stop = asyncio.Event()

    async def ensure_groups(self) -> None:
        for stream in self.streams:
            try:
                await self.redis.xgroup_create(
                    stream, self.settings.dispatcher_group, id="0-0", mkstream=True
                )
            except ResponseError as exc:
                if "BUSYGROUP" not in str(exc):
                    raise

    async def run(self) -> None:
        await self.ensure_groups()
        while not self._stop.is_set():
            try:
                raw_messages = await self.redis.xreadgroup(
                    self.settings.dispatcher_group,
                    self.settings.consumer_name,
                    {stream: ">" for stream in self.streams},
                    count=self.settings.consumer_batch_size,
                    block=self.settings.consumer_block_ms,
                )
                messages = cast(
                    list[tuple[str, list[tuple[str, dict[str, str]]]]], raw_messages
                )
                for stream, entries in messages:
                    for message_id, fields in entries:
                        await self._handle(stream, message_id, fields)
                await self._recover_pending()
            except asyncio.CancelledError:
                raise
            except Exception:
                LOGGER.exception("Dispatcher loop failed")
                await asyncio.sleep(1)

    def stop(self) -> None:
        self._stop.set()

    async def _handle(self, stream: str, message_id: str, fields: dict[str, str]) -> None:
        try:
            event = json.loads(fields["payload"])
            event_type = event.get("type")
            if event_type in {"earthquake_candidate", "crowdsourced_earthquake_candidate"}:
                await self._handle_candidate(event)
            elif event_type == "official_report_update":
                await self._handle_official(event)
            else:
                raise ValueError(f"Unsupported event type: {event_type}")
            await self.redis.xack(stream, self.settings.dispatcher_group, message_id)
            await self.redis.delete(self._failure_key(stream, message_id))
        except Exception:
            LOGGER.exception("Message failed stream=%s id=%s", stream, message_id)
            await self._record_failure(stream, message_id, fields)

    async def _handle_candidate(self, event: dict[str, Any]) -> None:
        zone_id = str(event["zone_id"])
        latitude = event.get("estimated_latitude")
        longitude = event.get("estimated_longitude")
        mapping = json.dumps({"zone_id": zone_id, "latitude": latitude, "longitude": longitude})
        await self.redis.set(
            f"seismik:event-zone:{event['event_id']}", mapping, ex=self.settings.event_zone_ttl_seconds
        )
        cooldown_key = f"seismik:alert:cooldown:{zone_id}"
        if await self.redis.exists(cooldown_key):
            LOGGER.info("Critical alert suppressed by cooldown zone=%s", zone_id)
            return
        targets = await self.devices.recipients(
            zone_id=zone_id,
            latitude=latitude,
            longitude=longitude,
            radius_km=self.settings.geofence_radius_km,
        )
        targets = [target for target in targets if target.receive_early_alerts]
        result = await self.push.send(event, targets, critical=True)
        await self._record_dry_run(event, result, critical=True)
        await self._remove_invalid(result.invalid_device_ids)
        await self.redis.set(cooldown_key, event["event_id"], ex=self.settings.alert_cooldown_seconds)
        LOGGER.info(
            "Critical push event_id=%s attempted=%d succeeded=%d",
            event["event_id"], result.attempted, result.succeeded,
        )

    async def _handle_official(self, event: dict[str, Any]) -> None:
        sent_key = f"seismik:push:sent:{event['event_id']}"
        if await self.redis.exists(sent_key):
            return
        report = event["preferred_report"]
        mapping_raw = await self.redis.get(f"seismik:event-zone:{event['candidate_event_id']}")
        mapping = json.loads(mapping_raw) if mapping_raw else {}
        targets = await self.devices.recipients(
            zone_id=mapping.get("zone_id"),
            latitude=report.get("latitude", mapping.get("latitude")),
            longitude=report.get("longitude", mapping.get("longitude")),
            radius_km=self.settings.geofence_radius_km,
        )
        magnitude = report.get("magnitude")
        targets = [
            target
            for target in targets
            if target.receive_official_updates
            and (magnitude is None or float(magnitude) >= target.minimum_notification_magnitude)
        ]
        result = await self.push.send(event, targets, critical=False)
        await self._record_dry_run(event, result, critical=False)
        await self._remove_invalid(result.invalid_device_ids)
        await self.redis.set(sent_key, "1", ex=self.settings.push_idempotency_seconds)
        LOGGER.info(
            "Official push event_id=%s attempted=%d succeeded=%d",
            event["event_id"], result.attempted, result.succeeded,
        )

    async def _remove_invalid(self, device_ids: tuple[str, ...]) -> None:
        for device_id in device_ids:
            await self.devices.unregister(device_id)

    async def _record_dry_run(
        self, event: dict[str, Any], result: PushResult, *, critical: bool
    ) -> None:
        """Persiste la evidencia TEST sin incluir tokens de APNs/FCM."""

        if not result.dry_run:
            return
        title, body, payload = notification_content(event, critical=critical)
        await self.redis.xadd(
            self.settings.push_audit_stream,
            {
                "event_id": str(event["event_id"]),
                "event_type": str(event["type"]),
                "test": "true",
                "critical": "true" if critical else "false",
                "attempted": str(result.attempted),
                "target_device_ids": json.dumps(result.target_device_ids),
                "payload": json.dumps(
                    {"title": title, "body": body, "data": payload},
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            },
            maxlen=self.settings.stream_maxlen,
            approximate=True,
        )

    async def _recover_pending(self) -> None:
        for stream in self.streams:
            result = await self.redis.xautoclaim(
                stream,
                self.settings.dispatcher_group,
                self.settings.consumer_name,
                min_idle_time=self.settings.pending_claim_idle_ms,
                start_id="0-0",
                count=self.settings.consumer_batch_size,
            )
            entries = result[1] if len(result) > 1 else []
            for message_id, fields in entries:
                await self._handle(stream, message_id, fields)

    async def _record_failure(
        self, stream: str, message_id: str, fields: dict[str, str]
    ) -> None:
        key = self._failure_key(stream, message_id)
        pipe = self.redis.pipeline(transaction=True)
        pipe.incr(key)
        pipe.expire(key, 86_400)
        attempts, _ = await pipe.execute()
        if int(attempts) < self.settings.max_delivery_attempts:
            return
        await self.redis.xadd(
            self.settings.dead_letter_stream,
            {
                "source_stream": stream,
                "source_id": message_id,
                "payload": fields.get("payload", ""),
                "attempts": str(attempts),
            },
            maxlen=self.settings.stream_maxlen,
            approximate=True,
        )
        await self.redis.xack(stream, self.settings.dispatcher_group, message_id)
        await self.redis.delete(key)
        LOGGER.critical("Message moved to dead letter stream=%s id=%s", stream, message_id)

    @staticmethod
    def _failure_key(stream: str, message_id: str) -> str:
        return f"seismik:dispatch:failures:{stream}:{message_id}"


async def run_dispatcher() -> None:
    health_server = start_health_server()
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    devices = DeviceRepository(redis)
    worker = StreamConsumer(
        redis,
        settings,
        devices,
        PushDispatcher(settings, invalid_token_handler=devices.unregister),
    )
    loop = asyncio.get_running_loop()
    for signal_name in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signal_name, worker.stop)
        except (NotImplementedError, RuntimeError):
            pass
    try:
        await worker.run()
    finally:
        health_server.shutdown()
        await redis.aclose()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)sZ %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(run_dispatcher())


if __name__ == "__main__":
    main()
