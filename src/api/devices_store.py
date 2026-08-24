from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Mapping, cast

from redis.asyncio import Redis

from api.schemas import DeviceRegistration, DeviceTarget, Platform


class DeviceRepository:
    GEO_KEY = "seismik:devices:geo"

    def __init__(self, redis: Redis):
        self.redis = redis

    @staticmethod
    def _device_key(device_id: str) -> str:
        return f"seismik:device:{device_id}"

    @staticmethod
    def _zone_key(zone_id: str) -> str:
        return f"seismik:devices:zone:{zone_id}"

    @staticmethod
    def _token_key(platform: Platform | str, token: str) -> str:
        digest = hashlib.sha256(token.encode()).hexdigest()
        return f"seismik:device-token:{platform}:{digest}"

    async def register(self, registration: DeviceRegistration) -> None:
        old = cast(dict[str, str], await self.redis.hgetall(self._device_key(registration.device_id)))
        if old:
            await self._remove_indexes(registration.device_id, old)

        token_owner = await self.redis.get(self._token_key(registration.platform, registration.token))
        if token_owner and token_owner != registration.device_id:
            await self.unregister(str(token_owner))

        record = {
            "device_id": registration.device_id,
            "platform": registration.platform.value,
            "token": registration.token,
            "country_code": registration.country_code or "",
            "zone_id": registration.zone_id or "",
            "latitude": "" if registration.latitude is None else str(registration.latitude),
            "longitude": "" if registration.longitude is None else str(registration.longitude),
            "critical_alerts_authorized": "1" if registration.critical_alerts_authorized else "0",
            "locale": registration.locale,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        pipe = self.redis.pipeline(transaction=True)
        pipe.hset(self._device_key(registration.device_id), mapping=cast(dict[Any, Any], record))
        pipe.set(self._token_key(registration.platform, registration.token), registration.device_id)
        if registration.zone_id:
            pipe.sadd(self._zone_key(registration.zone_id), registration.device_id)
        if registration.latitude is not None and registration.longitude is not None:
            pipe.geoadd(
                self.GEO_KEY,
                [registration.longitude, registration.latitude, registration.device_id],
            )
        await pipe.execute()

    async def unregister(self, device_id: str) -> bool:
        key = self._device_key(device_id)
        old = cast(dict[str, str], await self.redis.hgetall(key))
        if not old:
            return False
        await self._remove_indexes(device_id, old)
        await self.redis.delete(key)
        return True

    async def exists(self, device_id: str) -> bool:
        return bool(await self.redis.exists(self._device_key(device_id)))

    async def recipients(
        self,
        *,
        zone_id: str | None,
        latitude: float | None,
        longitude: float | None,
        radius_km: float,
    ) -> list[DeviceTarget]:
        device_ids: set[str] = set()
        if zone_id:
            device_ids.update(cast(set[str], await self.redis.smembers(self._zone_key(zone_id))))
        if latitude is not None and longitude is not None:
            nearby = cast(list[str], await self.redis.geosearch(
                self.GEO_KEY,
                longitude=longitude,
                latitude=latitude,
                radius=radius_km,
                unit="km",
            ))
            device_ids.update(nearby)
        if not device_ids:
            return []
        pipe = self.redis.pipeline(transaction=False)
        ordered_ids = sorted(str(item) for item in device_ids)
        for device_id in ordered_ids:
            pipe.hgetall(self._device_key(device_id))
        records = await pipe.execute()
        result = []
        for device_id, record in zip(ordered_ids, records, strict=True):
            if not record or not record.get("token"):
                continue
            result.append(
                DeviceTarget(
                    device_id=device_id,
                    platform=record["platform"],
                    token=record["token"],
                    critical_alerts_authorized=record.get("critical_alerts_authorized") == "1",
                    locale=record.get("locale") or "es",
                )
            )
        return result

    async def _remove_indexes(self, device_id: str, record: Mapping[str, str]) -> None:
        pipe = self.redis.pipeline(transaction=True)
        if record.get("zone_id"):
            pipe.srem(self._zone_key(record["zone_id"]), device_id)
        if record.get("token") and record.get("platform"):
            pipe.delete(self._token_key(record["platform"], record["token"]))
        pipe.zrem(self.GEO_KEY, device_id)
        await pipe.execute()
