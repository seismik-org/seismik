"""Lo que el administrador puede ver de los clientes: nada identificable.

`redact` (api.admin) ya oculta tokens, firmas, secretos e IP. Este módulo añade
la privacidad de las personas: nombres (también los de Familia), correos,
teléfonos, mensajes y comentarios libres, URLs de clientes y ubicaciones
exactas. Se aplica en la API, no en la página: el navegador del administrador
nunca recibe el dato.

Los identificadores técnicos (dispositivo, cuenta, círculo, miembro, webhook…)
salen como un código que no se puede revertir. Sirve para ver que dos entradas
son de la misma cuenta al depurar, pero no para saber de quién.

Los registros de sismos, alertas y publicaciones son datos públicos y sólo
pasan por el filtro de correos.
"""
from __future__ import annotations

import hashlib
import hmac
import re
from typing import Any

MASK = "•••"
# Registros que sólo contienen sismos oficiales o publicaciones ya públicas.
PUBLIC_STREAMS = frozenset({"official", "candidates", "alerts", "x_publisher", "facebook_audit"})
TEXT_PUBLIC_STREAMS = frozenset({"push_audit"})

EMAIL = re.compile(r"[A-Za-z0-9._%+'-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
IDENTITY_KEY = re.compile(
    r"(^|_)(display_?name|full_?name|nombre|name|names|email|correo|phone|telefono|tel|address|direccion|"
    r"contact|owner|author|reporter|username|endpoint|callback|webhook_?url)($|_)", re.I
)
FREE_TEXT_KEY = re.compile(
    r"(^|_)(message|mensaje|comment|comentario|details|detalle|note|notes|nota|description|descripcion|"
    r"text|body|title)($|_)", re.I
)
ID_KEY = re.compile(
    r"(^|_)(device_ids?|target_device_ids|uid|firebase_uid|account_id|circle_id|member_id|owner_uid|"
    r"owner_device_id|user_id|webhook_id|key_id|developer_id|client_id|installation_id)$", re.I
)
COORDINATE_KEY = re.compile(r"(^|_)(lat|latitude|lon|lng|longitude)$", re.I)


def pseudonym(value: Any, secret: str) -> str:
    digest = hmac.new(secret.encode(), str(value).encode(), hashlib.sha256).hexdigest()
    return f"id:{digest[:10]}"


class PrivateView:
    """Filtro de privacidad de un registro; se crea una vez por solicitud."""

    def __init__(self, stream: str, secret: str, admin_emails: str = ""):
        self.public = stream in PUBLIC_STREAMS
        # Las pruebas de notificación llevan el título y el texto de sismos públicos.
        self.text_is_public = stream in TEXT_PUBLIC_STREAMS
        self.secret = secret or "seismik-admin-view"
        self.admin_emails = {item.strip().casefold() for item in admin_emails.split(",") if item.strip()}

    def __call__(self, value: Any) -> Any:
        return self._walk(value, False, 0)

    def _email(self, match: re.Match[str]) -> str:
        # El correo de un administrador sale en la auditoría de sus propias acciones.
        return match.group(0) if match.group(0).casefold() in self.admin_emails else MASK

    def _walk(self, value: Any, family: bool, depth: int) -> Any:
        if depth > 12:
            return MASK
        if isinstance(value, dict):
            # Un aviso de Familia lleva el nombre hasta en el título y el cuerpo.
            data = value.get("data")
            family = family or value.get("type") == "family_status" or (
                isinstance(data, dict) and data.get("type") == "family_status"
            )
            return {key: self._field(str(key), item, family, depth) for key, item in value.items()}
        if isinstance(value, list):
            return [self._walk(item, family, depth + 1) for item in value]
        if isinstance(value, str):
            return EMAIL.sub(self._email, value)
        return value

    def _field(self, key: str, value: Any, family: bool, depth: int) -> Any:
        if value in (None, "", [], {}):
            return value
        if self.public:
            if family and (IDENTITY_KEY.search(key) or FREE_TEXT_KEY.search(key)):
                return MASK
            return self._walk(value, family, depth + 1)
        if IDENTITY_KEY.search(key):
            return MASK
        if FREE_TEXT_KEY.search(key) and (family or not self.text_is_public):
            return MASK
        if ID_KEY.search(key):
            if isinstance(value, list):
                return [pseudonym(item, self.secret) for item in value]
            return pseudonym(value, self.secret)
        if COORDINATE_KEY.search(key) and isinstance(value, (int, float)) and not isinstance(value, bool):
            # Una décima de grado son ~11 km: suficiente para juzgar un reporte, no para ubicar a alguien.
            return round(float(value), 1)
        return self._walk(value, family, depth + 1)


def view_for(stream: str, settings: Any) -> PrivateView:
    """Filtro con la clave del panel: los códigos cambian si se rota la clave."""

    secret = settings.admin_mfa_encryption_key.get_secret_value()
    return PrivateView(stream, secret, settings.admin_emails)
