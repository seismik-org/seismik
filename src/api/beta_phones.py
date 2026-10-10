"""Teléfonos de prueba (beta) que el panel puede inscribir y usar en simulacros.

Lo comparten la API (que los gestiona) y el dispatcher (que vuelve a comprobar,
al enviar, que cada teléfono sigue inscrito). El identificador del teléfono no
es un dato personal, pero el panel sólo muestra el código `ref` y las últimas
cuatro letras.
"""
from __future__ import annotations

import hashlib

PHONES_KEY = "seismik:admin:beta-phones"
DRILL_KEY_PREFIX = "seismik:admin:drill:"
DRILL_INDEX_KEY = "seismik:admin:drills"


def phone_ref(device_id: str) -> str:
    return hashlib.sha256(device_id.encode()).hexdigest()[:16]


def digest16(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]
