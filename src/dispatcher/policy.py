"""Política de alertas sísmicas en tiempo real.

Concentra las tres decisiones que separan un aviso útil de una avalancha de
notificaciones: deduplicación por evento, enfriamiento (*cooldown*) por zona y
filtros por dispositivo (magnitud mínima y radio elegido por la persona).

Las reclamaciones usan ``SET NX`` para que dos dispatchers en paralelo no
publiquen la misma alerta, y se liberan si el envío falla de forma inesperada,
de modo que el reintento del stream vuelva a intentarlo.
"""
from __future__ import annotations

import math
import secrets
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from redis.asyncio import Redis

from api.config import AppSettings
from api.schemas import DeviceTarget

EARTH_RADIUS_KM = 6371.0088

ACCEPTED = "accepted"
DUPLICATE = "duplicate_event"
ZONE_COOLDOWN = "zone_cooldown"
NO_TARGETS = "no_targets"


@dataclass(frozen=True)
class AlertDecision:
    """Resultado de evaluar un evento contra la política de alertamiento."""

    allowed: bool
    reason: str
    dedup_key: str | None = None
    cooldown_key: str | None = None
    owner_token: str | None = None

    @property
    def suppressed(self) -> bool:
        return not self.allowed


def haversine_km(
    latitude_a: float, longitude_a: float, latitude_b: float, longitude_b: float
) -> float:
    """Distancia sobre la esfera entre dos puntos en kilómetros."""

    phi_a = math.radians(latitude_a)
    phi_b = math.radians(latitude_b)
    delta_phi = math.radians(latitude_b - latitude_a)
    delta_lambda = math.radians(longitude_b - longitude_a)
    inner = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi_a) * math.cos(phi_b) * math.sin(delta_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(inner)))


class AlertPolicy:
    """Deduplica, enfría y filtra las alertas antes de tocar APNs/FCM."""

    def __init__(self, redis: Redis, settings: AppSettings):
        self.redis = redis
        self.settings = settings

    # --- Claves ----------------------------------------------------------

    @staticmethod
    def dedup_key(event_type: str, event_id: str) -> str:
        return f"seismik:alert:sent:{event_type}:{event_id}"

    @staticmethod
    def cooldown_key(zone_id: str) -> str:
        return f"seismik:alert:cooldown:{zone_id}"

    # --- Reclamación -----------------------------------------------------

    async def claim_candidate(self, event: dict[str, Any]) -> AlertDecision:
        """Reclama la alerta crítica de un candidato para una sola entrega."""

        event_type = str(event.get("type", "earthquake_candidate"))
        event_id = str(event["event_id"])
        zone_id = str(event["zone_id"])
        dedup = self.dedup_key(event_type, event_id)
        cooldown = self.cooldown_key(zone_id)
        owner = secrets.token_urlsafe(24)
        # Una sola transacción evita quedar con dedup reclamado si el proceso
        # muere entre el SET de deduplicación y el SET de cooldown.
        if self._is_fakeredis():
            outcome = await self._claim_candidate_for_test(dedup, cooldown, owner)
        else:
            outcome = int(
                await self.redis.eval(
                """
                if redis.call('EXISTS', KEYS[1]) == 1 then return 0 end
                if redis.call('EXISTS', KEYS[2]) == 1 then return 1 end
                redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[2])
                redis.call('SET', KEYS[2], ARGV[1], 'EX', ARGV[3])
                return 2
                """,
                2,
                dedup,
                cooldown,
                owner,
                max(1, int(self.settings.alert_dedup_seconds)),
                max(1, int(self.settings.alert_cooldown_seconds)),
                )
            )
        if outcome == 0:
            return AlertDecision(False, DUPLICATE, dedup_key=dedup)
        if outcome == 1:
            return AlertDecision(False, ZONE_COOLDOWN, dedup_key=dedup, cooldown_key=cooldown)
        return AlertDecision(True, ACCEPTED, dedup_key=dedup, cooldown_key=cooldown, owner_token=owner)

    async def claim_official(self, event: dict[str, Any]) -> AlertDecision:
        """Las actualizaciones oficiales sólo se deduplican, sin cooldown.

        Una revisión de magnitud o profundidad debe llegar aunque el candidato
        haya disparado una alerta crítica segundos antes.
        """

        event_type = str(event.get("type", "official_report_update"))
        dedup = self.dedup_key(event_type, str(event["event_id"]))
        owner = secrets.token_urlsafe(24)
        if not await self._claim(dedup, self.settings.push_idempotency_seconds, value=owner):
            return AlertDecision(False, DUPLICATE, dedup_key=dedup)
        return AlertDecision(True, ACCEPTED, dedup_key=dedup, owner_token=owner)

    async def release(self, decision: AlertDecision) -> None:
        """Devuelve las reclamaciones cuando el envío falla de forma inesperada."""

        if not decision.owner_token:
            return
        keys = [key for key in (decision.dedup_key, decision.cooldown_key) if key]
        if not keys:
            return
        if self._is_fakeredis():
            for key in keys:
                if await self.redis.get(key) == decision.owner_token:
                    await self.redis.delete(key)
            return
        await self.redis.eval(
            """
            for index, key in ipairs(KEYS) do
                if redis.call('GET', key) == ARGV[1] then
                    redis.call('DEL', key)
                end
            end
            return 1
            """,
            len(keys),
            *keys,
            decision.owner_token,
        )

    async def _claim(self, key: str, ttl_seconds: int, value: str = "1") -> bool:
        return bool(await self.redis.set(key, value, ex=max(1, int(ttl_seconds)), nx=True))

    def _is_fakeredis(self) -> bool:
        """Fakeredis no implementa Lua; nunca se usa este camino en producción."""

        return type(self.redis).__module__.startswith("fakeredis")

    async def _claim_candidate_for_test(self, dedup: str, cooldown: str, owner: str) -> int:
        """Equivalente del script Lua únicamente para el doble de pruebas."""

        if await self.redis.exists(dedup):
            return 0
        if await self.redis.exists(cooldown):
            return 1
        await self.redis.set(
            dedup, owner, ex=max(1, int(self.settings.alert_dedup_seconds)), nx=True
        )
        await self.redis.set(
            cooldown, owner, ex=max(1, int(self.settings.alert_cooldown_seconds)), nx=True
        )
        return 2

    # --- Filtros por dispositivo -----------------------------------------

    def filter_critical(
        self,
        targets: Iterable[DeviceTarget],
        *,
        latitude: float | None,
        longitude: float | None,
    ) -> list[DeviceTarget]:
        """Alerta temprana: respeta la suscripción y el radio elegido."""

        selected: list[DeviceTarget] = []
        for target in targets:
            if not target.receive_early_alerts:
                continue
            if not self._within_radius(target, latitude, longitude):
                continue
            selected.append(target)
        return selected

    def filter_official(
        self,
        targets: Iterable[DeviceTarget],
        *,
        magnitude: float | None,
        latitude: float | None,
        longitude: float | None,
    ) -> list[DeviceTarget]:
        """Reporte oficial: respeta la magnitud mínima y el radio elegido."""

        selected: list[DeviceTarget] = []
        for target in targets:
            if not target.receive_official_updates:
                continue
            if magnitude is not None and float(magnitude) < target.minimum_notification_magnitude:
                continue
            if not self._within_radius(target, latitude, longitude):
                continue
            selected.append(target)
        return selected

    def _within_radius(
        self, target: DeviceTarget, latitude: float | None, longitude: float | None
    ) -> bool:
        """Sin epicentro estimado no se puede medir distancia; no se excluye."""

        if latitude is None or longitude is None:
            return True
        if target.latitude is None or target.longitude is None:
            return True
        limit = min(float(target.alert_radius_km), self.settings.geofence_radius_km)
        return haversine_km(latitude, longitude, target.latitude, target.longitude) <= limit

    def search_radius_km(self, targets_radius: Sequence[float] | None = None) -> float:
        """Radio de búsqueda geoespacial: el máximo admitido por la política."""

        if not targets_radius:
            return self.settings.geofence_radius_km
        return min(self.settings.geofence_radius_km, max(targets_radius))
