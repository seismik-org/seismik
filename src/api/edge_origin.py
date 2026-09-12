"""Cierra la API a lo que no llegue por el Worker de Cloudflare.

Cloud Run publica cada servicio en una URL `*.run.app` alcanzable desde
Internet. Con el Worker delante, esa URL es una puerta lateral: salta las
cabeceras de seguridad, la protección de Cloudflare y cualquier regla de tráfico
que se configure allí. Es el mismo problema que tenía la VM cuando su IP
respondía directamente.

El Worker añade un secreto compartido en `X-Seismik-Origin-Auth`, y los
servicios internos que llaman a la API por su URL directa (el reenviador de
Pub/Sub) envían el mismo. Sin secreto configurado la guardia no hace nada: así
el código puede desplegarse antes de repartir el valor, sin cortar el servicio.
"""
from __future__ import annotations

import hmac
import json

from starlette.types import ASGIApp, Receive, Scope, Send

EDGE_ORIGIN_HEADER = "x-seismik-origin-auth"

# Las sondas de salud no traen cabeceras propias y la respuesta no revela nada.
EXEMPT_PATHS = frozenset({"/health/live"})


class EdgeOriginGuard:
    """Middleware ASGI que exige el secreto de origen en cada petición HTTP."""

    def __init__(self, app: ASGIApp, secret: str = "") -> None:
        self.app = app
        self._secret = secret.encode()
        self._header = EDGE_ORIGIN_HEADER.encode()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or not self._secret
            or scope.get("path") in EXEMPT_PATHS
            or self._authorized(scope)
        ):
            await self.app(scope, receive, send)
            return

        body = json.dumps({"detail": "Origin not allowed"}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 403,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})

    def _authorized(self, scope: Scope) -> bool:
        provided = b""
        for name, value in scope.get("headers", []):
            if name == self._header:
                provided = value
                break
        # En tiempo constante: la latencia no debe revelar cuántos bytes coinciden.
        return hmac.compare_digest(provided, self._secret)
