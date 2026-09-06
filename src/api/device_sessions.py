"""Tokens de sesión rotables para instalaciones móviles verificadas.

Una aplicación distribuida no puede guardar un secreto común: cualquiera puede
extraerlo del APK o IPA. Este módulo emite una capacidad aleatoria por
instalación después de validar App Check y sólo conserva su hash en Redis.
"""
from __future__ import annotations

import hashlib
import secrets

from redis.asyncio import Redis


class DeviceSessionRepository:
    def __init__(self, redis: Redis, *, ttl_seconds: int):
        self.redis = redis
        self.ttl_seconds = ttl_seconds

    @staticmethod
    def _digest(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @classmethod
    def _token_key(cls, token: str) -> str:
        return f"seismik:device-session:{cls._digest(token)}"

    @staticmethod
    def _device_key(device_id: str) -> str:
        return f"seismik:device-session-device:{device_id}"

    async def issue(self, device_id: str) -> str:
        """Rota cualquier sesión anterior de la misma instalación."""

        previous_digest_raw = await self.redis.get(self._device_key(device_id))
        previous_digest = (
            previous_digest_raw.decode("utf-8")
            if isinstance(previous_digest_raw, bytes)
            else previous_digest_raw
        )
        if previous_digest:
            await self.redis.delete(f"seismik:device-session:{previous_digest}")
        token = secrets.token_urlsafe(32)
        digest = self._digest(token)
        pipe = self.redis.pipeline(transaction=True)
        pipe.set(self._token_key(token), device_id, ex=self.ttl_seconds)
        pipe.set(self._device_key(device_id), digest, ex=self.ttl_seconds)
        await pipe.execute()
        return token

    async def resolve(self, token: str) -> str | None:
        device_id_raw = await self.redis.get(self._token_key(token))
        if not device_id_raw:
            return None
        device_id = (
            device_id_raw.decode("utf-8")
            if isinstance(device_id_raw, bytes)
            else str(device_id_raw)
        )
        # Renovación deslizante: una instalación usada conserva su sesión, sin
        # convertirla en una credencial eterna.
        pipe = self.redis.pipeline(transaction=True)
        pipe.expire(self._token_key(token), self.ttl_seconds)
        pipe.expire(self._device_key(device_id), self.ttl_seconds)
        await pipe.execute()
        return device_id

    async def revoke(self, device_id: str) -> None:
        digest_raw = await self.redis.get(self._device_key(device_id))
        digest = digest_raw.decode("utf-8") if isinstance(digest_raw, bytes) else digest_raw
        pipe = self.redis.pipeline(transaction=True)
        pipe.delete(self._device_key(device_id))
        if digest:
            pipe.delete(f"seismik:device-session:{digest}")
        await pipe.execute()
