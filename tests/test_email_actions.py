"""Correos de acceso propios: enlace directo a la página de Seismik, diseño en español y respaldo a Firebase."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from fakeredis.aioredis import FakeRedis
from fastapi import FastAPI
from firebase_admin import auth

from api import developer_keys
from api.config import AppSettings
from api.email_actions import action_link, router
from api.mail_templates import password_reset, verify_email
from api.mailer import Mailer, Message

ORIGIN = {"Origin": "https://auth.seismik.org"}
FIREBASE_LINK = "https://seismik-15bbb.firebaseapp.com/__/auth/action?mode=resetPassword&oobCode=CODE123&apiKey=KEY&lang=es"


class Harness:
    def __init__(self, monkeypatch: pytest.MonkeyPatch, *, key: str = "re_test_clave_de_prueba", known: bool = True) -> None:
        self.sent: list[Message] = []
        self.known = known
        self.identity: dict[str, Any] = {"uid": "fb-1", "email": "ana@example.test", "email_verified": False}
        harness = self

        async def fake_send(self_: Mailer, message: Message) -> bool:
            harness.sent.append(message)
            return True

        def reset_link(email: str, action_code_settings: Any = None, app: Any = None) -> str:
            if not harness.known:
                raise auth.UserNotFoundError("no existe")
            return FIREBASE_LINK

        def verify_link(email: str, action_code_settings: Any = None, app: Any = None) -> str:
            return FIREBASE_LINK.replace("resetPassword", "verifyEmail")

        def verify_token(token: str, app: Any = None, check_revoked: bool = False) -> dict[str, Any]:
            if token.startswith("bad"):
                raise ValueError("token inválido")
            return harness.identity

        monkeypatch.setattr(Mailer, "send", fake_send)
        monkeypatch.setattr(auth, "generate_password_reset_link", reset_link)
        monkeypatch.setattr(auth, "generate_email_verification_link", verify_link)
        monkeypatch.setattr(auth, "verify_id_token", verify_token)
        monkeypatch.setattr(developer_keys, "_firebase_app", lambda request: object())
        app = FastAPI()
        app.state.redis = FakeRedis(decode_responses=True)
        app.state.settings = AppSettings(resend_api_key=key)
        app.include_router(router)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test")


def test_the_link_goes_straight_to_the_seismik_page_with_the_action_code() -> None:
    link = action_link(FIREBASE_LINK, "resetPassword")
    assert link == "https://auth.seismik.org/id?mode=resetPassword&oobCode=CODE123&lang=es"
    with pytest.raises(ValueError):
        action_link("https://example.test/sin-codigo", "resetPassword")


@pytest.mark.asyncio
async def test_a_reset_request_sends_the_branded_spanish_email(monkeypatch: pytest.MonkeyPatch) -> None:
    h = Harness(monkeypatch)
    done = await h.client.post("/v1/oauth/email/reset-request", json={"email": " Ana@Example.test "}, headers=ORIGIN)

    assert done.status_code == 202 and done.json() == {"accepted": True}
    [message] = h.sent
    assert (message.to, message.sender, message.subject) == ("ana@example.test", "cuentas", "Cambia tu contraseña de Seismik")
    assert "https://auth.seismik.org/id?mode=resetPassword&oobCode=CODE123&lang=es" in message.text
    assert message.html and 'href="https://auth.seismik.org/id?mode=resetPassword&amp;oobCode=CODE123&amp;lang=es"' in message.html
    assert "firebaseapp.com" not in message.text and "firebaseapp.com" not in message.html, "el enlace no pasa por la página de Firebase"


@pytest.mark.asyncio
async def test_an_unknown_email_gets_the_same_answer_and_no_message(monkeypatch: pytest.MonkeyPatch) -> None:
    h = Harness(monkeypatch, known=False)
    done = await h.client.post("/v1/oauth/email/reset-request", json={"email": "nadie@example.test"}, headers=ORIGIN)

    assert done.status_code == 202 and done.json() == {"accepted": True}
    assert h.sent == []


@pytest.mark.asyncio
async def test_origin_validation_rate_limits_and_disabled_mail(monkeypatch: pytest.MonkeyPatch) -> None:
    h = Harness(monkeypatch)
    body = {"email": "ana@example.test"}
    for foreign in ({}, {"Origin": "https://evil.example"}, {"Origin": "https://seismik.org"}):
        assert (await h.client.post("/v1/oauth/email/reset-request", json=body, headers=foreign)).status_code == 403
    assert (await h.client.post("/v1/oauth/email/reset-request", json={"email": "sin-arroba"}, headers=ORIGIN)).status_code == 422
    # Tres correos por hora y dirección; el cuarto no sale, pero la respuesta es la misma.
    for _ in range(5):
        assert (await h.client.post("/v1/oauth/email/reset-request", json=body, headers=ORIGIN)).status_code == 202
    assert len(h.sent) == 3

    off = Harness(monkeypatch, key="")
    answer = await off.client.post("/v1/oauth/email/reset-request", json=body, headers=ORIGIN)
    assert answer.status_code == 503, "sin clave la página usa el correo de Firebase"


@pytest.mark.asyncio
async def test_verification_needs_a_valid_token_and_skips_verified_accounts(monkeypatch: pytest.MonkeyPatch) -> None:
    h = Harness(monkeypatch)
    assert (await h.client.post("/v1/oauth/email/verify-request", json={"id_token": "bad" + "x" * 30}, headers=ORIGIN)).status_code == 401

    done = await h.client.post("/v1/oauth/email/verify-request", json={"id_token": "t" * 40}, headers=ORIGIN)
    assert done.status_code == 202
    [message] = h.sent
    assert (message.to, message.subject) == ("ana@example.test", "Confirma tu correo en Seismik")
    assert "mode=verifyEmail" in message.text and "oobCode=CODE123" in message.text

    h.identity["email_verified"] = True
    again = await h.client.post("/v1/oauth/email/verify-request", json={"id_token": "t" * 40}, headers=ORIGIN)
    assert again.json() == {"accepted": True, "already_verified": True}
    assert len(h.sent) == 1


def test_templates_escape_what_they_are_given_and_are_in_spanish() -> None:
    message = password_reset("a<b>@example.test", link='https://auth.seismik.org/id?mode=resetPassword&oobCode="><script>')
    assert message.html and "<script>" not in message.html and "&lt;b&gt;" in message.html
    for built in (message, verify_email("ana@example.test", link="https://auth.seismik.org/id?mode=verifyEmail&oobCode=x")):
        assert built.sender == "cuentas" and built.html and built.text
        assert "Seismik" in built.subject and "ignora este mensaje" in built.text
        assert "https://seismik.org/assets/icon-192.png" in built.html
        assert "no representa a ninguna entidad pública" in built.html
