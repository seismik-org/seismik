"""Opt-in sharing of recently registered locations, not live GPS or a safety check-in."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from typing import Any, cast

from redis.asyncio import Redis

from api.accounts import device_account_key
from api.config import AppSettings
from api.family import automatic_location_key
from api.schemas import DeviceTarget


async def share_alert_locations(
    redis: Redis, settings: AppSettings, event: dict[str, Any], targets: list[DeviceTarget]
) -> None:
    if not settings.push_enabled or settings.push_mode != "production":
        return
    if any(event.get(key) for key in ("simulation", "is_test", "historical", "drill")):
        return
    related = str(event.get("candidate_event_id") or event.get("event_id") or "")
    if not related or related.startswith(("local-", "test-", "simulation-", "historical-")):
        return
    now = datetime.now(timezone.utc)
    # Prefer the freshest of a person's linked phones, not arbitrary target ordering.
    points: dict[str, tuple[datetime, float, float]] = {}
    for target in targets:
        uid = await redis.get(device_account_key(target.device_id))
        if not uid or await redis.get(automatic_location_key(str(uid))) != "1":
            continue
        record = await redis.hgetall(f"seismik:device:{target.device_id}")
        try:
            observed = datetime.fromisoformat(str(record["updated_at"]))
            latitude, longitude = float(record["latitude"]), float(record["longitude"])
            if not math.isfinite(latitude) or not math.isfinite(longitude):
                continue
            if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                continue
            if not timedelta(0) <= now - observed <= timedelta(hours=1):
                continue
        except (KeyError, ValueError, TypeError):
            continue
        if str(uid) not in points or observed > points[str(uid)][0]:
            points[str(uid)] = (observed, latitude, longitude)
    for uid, (observed, latitude, longitude) in points.items():
        if await redis.get(automatic_location_key(uid)) != "1":
            continue
        circle = cast(str | None, await redis.get(f"seismik:family:account:{uid}"))
        if not circle or not await redis.sismember(f"seismik:family:members:{circle}", uid):
            continue
        if not await redis.set(f"seismik:family:auto-alert:{uid}:{related}", "1", nx=True, ex=86400):
            continue
        profile = await redis.hgetall(f"seismik:family:member:{circle}:{uid}")
        location = {
            "latitude": round(latitude, 2), "longitude": round(longitude, 2),
            "precision": "approximate", "source": "automatic_alert",
            "registered_at": observed.isoformat(), "shared_at": now.isoformat(),
            "expires_at": (now + timedelta(hours=1)).isoformat(), "related_event_id": related,
        }
        notification = {
            "type": "family_status", "status": "location_only",
            "event_id": f"family-location-{target_id(uid, related)}",
            "circle_id": str(circle), "member_id": uid,
            "display_name": profile.get("display_name") or "Tu familiar",
            "related_event_id": related, "reported_at": now.isoformat(),
            "message": "Ubicación aproximada registrada recientemente. Estado sin confirmar.",
        }
        pipe = redis.pipeline(transaction=True)
        pipe.set(f"seismik:family:location:{circle}:{uid}", json.dumps(location), ex=3600)
        pipe.xadd(settings.family_notification_stream, {"payload": json.dumps(notification)},
                  maxlen=settings.stream_maxlen, approximate=True)
        try:
            await pipe.execute()
        except Exception:
            await redis.delete(f"seismik:family:auto-alert:{uid}:{related}")
            raise


def target_id(uid: str, event_id: str) -> str:
    return hashlib.sha256(f"{uid}:{event_id}".encode()).hexdigest()[:24]
