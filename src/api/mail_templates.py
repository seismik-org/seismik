"""Textos de los correos de Seismik, todos en español."""

from __future__ import annotations

import html

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


# --- correos de acceso con diseño propio (mismos colores que seismik.org) --------------------------------------

_LOGO = "https://seismik.org/assets/icon-192.png"
_BG, _CARD, _LINE = "#060a13", "#0e1524", "#1c2740"
_TEXT, _MUTED, _PRIMARY, _INK = "#eef3ff", "#9dadc8", "#7cc4ff", "#04121f"


def _branded(heading: str, paragraphs: list[str], button: str, url: str, note: str) -> tuple[str, str]:
    """Texto plano y HTML con tablas y estilos en línea: es lo único que todos los clientes de correo respetan."""

    esc = html.escape
    body = "".join(f'<p style="margin:0 0 16px;font-size:16px;line-height:1.55;color:{_TEXT}">{esc(p)}</p>' for p in paragraphs)
    page = (
        f'<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<meta name="color-scheme" content="dark light"><title>{esc(heading)}</title></head>'
        f'<body style="margin:0;padding:0;background:{_BG}">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{_BG};padding:32px 12px">'
        f'<tr><td align="center"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="max-width:560px;background:{_CARD};border:1px solid {_LINE};border-radius:20px">'
        f'<tr><td style="padding:28px 32px 0">'
        f'<table role="presentation" cellpadding="0" cellspacing="0"><tr>'
        f'<td style="padding-right:12px"><img src="{_LOGO}" width="40" height="40" alt="" style="display:block;border-radius:10px;border:0"></td>'
        f'<td style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;font-size:18px;font-weight:800;'
        f'letter-spacing:2px;color:{_TEXT}">SEISMIK</td></tr></table></td></tr>'
        f'<tr><td style="padding:24px 32px 8px;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif">'
        f'<h1 style="margin:0 0 18px;font-size:26px;line-height:1.2;color:{_TEXT}">{esc(heading)}</h1>{body}'
        f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:26px 0 22px"><tr>'
        f'<td style="border-radius:999px;background:{_PRIMARY}"><a href="{esc(url, quote=True)}" '
        f'style="display:inline-block;padding:14px 28px;font-size:16px;font-weight:700;color:{_INK};text-decoration:none;'
        f'border-radius:999px">{esc(button)}</a></td></tr></table>'
        f'<p style="margin:0 0 6px;font-size:13px;line-height:1.5;color:{_MUTED}">Si el botón no funciona, copia este enlace en tu navegador:</p>'
        f'<p style="margin:0 0 22px;font-size:12px;line-height:1.5;word-break:break-all;color:{_PRIMARY}">{esc(url)}</p>'
        f'<p style="margin:0 0 8px;font-size:14px;line-height:1.55;color:{_MUTED}">{esc(note)}</p></td></tr>'
        f'<tr><td style="padding:18px 32px 28px;border-top:1px solid {_LINE};font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;'
        f'font-size:12px;line-height:1.6;color:{_MUTED}">Seismik es un proyecto independiente; no representa a ninguna entidad pública.<br>'
        f'<a href="https://seismik.org/terms-of-privacy/" style="color:{_MUTED}">Política de privacidad</a></td></tr>'
        f'</table></td></tr></table></body></html>'
    )
    text = "\n\n".join([heading, *paragraphs, f"{button}: {url}", note])
    return text, page


def password_reset(to: str, *, link: str) -> Message:
    text, page = _branded(
        "Elige una nueva contraseña",
        [f"Recibimos una solicitud para cambiar la contraseña de la cuenta de Seismik asociada a {to}."],
        "Cambiar contraseña",
        link,
        "El enlace funciona una sola vez y vence en 1 hora. Si no fuiste tú, ignora este mensaje: tu contraseña seguirá igual.",
    )
    return Message(to=to, sender="cuentas", subject="Cambia tu contraseña de Seismik", text=text, html=page)


def verify_email(to: str, *, link: str) -> Message:
    text, page = _branded(
        "Confirma tu correo",
        [f"Gracias por crear tu cuenta en Seismik. Confirma que {to} es tuyo para empezar a usarla."],
        "Confirmar mi correo",
        link,
        "El enlace caduca pasados unos días. Si no creaste esta cuenta, ignora este mensaje: no se activará nada.",
    )
    return Message(to=to, sender="cuentas", subject="Confirma tu correo en Seismik", text=text, html=page)
