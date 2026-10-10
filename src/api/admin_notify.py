"""Aviso opcional cuando alguien hace una acción sensible en el panel de administración.

Si `SEISMIK_ADMIN_ALERT_WEBHOOK_URL` está definida (Slack, Discord o similar) se envía una
línea corta. Nunca incluye datos de clientes. Un fallo del aviso no frena la acción.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

LOGGER = logging.getLogger(__name__)
_PENDING: set[asyncio.Task[None]] = set()


async def _post(url: str, text: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            await client.post(url, json={"text": text, "content": text})
    except Exception:  # el aviso es un extra: no debe romper la acción ya hecha
        LOGGER.warning("No se pudo enviar el aviso de acción sensible", exc_info=True)


def notify(settings: Any, text: str) -> None:
    url = settings.admin_alert_webhook_url.get_secret_value().strip()
    if not url.startswith("https://"):
        return
    task = asyncio.get_running_loop().create_task(_post(url, f"Seismik Admin · {text}"))
    _PENDING.add(task)
    task.add_done_callback(_PENDING.discard)
