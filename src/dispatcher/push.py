from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import firebase_admin  # type: ignore[import-untyped]
from aioapns import APNs, NotificationRequest, PushType
from firebase_admin import credentials, messaging

from api.config import AppSettings
from api.schemas import DeviceTarget, Platform

LOGGER = logging.getLogger(__name__)
InvalidTokenHandler = Callable[[str], Awaitable[object]]


@dataclass(frozen=True)
class PushResult:
    attempted: int
    succeeded: int
    invalid_device_ids: tuple[str, ...] = ()
    dry_run: bool = False
    target_device_ids: tuple[str, ...] = ()


class PushDispatcher:
    def __init__(
        self,
        settings: AppSettings,
        invalid_token_handler: InvalidTokenHandler | None = None,
    ):
        self.settings = settings
        self.invalid_token_handler = invalid_token_handler
        # aioapns conserva y reutiliza su conexion HTTP/2. No se crea un cliente
        # por token, evitando handshakes TLS en la ruta critica.
        self.apns: APNs | None = self._build_apns() if settings.push_enabled else None
        self.firebase_app: firebase_admin.App | None = (
            self._build_firebase() if settings.push_enabled else None
        )

    async def send(
        self, event: dict[str, Any], targets: Iterable[DeviceTarget], *, critical: bool
    ) -> PushResult:
        target_list = list(targets)
        if self.settings.push_mode == "testers":
            allowlist = set(self.settings.push_test_device_ids)
            target_list = [item for item in target_list if item.device_id in allowlist]
        if not target_list:
            return PushResult(attempted=0, succeeded=0)
        if not self.settings.push_enabled:
            LOGGER.warning(
                "Push disabled; dry dispatch event_id=%s targets=%d",
                event.get("event_id"),
                len(target_list),
            )
            return PushResult(
                attempted=len(target_list),
                succeeded=0,
                dry_run=True,
                target_device_ids=tuple(item.device_id for item in target_list),
            )

        ios = [item for item in target_list if item.platform is Platform.IOS]
        android = [item for item in target_list if item.platform is Platform.ANDROID]
        apns_result, fcm_result = await asyncio.gather(
            self._send_apns(event, ios, critical=critical),
            self._send_fcm(event, android, critical=critical),
        )
        return PushResult(
            attempted=apns_result.attempted + fcm_result.attempted,
            succeeded=apns_result.succeeded + fcm_result.succeeded,
            invalid_device_ids=apns_result.invalid_device_ids + fcm_result.invalid_device_ids,
            target_device_ids=tuple(item.device_id for item in target_list),
        )

    async def _send_apns(
        self, event: dict[str, Any], targets: list[DeviceTarget], *, critical: bool
    ) -> PushResult:
        if not targets:
            return PushResult(0, 0)
        if self.apns is None:
            raise RuntimeError("APNs credentials are not configured")
        title, body, data = notification_content(event, critical=critical)
        semaphore = asyncio.Semaphore(self.settings.apns_concurrency)

        async def send_one(target: DeviceTarget) -> tuple[bool, bool]:
            use_critical = critical and target.critical_alerts_authorized
            aps: dict[str, Any] = {
                "alert": {"title": title, "body": body},
                "thread-id": str(
                    event.get("zone_id")
                    or event.get("candidate_event_id")
                    or event.get("thread_id")
                    or "seismik"
                ),
                "interruption-level": (
                    "critical" if use_critical else ("time-sensitive" if critical else "active")
                ),
                "sound": (
                    {"critical": 1, "name": "alarm.aiff", "volume": 1.0}
                    if use_critical
                    else "default"
                ),
            }
            request = NotificationRequest(
                device_token=target.token,
                message={"aps": aps, **data},
                notification_id=apns_notification_id(str(event["event_id"])),
                time_to_live=30 if critical else 3600,
                priority=10,
                collapse_key=(
                    None
                    if critical
                    else collapse_key(str(event.get("candidate_event_id", event["event_id"])))
                ),
                push_type=PushType.ALERT,
            )
            async with semaphore:
                result = await self.apns.send_notification(request)  # type: ignore[union-attr]
            invalid = result.description in {
                "BadDeviceToken",
                "Unregistered",
                "DeviceTokenNotForTopic",
            }
            if invalid:
                await self._purge_invalid(target.device_id)
            return result.is_successful, invalid

        outcomes: list[tuple[bool, bool]] = []
        for offset in range(0, len(targets), self.settings.push_batch_size):
            batch = targets[offset : offset + self.settings.push_batch_size]
            outcomes.extend(await asyncio.gather(*(send_one(target) for target in batch)))
        invalid = tuple(
            target.device_id
            for target, (_success, is_invalid) in zip(targets, outcomes, strict=True)
            if is_invalid
        )
        return PushResult(
            attempted=len(targets),
            succeeded=sum(success for success, _invalid in outcomes),
            invalid_device_ids=invalid,
        )

    async def _send_fcm(
        self, event: dict[str, Any], targets: list[DeviceTarget], *, critical: bool
    ) -> PushResult:
        if not targets:
            return PushResult(0, 0)
        if self.firebase_app is None:
            raise RuntimeError("Firebase credentials are not configured")
        title, body, payload = notification_content(event, critical=critical)
        data = {key: stringify(value) for key, value in payload.items()}
        data["channel_id"] = "seismic_critical_alerts" if critical else "seismic_updates"
        semaphore = asyncio.Semaphore(self.settings.fcm_concurrency)

        async def send_chunk(batch: list[DeviceTarget]) -> tuple[int, list[str]]:
            message = messaging.MulticastMessage(
                tokens=[target.token for target in batch],
                data=data,
                # La alerta critica es data-only: el isolate de Flutter crea la
                # notificacion local full-screen en el canal ya provisionado.
                notification=(
                    None if critical else messaging.Notification(title=title, body=body)
                ),
                android=messaging.AndroidConfig(
                    priority="high" if critical else "normal",
                    ttl=timedelta(seconds=30 if critical else 3600),
                    notification=(
                        None
                        if critical
                        else messaging.AndroidNotification(
                            channel_id="seismic_updates",
                            sound="default",
                            visibility="public",
                        )
                    ),
                ),
            )
            async with semaphore:
                response = await messaging.send_each_for_multicast_async(
                    message, app=self.firebase_app
                )
            invalid: list[str] = []
            for target, item in zip(batch, response.responses, strict=True):
                if item.success:
                    continue
                error = item.exception
                if isinstance(
                    error, (messaging.UnregisteredError, messaging.SenderIdMismatchError)
                ):
                    invalid.append(target.device_id)
                    await self._purge_invalid(target.device_id)
                LOGGER.warning("FCM rejected device_id=%s error=%s", target.device_id, error)
            return response.success_count, invalid

        chunks = [
            targets[offset : offset + 500]
            for offset in range(0, len(targets), 500)
        ]
        results = await asyncio.gather(*(send_chunk(chunk) for chunk in chunks))
        return PushResult(
            attempted=len(targets),
            succeeded=sum(succeeded for succeeded, _invalid in results),
            invalid_device_ids=tuple(
                device_id for _succeeded, invalid in results for device_id in invalid
            ),
        )

    async def _purge_invalid(self, device_id: str) -> None:
        if self.invalid_token_handler is not None:
            await self.invalid_token_handler(device_id)

    def _build_apns(self) -> APNs | None:
        required = (
            self.settings.apns_key_path,
            self.settings.apns_key_id,
            self.settings.apns_team_id,
            self.settings.apns_topic,
        )
        if not all(required):
            return None
        key = Path(self.settings.apns_key_path or "").read_text(encoding="utf-8")
        return APNs(
            key=key,
            key_id=self.settings.apns_key_id,
            team_id=self.settings.apns_team_id,
            topic=self.settings.apns_topic,
            use_sandbox=self.settings.apns_use_sandbox,
        )

    def _build_firebase(self) -> firebase_admin.App | None:
        try:
            return firebase_admin.get_app("seismik-push")
        except ValueError:
            credential = (
                credentials.Certificate(self.settings.firebase_credentials_path)
                if self.settings.firebase_credentials_path
                else credentials.ApplicationDefault()
            )
            return firebase_admin.initialize_app(credential, name="seismik-push")


def notification_content(
    event: dict[str, Any], *, critical: bool
) -> tuple[str, str, dict[str, Any]]:
    if event.get("type") == "family_status":
        return family_notification_content(event)
    if event.get("type") == "official_report_update":
        report = event["preferred_report"]
        magnitude = report.get("magnitude")
        depth = report.get("depth_km")
        magnitude_text = (
            f"M {magnitude:.1f}" if isinstance(magnitude, (int, float)) else "Magnitud pendiente"
        )
        depth_text = f", profundidad {depth:.0f} km" if isinstance(depth, (int, float)) else ""
        title = "Reporte s\u00edsmico oficial"
        body = f"{magnitude_text}{depth_text}. {report.get('place') or report.get('agency')}"
        data = {
            "type": event["type"],
            "event_id": event["event_id"],
            "candidate_event_id": event["candidate_event_id"],
            "official_event_id": report.get("official_event_id"),
            "origin_time": report.get("origin_time"),
            "jurisdiction": report.get("jurisdiction"),
            "latitude": report["latitude"],
            "longitude": report["longitude"],
            "magnitude": report.get("magnitude"),
            "depth_km": report.get("depth_km"),
            "agency": report.get("agency"),
            "attribution": report.get("attribution"),
            "place": report.get("place"),
            "official_url": report.get("official_url"),
        }
        return title, body, data

    title = "\u00a1ALERTA S\u00cdSMICA!"
    body = (
        "\u00a1Ag\u00e1chate, C\u00fabrete y Suj\u00e9tate! "
        "Al\u00e9jate de ventanas y objetos que puedan caer."
    )
    return title, body, {
        "type": event["type"],
        "event_id": event["event_id"],
        "zone_id": event["zone_id"],
        "detected_at": event["detected_at"],
        "estimated_latitude": event.get("estimated_latitude"),
        "estimated_longitude": event.get("estimated_longitude"),
        "critical": critical,
    }


def family_notification_content(event: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    """Aviso a la familia tras un reporte de estado.

    Los datos que viajan al teléfono se eligen uno a uno: el identificador de la
    cuenta del autor y el del círculo sirven al dispatcher, no a los familiares.
    """

    name = str(event.get("display_name") or "Tu familiar")
    needs_help = event.get("status") == "need_help"
    title = f"{name} necesita ayuda" if needs_help else f"{name} está bien"
    message = str(event.get("message") or "").strip()
    default_body = (
        "Reportó que necesita ayuda. Abre Seismik para ver dónde está."
        if needs_help
        else "Reportó que está a salvo. Abre Seismik para ver a tu familia."
    )
    return title, message or default_body, {
        "type": "family_status",
        "event_id": event["event_id"],
        "status": event.get("status"),
        "display_name": name,
        "reported_at": event.get("reported_at"),
    }


def stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def apns_notification_id(event_id: str) -> str:
    try:
        return str(UUID(event_id))
    except ValueError:
        return str(uuid5(NAMESPACE_URL, event_id))


def collapse_key(value: str) -> str:
    encoded = value.encode("utf-8")
    return value if len(encoded) <= 64 else hashlib.sha256(encoded).hexdigest()
