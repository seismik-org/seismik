from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import ResponseError, WatchError

PUBLISH_ONCE_LUA = """
local created = redis.call('SET', KEYS[1], '1', 'EX', ARGV[1], 'NX')
if not created then
  return {0, ''}
end
local stream_id = redis.call(
  'XADD', KEYS[2], 'MAXLEN', '~', ARGV[2], '*',
  'payload', ARGV[3], 'event_id', ARGV[4], 'event_type', ARGV[5]
)
return {1, stream_id}
"""


@dataclass(frozen=True)
class PublishResult:
    accepted: bool
    stream_id: str | None


class RedisEventBus:
    def __init__(self, redis: Redis, stream_maxlen: int, idempotency_seconds: int):
        self.redis = redis
        self.stream_maxlen = stream_maxlen
        self.idempotency_seconds = idempotency_seconds

    async def publish_once(self, stream: str, event: dict[str, Any]) -> PublishResult:
        event_id = str(event["event_id"])
        event_type = str(event["type"])
        seen_key = f"seismik:webhook:seen:{event_type}:{event_id}"
        payload = json.dumps(event, ensure_ascii=False, separators=(",", ":"), default=str)
        try:
            result = await self.redis.eval(
                PUBLISH_ONCE_LUA,
                2,
                seen_key,
                stream,
                self.idempotency_seconds,
                self.stream_maxlen,
                payload,
                event_id,
                event_type,
            )
        except ResponseError as exc:
            if "unknown command" not in str(exc).lower() or "eval" not in str(exc).lower():
                raise
            return await self._publish_once_transaction(
                seen_key, stream, payload, event_id, event_type
            )
        accepted = bool(int(result[0]))
        stream_id = result[1] or None
        if isinstance(stream_id, bytes):
            stream_id = stream_id.decode()
        return PublishResult(accepted=accepted, stream_id=stream_id)

    async def _publish_once_transaction(
        self, seen_key: str, stream: str, payload: str, event_id: str, event_type: str
    ) -> PublishResult:
        """Fallback atomico para Redis con EVAL deshabilitado y para fakeredis."""

        while True:
            async with self.redis.pipeline(transaction=True) as pipe:
                try:
                    await pipe.watch(seen_key)
                    if await pipe.exists(seen_key):
                        return PublishResult(False, None)
                    pipe.multi()
                    pipe.set(seen_key, "1", ex=self.idempotency_seconds)
                    pipe.xadd(
                        stream,
                        {"payload": payload, "event_id": event_id, "event_type": event_type},
                        maxlen=self.stream_maxlen,
                        approximate=True,
                    )
                    _created, stream_id = await pipe.execute()
                    if isinstance(stream_id, bytes):
                        stream_id = stream_id.decode()
                    return PublishResult(True, str(stream_id))
                except WatchError:
                    continue

    async def publish(self, stream: str, event: dict[str, Any]) -> str:
        result = await self.redis.xadd(
            stream,
            {
                "payload": json.dumps(event, ensure_ascii=False, separators=(",", ":"), default=str),
                "event_id": str(event["event_id"]),
                "event_type": str(event["type"]),
            },
            maxlen=self.stream_maxlen,
            approximate=True,
        )
        return result.decode() if isinstance(result, bytes) else str(result)
