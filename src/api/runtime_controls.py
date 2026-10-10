"""Persistent pause switches shared by the API and running workers."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from redis.asyncio import Redis

PAUSE_KEY = "seismik:operations:paused"
FEATURES = {
    "alerts": "Alertas sísmicas a dispositivos",
    "x": "Publicaciones automáticas en X",
    "facebook": "Publicaciones automáticas en Facebook",
}


async def paused(redis: Redis, feature: str) -> bool:
    # No local cache: a pause is checked immediately before each delivery.
    return await redis.hget(PAUSE_KEY, feature) in {"1", b"1"}


INFO_PREFIX = "seismik:operations:info:"
_STARTED_AT = datetime.now(timezone.utc).isoformat()


def service_info(role: str, flags: dict[str, Any]) -> dict[str, Any]:
    """Quién soy y con qué ajustes corro. Cloud Run define K_SERVICE y K_REVISION."""

    return {
        "role": role, "service": os.environ.get("K_SERVICE", ""), "revision": os.environ.get("K_REVISION", ""),
        "started_at": _STARTED_AT, "flags": flags,
    }


async def announce(
    redis: Redis, capabilities: dict[str, bool], info: dict[str, Any] | None = None,
) -> None:
    for feature, configured in capabilities.items():
        await redis.set(
            f"seismik:operations:worker:{feature}",
            json.dumps({"configured": configured}), ex=90,
        )
    if info:
        # Qué versión corre y con qué ajustes: sólo banderas, nunca secretos.
        await redis.set(f"{INFO_PREFIX}{info['role']}", json.dumps(info, default=str), ex=90)


async def heartbeat(
    redis: Redis, capabilities: dict[str, bool], info: dict[str, Any] | None = None,
) -> None:
    while True:
        try:
            await announce(redis, capabilities, info)
        except Exception:
            logging.getLogger(__name__).exception("Operations heartbeat failed")
        await asyncio.sleep(30)


async def state(redis: Redis) -> list[dict[str, Any]]:
    result = []
    for feature, label in FEATURES.items():
        raw = await redis.get(f"seismik:operations:worker:{feature}")
        try:
            configured = bool(raw and json.loads(raw).get("configured") is True)
        except (ValueError, AttributeError, TypeError):
            configured = False
        is_paused = await paused(redis, feature)
        result.append({"id": feature, "label": label, "configured": configured,
                       "worker_available": bool(raw), "paused": is_paused,
                       "enabled": configured and not is_paused})
    return result
