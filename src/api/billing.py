"""Contabilidad interna de uso y créditos, independiente del procesador de pagos.

El saldo sólo puede modificarse mediante un movimiento idempotente. Paddle,
Stripe o una factura institucional se conectarán después como fuentes de esos
movimientos; nunca como la fuente de verdad para autorizar una solicitud.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TypedDict

from redis.asyncio import Redis
from redis.exceptions import WatchError


class BillingSummary(TypedDict):
    period: str
    requests: int
    events_read: int
    stations_read: int
    credit_balance_microunits: int
    payments_enabled: bool


def period_for(moment: datetime | None = None) -> str:
    return (moment or datetime.now(timezone.utc)).strftime("%Y%m")


def _meter_key(uid: str, period: str) -> str:
    return f"seismik:billing:meter:{uid}:{period}"


def _balance_key(uid: str) -> str:
    return f"seismik:billing:balance:{uid}"


async def record_usage(redis: Redis, uid: str, scope: str, key_id: str | None) -> None:
    """Registra unidades medibles después de pasar autenticación y cuota.

    La unidad es una solicitud autenticada, no una promesa de precio. Se
    conserva un agregado mensual de bajo costo hasta que exista facturación.
    """
    period = period_for()
    key = _meter_key(uid, period)
    pipe = redis.pipeline(transaction=True)
    pipe.hincrby(key, "requests", 1)
    pipe.hincrby(key, f"scope:{scope}", 1)
    pipe.hsetnx(key, "period", period)
    pipe.hsetnx(key, "first_recorded_at", datetime.now(timezone.utc).isoformat())
    if key_id:
        pipe.sadd(f"seismik:billing:keys:{uid}:{period}", key_id)
        pipe.expire(f"seismik:billing:keys:{uid}:{period}", 34_560_000)
    pipe.expire(key, 34_560_000)  # 400 días: suficiente para conciliación beta.
    await pipe.execute()


async def summary(redis: Redis, uid: str) -> BillingSummary:
    period = period_for()
    values = await redis.hgetall(_meter_key(uid, period))
    return {
        "period": period,
        "requests": int(values.get("requests", 0)),
        "events_read": int(values.get("scope:events:read", 0)),
        "stations_read": int(values.get("scope:stations:read", 0)),
        "credit_balance_microunits": int(await redis.get(_balance_key(uid)) or 0),
        "payments_enabled": False,
    }


async def apply_credit_entry(
    redis: Redis,
    uid: str,
    entry_id: str,
    delta_microunits: int,
    source: str,
) -> int:
    """Aplica un movimiento de crédito exactamente una vez.

    Es deliberadamente interno: antes de conectar un PSP, los webhooks no
    pueden acreditar saldo. ``entry_id`` será el id único del pago/factura.
    """
    event_key = f"seismik:billing:entry:{entry_id}"
    balance_key = _balance_key(uid)
    ledger_key = f"seismik:billing:ledger:{uid}"

    # WATCH/MULTI evita depender de Lua: es atómico también en Redis real y
    # permite que el simulador de pruebas valide la misma semántica.
    for _ in range(5):
        pipe = redis.pipeline(transaction=True)
        try:
            await pipe.watch(event_key)
            if await pipe.exists(event_key):
                current = await pipe.get(balance_key)
                await pipe.reset()
                return int(current or 0)
            pipe.multi()
            pipe.set(event_key, entry_id)
            pipe.incrby(balance_key, delta_microunits)
            pipe.xadd(
                ledger_key,
                {
                    "entry_id": entry_id,
                    "delta_microunits": str(delta_microunits),
                    "source": source,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            result = await pipe.execute()
            return int(result[1])
        except WatchError:
            # Otro proceso aplicó una entrada concurrente; se reevalúa sin
            # duplicar el movimiento.
            continue
        finally:
            await pipe.reset()
    raise RuntimeError("No se pudo aplicar el movimiento de crédito de forma atómica")
