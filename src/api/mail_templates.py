"""Textos de los correos de Seismik, todos en español."""

from __future__ import annotations

from api.mailer import Message


def account_erased(to: str, *, request_id: str) -> Message:
    return Message(
        to=to,
        sender="cuentas",
        subject="Tu cuenta de Seismik fue eliminada",
        idempotency_key=f"account-erased-{request_id}",
        text=(
            "Hola:\n\n"
            "Eliminamos tu cuenta de Seismik y los datos asociados: dispositivos, círculos familiares, "
            "claves de API y los reportes enviados desde tus dispositivos. Las sesiones abiertas dejaron de funcionar.\n\n"
            "Se conserva únicamente el libro contable de facturación, si existía, por obligación legal.\n\n"
            f"Referencia: {request_id}\n\n"
            "Si no fuiste tú quien lo pidió, escribe de inmediato a support@seismik.org con esa referencia."
        ),
    )


def deletion_request_received(to: str, *, request_id: str) -> Message:
    return Message(
        to=to,
        sender="cuentas",
        subject="Recibimos tu solicitud de eliminación",
        idempotency_key=f"deletion-received-{request_id}",
        text=(
            "Hola:\n\n"
            "Recibimos una solicitud para eliminar la cuenta de Seismik asociada a este correo. "
            "Una persona del equipo la revisará y verificará que viene de la titular antes de borrar nada; "
            "procuramos completarla en un máximo de 30 días calendario.\n\n"
            f"Referencia: {request_id}\n\n"
            "Si no hiciste esta solicitud, ignora este mensaje: no se borrará ningún dato sin verificarla. "
            "Si quieres eliminar tu cuenta al instante, inicia sesión en https://seismik.org/delete-account/ y confírmalo allí."
        ),
    )
