"""Account-owned plans. Paid activation is administrative, never client supplied."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from typing import Any

from redis.asyncio import Redis

from api.config import AppSettings, get_settings

# Keep the legacy usage-plan ID so existing Redis profiles remain valid.
PLAN_NAMES = {
    "free": "Always Free with API Key",
    "pay_as_you_use": "Pay-as-you-go",
    "pro": "Pro",
    "max": "Max",
    "ultra": "Ultra",
    "enterprise": "Enterprise",
}

# USD/month, minute, day, month, active keys. Finite caps bound compute/egress.
PLAN_LIMITS = {
    "pay_as_you_use": (None, 120, 20_000, 200_000, 5),
    "pro": (19, 120, 10_000, 50_000, 5),
    "max": (49, 240, 20_000, 150_000, 10),
    "ultra": (129, 360, 40_000, 400_000, 20),
    "enterprise": (None, None, None, None, None),
}


def catalog(settings: AppSettings) -> list[dict[str, Any]]:
    descriptions = {
        "free": "Para aprender y probar la API. Sin tarjeta ni cargos.",
        "pay_as_you_use": "Sin mensualidad. Eventos: US$0,0005 por consulta; estaciones: US$0,001. Saldo desde US$5.",
        "pro": "Para proyectos personales e integraciones pequeñas. Consultas incluidas hasta las cuotas.",
        "max": "Para aplicaciones en crecimiento. Más consultas y claves con gasto mensual fijo.",
        "ultra": "Para equipos con mayor volumen. Capacidad acotada y sin cargos automáticos por excedentes.",
        "enterprise": "Acuerdo a medida: volumen, integración y soporte se negocian con Seismik.",
    }
    plans = []
    for plan_id, name in PLAN_NAMES.items():
        price, minute, day, month, keys = (
            (0, settings.developer_free_requests_per_minute,
             settings.developer_free_requests_per_day, 30_000,
             settings.developer_max_active_keys)
            if plan_id == "free" else PLAN_LIMITS[plan_id]
        )
        billing_model = "subscription"
        if plan_id == "free":
            billing_model = "free"
        elif plan_id == "pay_as_you_use":
            billing_model = "usage"
        elif plan_id == "enterprise":
            billing_model = "negotiated"
        price_label = f"US${price} / mes"
        if plan_id == "free":
            price_label = "Gratis"
        elif plan_id == "pay_as_you_use":
            price_label = "Desde US$5"
        elif plan_id == "enterprise":
            price_label = "A negociar"
        plans.append({
            "id": plan_id,
            "name": name,
            "description": descriptions[plan_id],
            "billing_model": billing_model,
            "availability": "available" if plan_id == "free" else "contact",
            "price_label": price_label,
            "currency": "USD",
            "monthly_price_microunits": price * 1_000_000 if price is not None else None,
            "requests_per_minute": minute,
            "requests_per_day": day,
            "requests_per_month": month,
            "max_active_keys": keys,
            "overage_policy": "hard_stop",
        })
    return plans


async def account_plan(redis: Redis, uid: str, settings: AppSettings) -> dict[str, Any]:
    profile = await redis.hgetall(f"seismik:developer-profile:{uid}")
    plan_id = profile.get("plan", "free")
    if plan_id not in PLAN_NAMES:
        plan_id = "free"  # Unknown/legacy values never grant higher permissions.
    plan = next(item for item in catalog(settings) if item["id"] == plan_id)
    defaults = {
        "requests_per_minute": settings.developer_free_requests_per_minute,
        "requests_per_day": settings.developer_free_requests_per_day,
        "max_active_keys": settings.developer_max_active_keys,
        "requests_per_month": 30_000,
    }
    # Administrative activation applies published limits, never a client choice.
    for field, default in defaults.items():
        plan[field] = default if plan_id == "free" else int(profile.get(f"plan_{field}", plan[field] or default))
    plan["status"] = "active"
    plan["assigned_at"] = profile.get("plan_assigned_at")
    plan["payments_enabled"] = False
    return plan


async def assign_plan(
    redis: Redis, uid: str, plan_id: str, *, actor: str, reason: str,
    requests_per_minute: int | None = None, requests_per_day: int | None = None,
    max_active_keys: int | None = None, requests_per_month: int | None = None,
) -> None:
    """Administrative only; all keys immediately follow the account's plan."""
    if plan_id not in PLAN_NAMES or not uid.strip() or not actor.strip() or not reason.strip():
        raise ValueError("Valid plan, account UID, actor and reason are required")
    limits = {"requests_per_minute": requests_per_minute, "requests_per_day": requests_per_day, "max_active_keys": max_active_keys, "requests_per_month": requests_per_month}
    if any(value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 1) for value in limits.values()):
        raise ValueError("Plan limits must be positive integers")
    now = datetime.now(timezone.utc).isoformat()
    profile_key = f"seismik:developer-profile:{uid}"
    pipe = redis.pipeline(transaction=True)
    pipe.hdel(profile_key, *(f"plan_{field}" for field in limits))
    pipe.hset(profile_key, mapping={"plan": plan_id, "plan_assigned_at": now, **{f"plan_{field}": value for field, value in limits.items() if value is not None}})
    pipe.xadd("stream:seismik:developer-plan-audit", {"uid": uid, "plan": plan_id, "actor": actor, "reason": reason, "timestamp": now})
    await pipe.execute()


def main() -> None:
    parser = argparse.ArgumentParser(description="Assign a negotiated developer account plan; does not enable payments.")
    parser.add_argument("uid")
    parser.add_argument("plan", choices=PLAN_NAMES)
    parser.add_argument("--actor", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--requests-per-minute", type=int)
    parser.add_argument("--requests-per-day", type=int)
    parser.add_argument("--max-active-keys", type=int)
    parser.add_argument("--requests-per-month", type=int)
    args = parser.parse_args()

    async def run() -> None:
        redis = Redis.from_url(get_settings().redis_url, decode_responses=True)
        try:
            await assign_plan(redis, args.uid, args.plan, actor=args.actor, reason=args.reason, requests_per_minute=args.requests_per_minute, requests_per_day=args.requests_per_day, max_active_keys=args.max_active_keys, requests_per_month=args.requests_per_month)
        finally:
            await redis.aclose()
    asyncio.run(run())


if __name__ == "__main__":
    main()
