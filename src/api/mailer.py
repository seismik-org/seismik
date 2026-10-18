"""Correo saliente de Seismik por Resend.

Dos remitentes, ambos del dominio verificado seismik.org: `cuentas@` para lo que tiene que ver con una
cuenta o con datos personales (se puede responder; las respuestas van a `mail_reply_to`) y `noreply@`
para avisos automáticos que no esperan respuesta. Sin `SEISMIK_RESEND_API_KEY` el módulo no envía nada
y lo dice con `False`: un correo que no sale nunca debe romper la operación que lo originó.
"""

from __future__ import annotations

import html
import logging
from dataclasses import dataclass
from typing import Literal

import httpx

from api.config import AppSettings

LOGGER = logging.getLogger(__name__)

RESEND_URL = "https://api.resend.com/emails"
SEND_TIMEOUT_SECONDS = 8.0
FOOTER_TEXT = (
    "Seismik es un proyecto independiente; no representa a ninguna entidad pública.\n"
    "Política de privacidad: https://seismik.org/terms-of-privacy/"
)


@dataclass(frozen=True)
class Message:
    to: str
    subject: str
    text: str
    sender: Literal["cuentas", "noreply"] = "cuentas"
    # Evita un segundo correo si el mismo hecho se notifica dos veces (reintentos).
    idempotency_key: str | None = None


def _html(text: str) -> str:
    paragraphs = "".join(
        f'<p style="margin:0 0 14px">{html.escape(block).replace(chr(10), "<br>")}</p>'
        for block in text.strip().split("\n\n")
    )
    return (
        '<div style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;'
        f'font-size:16px;line-height:1.5;color:#10182b;max-width:560px">{paragraphs}</div>'
    )


class Mailer:
    def __init__(self, settings: AppSettings, client: httpx.AsyncClient | None = None):
        self.settings = settings
        self._client = client

    @property
    def enabled(self) -> bool:
        return bool(self.settings.resend_api_key.get_secret_value())

    async def send(self, message: Message) -> bool:
        """Envía y devuelve si Resend lo aceptó. Nunca lanza ni registra el correo del destinatario."""

        if not self.enabled:
            return False
        sender = self.settings.mail_cuentas_from if message.sender == "cuentas" else self.settings.mail_noreply_from
        body = f"{message.text.strip()}\n\n--\n{FOOTER_TEXT}"
        payload: dict[str, object] = {
            "from": sender,
            "to": [message.to],
            "subject": message.subject,
            "text": body,
            "html": _html(body),
        }
        if message.sender == "cuentas" and self.settings.mail_reply_to:
            payload["reply_to"] = self.settings.mail_reply_to
        headers = {"Authorization": f"Bearer {self.settings.resend_api_key.get_secret_value()}"}
        if message.idempotency_key:
            headers["Idempotency-Key"] = message.idempotency_key
        try:
            if self._client is not None:
                response = await self._client.post(RESEND_URL, json=payload, headers=headers)
            else:
                async with httpx.AsyncClient(timeout=SEND_TIMEOUT_SECONDS) as client:
                    response = await client.post(RESEND_URL, json=payload, headers=headers)
        except httpx.HTTPError as error:
            LOGGER.warning("Resend no respondió: %s", type(error).__name__)
            return False
        if response.status_code >= 300:
            # Sólo el código: el cuerpo puede repetir el destinatario.
            LOGGER.warning("Resend rechazó un correo con estado %s", response.status_code)
            return False
        return True
