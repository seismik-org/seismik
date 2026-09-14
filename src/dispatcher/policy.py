"""Política de alertas sísmicas en tiempo real.

Concentra las decisiones que separan un aviso útil de una avalancha de
notificaciones: deduplicación por evento y por sismo, enfriamiento (*cooldown*)
por zona y a quién le llega cada aviso.

A quién le llega lo decide el perímetro de sacudida (api/felt_area.py): la
intensidad que se espera en la ubicación de cada teléfono. La magnitud mínima y
el radio que elige la persona sólo se usan cuando no hay perímetro, porque el
sismo todavía no tiene magnitud o ubicación. Así un sismo fuerte que sacude a
alguien siempre hace sonar la alarma, sin importar su configuración.

Las reclamaciones usan ``SET NX`` para que dos dispatchers en paralelo no
publiquen la misma alerta, y se liberan si el envío falla de forma inesperada,
de modo que el reintento del stream vuelva a intentarlo.
"""
from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Literal, Sequence, cast

from redis.asyncio import Redis

from api.config import AppSettings
from api.felt_area import FELT, LIGHT, MAX_RADIUS_KM, STRONG, haversine_km, intensity_at, radius_km
from api.schemas import DeviceTarget

__all__ = ["AlertPolicy", "AlertDecision", "haversine_km"]

# La alerta temprana llega antes que las ondas: desde sacudida ligera (IV) vale
# la pena protegerse. Es el umbral de ShakeAlert en las apps públicas.
EARLY_ALARM_MMI = LIGHT
# Sacudida fuerte (VI): la alarma suena siempre, sin importar la configuración.
ALWAYS_ALARM_MMI = STRONG
# Un reporte oficial llega cuando el sismo ya pasó: se avisa a quien lo sintió.
OFFICIAL_NOTICE_MMI = FELT

Delivery = Literal["alarm", "notice"]
ALARM: Literal["alarm"] = "alarm"
NOTICE: Literal["notice"] = "notice"

ACCEPTED = "accepted"
DUPLICATE = "duplicate_event"
DUPLICATE_QUAKE = "duplicate_quake"
ZONE_COOLDOWN = "zone_cooldown"
NO_TARGETS = "no_targets"

# Sismos que llegan de los catálogos oficiales (integrations/catalog_alerts.py)
# y no de una detección propia.
CATALOG_ORIGIN = "official_catalog"

OFFICIAL_QUAKES_KEY = "seismik:alert:official-quakes"
# Dos reportes son el mismo sismo si sus orígenes y epicentros están así de cerca.
SAME_QUAKE_SECONDS = 90.0
SAME_QUAKE_KM = 150.0
# Una revisión sólo vuelve a avisar si la magnitud sube al menos esto.
REVISION_MAGNITUDE_STEP = 0.5


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


def _origin(value: Any) -> datetime | None:
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _as_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


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
        """Las actualizaciones oficiales se deduplican por evento y por sismo, sin cooldown.

        Una revisión de magnitud o profundidad debe llegar aunque el candidato
        haya disparado una alerta crítica segundos antes. En cambio, el mismo
        sismo reportado por otra agencia, o por la detección propia y el
        catálogo a la vez, sólo vuelve a avisar si su magnitud sube.
        """

        event_type = str(event.get("type", "official_report_update"))
        dedup = self.dedup_key(event_type, str(event["event_id"]))
        report = event.get("preferred_report")
        if isinstance(report, dict) and await self._is_known_quake(report):
            return AlertDecision(False, DUPLICATE_QUAKE, dedup_key=dedup)
        owner = secrets.token_urlsafe(24)
        if not await self._claim(dedup, self.settings.push_idempotency_seconds, value=owner):
            return AlertDecision(False, DUPLICATE, dedup_key=dedup)
        return AlertDecision(True, ACCEPTED, dedup_key=dedup, owner_token=owner)

    async def remember_official_quake(self, report: dict[str, Any]) -> None:
        """Se llama tras enviar: si el envío falla, el reintento no se toma por duplicado."""

        origin = _origin(report.get("origin_time"))
        latitude, longitude = _as_float(report.get("latitude")), _as_float(report.get("longitude"))
        if origin is None or latitude is None or longitude is None:
            return
        stamp = origin.timestamp()
        member = json.dumps(
            {
                "id": report.get("official_event_id"),
                "source": report.get("source_id"),
                "lat": latitude,
                "lon": longitude,
                "mag": _as_float(report.get("magnitude")),
            },
            separators=(",", ":"),
        )
        await self.redis.zadd(OFFICIAL_QUAKES_KEY, {member: stamp})
        await self.redis.zremrangebyscore(OFFICIAL_QUAKES_KEY, "-inf", stamp - 172_800)

    async def _is_known_quake(self, report: dict[str, Any]) -> bool:
        origin = _origin(report.get("origin_time"))
        latitude, longitude = _as_float(report.get("latitude")), _as_float(report.get("longitude"))
        if origin is None or latitude is None or longitude is None:
            return False
        magnitude = _as_float(report.get("magnitude"))
        stamp = origin.timestamp()
        for raw in await self.redis.zrangebyscore(
            OFFICIAL_QUAKES_KEY, stamp - SAME_QUAKE_SECONDS, stamp + SAME_QUAKE_SECONDS
        ):
            known = json.loads(cast(str, raw))
            if haversine_km(known["lat"], known["lon"], latitude, longitude) > SAME_QUAKE_KM:
                continue
            known_magnitude = known.get("mag")
            if (
                magnitude is not None
                and known_magnitude is not None
                and magnitude >= float(known_magnitude) + REVISION_MAGNITUDE_STEP
            ):
                continue
            return True
        return False

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
        magnitude: float | None = None,
        depth_km: float | None = None,
    ) -> list[DeviceTarget]:
        """Alerta temprana: quién debe protegerse antes de que lleguen las ondas.

        Con magnitud y epicentro manda el perímetro: suena desde sacudida ligera
        para quien recibe alertas tempranas y desde sacudida fuerte para todos.
        Sin esos datos no hay perímetro y se conserva el radio de la persona.
        """

        selected: list[DeviceTarget] = []
        for target in targets:
            intensity = self._intensity(target, latitude, longitude, magnitude, depth_km)
            if intensity is None:
                if target.receive_early_alerts and self._within_radius(target, latitude, longitude):
                    selected.append(target)
            elif intensity >= ALWAYS_ALARM_MMI or (
                target.receive_early_alerts and intensity >= EARLY_ALARM_MMI
            ):
                selected.append(target)
        return selected

    def classify_official(
        self,
        target: DeviceTarget,
        *,
        magnitude: float | None,
        latitude: float | None,
        longitude: float | None,
        depth_km: float | None = None,
        origin_time: Any = None,
        now: datetime | None = None,
    ) -> Delivery | None:
        """Reporte oficial: alarma, aviso o nada para un dispositivo.

        - Sacudida fuerte (VI o más): alarma, sin importar la configuración.
          Si el sismo ya es viejo, un aviso: la alarma dejó de ser útil.
        - Se sintió (III a V): aviso para quien recibe reportes oficiales.
        - Menos: nada, aunque la magnitud supere el mínimo elegido.
        """

        intensity = self._intensity(target, latitude, longitude, magnitude, depth_km)
        if intensity is None:
            if not target.receive_official_updates:
                return None
            if magnitude is not None and float(magnitude) < target.minimum_notification_magnitude:
                return None
            return NOTICE if self._within_radius(target, latitude, longitude) else None
        if intensity >= ALWAYS_ALARM_MMI:
            return ALARM if self._alarm_still_useful(origin_time, now) else NOTICE
        if intensity >= OFFICIAL_NOTICE_MMI and target.receive_official_updates:
            return NOTICE
        return None

    def split_official(
        self,
        targets: Iterable[DeviceTarget],
        *,
        magnitude: float | None,
        latitude: float | None,
        longitude: float | None,
        depth_km: float | None = None,
        origin_time: Any = None,
    ) -> tuple[list[DeviceTarget], list[DeviceTarget]]:
        """Separa a quién le suena la alarma de a quién le llega un aviso."""

        now = datetime.now(timezone.utc)
        alarms: list[DeviceTarget] = []
        notices: list[DeviceTarget] = []
        for target in targets:
            delivery = self.classify_official(
                target,
                magnitude=magnitude,
                latitude=latitude,
                longitude=longitude,
                depth_km=depth_km,
                origin_time=origin_time,
                now=now,
            )
            if delivery == ALARM:
                alarms.append(target)
            elif delivery == NOTICE:
                notices.append(target)
        return alarms, notices

    def filter_official(
        self,
        targets: Iterable[DeviceTarget],
        *,
        magnitude: float | None,
        latitude: float | None,
        longitude: float | None,
        depth_km: float | None = None,
    ) -> list[DeviceTarget]:
        """Todos los que reciben algo del reporte oficial, alarma o aviso."""

        candidates = list(targets)
        alarms, notices = self.split_official(
            candidates, magnitude=magnitude, latitude=latitude, longitude=longitude, depth_km=depth_km
        )
        chosen = {target.device_id for target in (*alarms, *notices)}
        return [target for target in candidates if target.device_id in chosen]

    def _intensity(
        self,
        target: DeviceTarget,
        latitude: float | None,
        longitude: float | None,
        magnitude: float | None,
        depth_km: float | None,
    ) -> float | None:
        if (
            magnitude is None
            or latitude is None
            or longitude is None
            or target.latitude is None
            or target.longitude is None
        ):
            return None
        distance = haversine_km(latitude, longitude, target.latitude, target.longitude)
        return intensity_at(float(magnitude), depth_km, distance)

    def _alarm_still_useful(self, origin_time: Any, now: datetime | None) -> bool:
        origin = _origin(origin_time) if origin_time is not None else None
        if origin is None:
            return True
        elapsed = (now or datetime.now(timezone.utc)) - origin
        return elapsed <= timedelta(minutes=self.settings.official_alarm_max_age_minutes)

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

    def perimeter_search_radius_km(
        self, magnitude: float | None, depth_km: float | None, intensity: float
    ) -> float:
        """Radio para buscar teléfonos: el perímetro si es mayor que la geocerca.

        Un M7 se siente a más de 250 km; buscar sólo en la geocerca dejaría
        fuera a quien lo sintió.
        """

        base = self.settings.geofence_radius_km
        if magnitude is None:
            return base
        perimeter = radius_km(float(magnitude), depth_km, intensity) or 0.0
        return min(MAX_RADIUS_KM, max(base, perimeter))
