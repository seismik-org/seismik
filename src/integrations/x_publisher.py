"""Publicador seguro de boletines de Seismik en X.

Sólo publica eventos oficiales. Las detecciones sin confirmación se auditan,
pero no salen a la cuenta pública: una detección no es un boletín oficial.

Ningún mensaje detiene el servicio. Uno ilegible se audita y se descarta,
porque reintentarlo no lo arregla. Un rechazo de X queda pendiente y se
reintenta, también tras un reinicio, hasta `integration_delivery_max_attempts`;
después se audita como fallido.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, cast

import requests
from redis.asyncio import Redis
from redis.exceptions import ResponseError
from requests_oauthlib import OAuth1

from api.config import AppSettings, get_settings
from runtime_health import start_health_server

LOGGER = logging.getLogger(__name__)
X_POST_URL = "https://api.x.com/2/tweets"
AUDIT_STREAM = "stream:seismik:x-audit"


def _report(event: dict[str, Any]) -> dict[str, Any]:
    report = event.get("preferred_report") or event.get("report") or {}
    return report if isinstance(report, dict) else {}


def _magnitude(event: dict[str, Any]) -> float | None:
    raw: Any = _report(event).get("magnitude") or event.get("magnitude")
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _parse(fields: dict[str, str] | None) -> dict[str, Any] | None:
    try:
        event = json.loads((fields or {})["payload"])
    except (KeyError, TypeError, ValueError):
        return None
    return event if isinstance(event, dict) else None


def eligible(event: dict[str, Any], minimum_magnitude: float) -> bool:
    """Conservador: sólo informe oficial con magnitud suficiente y fuente URL."""
    magnitude = _magnitude(event)
    return (
        event.get("type") in {"official_report_available", "official_report_update"}
        # Sin identificador todos compartirían la marca de «publicado» y sólo
        # saldría el primer boletín.
        and bool(event.get("event_id"))
        and magnitude is not None
        and magnitude >= minimum_magnitude
        and bool(_report(event).get("official_url"))
    )


def bulletin_text(event: dict[str, Any]) -> str:
    report = _report(event)
    magnitude = _magnitude(event) or 0.0
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
            try:
                rows = cast(
                    list[tuple[str, list[tuple[str, dict[str, str]]]]],
                    await self.redis.xreadgroup(
                        self.settings.x_publisher_group,
                        self.settings.x_publisher_consumer_name,
                        {self.settings.integration_stream: ">"},
                        count=self.settings.consumer_batch_size,
                        block=self.settings.consumer_block_ms,
                    ),
                )
                for _stream, items in rows:
                    for message_id, fields in items:
                        await self._handle(message_id, fields)
                await self._recover_pending()
            except asyncio.CancelledError:
                raise
            except Exception:
                # Un corte de Redis no debe tumbar el proceso: Cloud Run lo
                # reiniciaría en bucle. Se reintenta en el siguiente ciclo.
                LOGGER.exception("X publisher loop failed")
                await asyncio.sleep(1)

    async def _recover_pending(self) -> None:
        """Retoma lo que quedó sin confirmar por un rechazo de X o un reinicio.

        `xreadgroup` con ">" sólo entrega mensajes nuevos: sin esto, un boletín
        pendiente al reiniciar no se volvería a leer nunca.
        """
        result = await self.redis.xautoclaim(
            self.settings.integration_stream,
            self.settings.x_publisher_group,
            self.settings.x_publisher_consumer_name,
            min_idle_time=self.settings.pending_claim_idle_ms,
            start_id="0-0",
            count=self.settings.consumer_batch_size,
        )
        entries = result[1] if len(result) > 1 else []
        for message_id, fields in entries:
            await self._handle(message_id, fields)

    async def _handle(self, message_id: str, fields: dict[str, str] | None) -> None:
        event = _parse(fields)
        if event is None:
            LOGGER.warning("Mensaje ilegible descartado id=%s", message_id)
            await self._audit("", "skipped_malformed", source_id=message_id)
            await self._acknowledge(message_id)
            return
        event_id = str(event.get("event_id", ""))
        published_key = f"seismik:x:published:{event_id}"
        try:
            if not eligible(event, self.settings.x_publisher_minimum_magnitude):
                await self._audit(event_id, "skipped_not_official_or_below_threshold")
            elif await self.redis.set(published_key, "1", nx=True, ex=2_592_000):
                await self._publish(event, published_key)
        except Exception as exc:
            LOGGER.warning("Publicación en X fallida event_id=%s error=%s", event_id, type(exc).__name__)
            await self._record_failure(message_id, event_id)
            return
        await self._acknowledge(message_id)

    async def _publish(self, event: dict[str, Any], published_key: str) -> None:
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
        try:
            response = await asyncio.to_thread(requests.post, X_POST_URL, json={"text": text}, auth=auth, timeout=10)
            response.raise_for_status()
        except Exception:
            # No salió: se libera la marca para que el reintento lo publique en
            # vez de darlo por hecho. Tras un envío correcto la marca se queda y
            # un fallo posterior no duplica el boletín.
            await self.redis.delete(published_key)
            raise
        try:
            body = response.json()
        except ValueError:
            body = {}
        data = body.get("data") if isinstance(body, dict) else None
        post_id = str(data.get("id", "")) if isinstance(data, dict) else ""
        await self._audit(event_id, "published", post_id=post_id)

    async def _record_failure(self, message_id: str, event_id: str) -> None:
        key = self._failure_key(message_id)
        attempts = int(await self.redis.incr(key))
        await self.redis.expire(key, 86_400)
        if attempts < self.settings.integration_delivery_max_attempts:
            return  # Queda pendiente: `_recover_pending` lo reintenta.
        LOGGER.critical("Boletín no publicado en X tras %s intentos event_id=%s", attempts, event_id)
        await self._audit(event_id, "failed", attempts=str(attempts), source_id=message_id)
        await self._acknowledge(message_id)

    async def _acknowledge(self, message_id: str) -> None:
        await self.redis.xack(self.settings.integration_stream, self.settings.x_publisher_group, message_id)
        await self.redis.delete(self._failure_key(message_id))

    async def _audit(self, event_id: str, action: str, **extra: str) -> None:
        entry = {"event_id": event_id, "action": action, "at": datetime.now(timezone.utc).isoformat(), **extra}
        await self.redis.xadd(AUDIT_STREAM, cast(dict[Any, Any], entry), maxlen=self.settings.stream_maxlen, approximate=True)

    @staticmethod
    def _failure_key(message_id: str) -> str:
        return f"seismik:x:failures:{message_id}"


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
