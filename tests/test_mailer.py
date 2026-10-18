"""Correo saliente: remitentes en español, apagado sin clave y sin datos de más."""

from __future__ import annotations

import json
import logging
import time

import httpx
import pytest
from fakeredis.aioredis import FakeRedis
from fastapi import FastAPI

from api import account_deletion
from api.account_erasure import router as erasure_router
from api.config import AppSettings
from api.mail_templates import account_erased, deletion_request_received
from api.mailer import RESEND_URL, Mailer, Message

KEY = "re_test_clave_de_prueba"


def settings(**extra: object) -> AppSettings:
    return AppSettings(resend_api_key=KEY, **extra)  # type: ignore[arg-type]


def recording(status: int = 200) -> tuple[httpx.AsyncClient, list[httpx.Request]]:
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(status, json={"id": "x", "message": "ana@example.test"})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler)), sent


@pytest.mark.asyncio
async def test_without_a_key_nothing_is_sent() -> None:
    client, sent = recording()
    mailer = Mailer(AppSettings(), client)
    assert mailer.enabled is False
    assert await mailer.send(Message(to="ana@example.test", subject="Hola", text="Hola")) is False
    assert sent == []


@pytest.mark.asyncio
async def test_accounts_mail_comes_from_cuentas_and_replies_go_to_support() -> None:
    client, sent = recording()
    ok = await Mailer(settings(), client).send(account_erased("ana@example.test", request_id="delreq_0123456789abcdef"))

    assert ok is True and len(sent) == 1
    request = sent[0]
    assert str(request.url) == RESEND_URL
    assert request.headers["authorization"] == f"Bearer {KEY}"
    assert request.headers["idempotency-key"] == "account-erased-delreq_0123456789abcdef"
    body = json.loads(request.content)
    assert body["from"] == "Seismik <cuentas@seismik.org>"
    assert body["reply_to"] == "support@seismik.org"
    assert body["to"] == ["ana@example.test"]
    assert body["subject"] == "Tu cuenta de Seismik fue eliminada"
    assert "delreq_0123456789abcdef" in body["text"] and "<p" in body["html"]
    assert "no representa a ninguna entidad pública" in body["text"], "el pie aclara que no somos una entidad oficial"


@pytest.mark.asyncio
async def test_automatic_notices_come_from_noreply_without_a_reply_to() -> None:
    client, sent = recording()
    await Mailer(settings(), client).send(Message(to="ana@example.test", subject="Aviso", text="Hola", sender="noreply"))

    body = json.loads(sent[0].content)
    assert body["from"] == "Seismik <noreply@seismik.org>"
    assert "reply_to" not in body


@pytest.mark.asyncio
async def test_the_html_escapes_what_it_is_given() -> None:
    client, sent = recording()
    await Mailer(settings(), client).send(Message(to="ana@example.test", subject="x", text="<script>alert(1)</script>\n\nsegunda"))

    html_body = json.loads(sent[0].content)["html"]
    assert "<script>" not in html_body and "&lt;script&gt;" in html_body


@pytest.mark.asyncio
async def test_a_failure_returns_false_and_never_logs_the_recipient(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING)
    client, _ = recording(status=422)
    assert await Mailer(settings(), client).send(Message(to="ana@example.test", subject="x", text="y")) is False

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin red", request=request)

    down = httpx.AsyncClient(transport=httpx.MockTransport(boom))
    assert await Mailer(settings(), down).send(Message(to="ana@example.test", subject="x", text="y")) is False
    assert "ana@example.test" not in caplog.text and KEY not in caplog.text


def test_every_email_template_is_in_spanish_and_names_a_reference() -> None:
    for message in (account_erased("a@example.test", request_id="delreq_1"), deletion_request_received("a@example.test", request_id="delreq_1")):
        assert message.sender == "cuentas" and message.subject and "delreq_1" in message.text
        assert message.text.startswith("Hola")
        assert "account" not in message.subject.lower() and "request" not in message.subject.lower()


def deletion_app(redis: FakeRedis, mailer_calls: list[Message], monkeypatch: pytest.MonkeyPatch, **extra: object) -> FastAPI:
    async def fake_send(self: Mailer, message: Message) -> bool:
        mailer_calls.append(message)
        return True

    monkeypatch.setattr(Mailer, "send", fake_send)
    app = FastAPI()
    app.state.redis = redis
    app.state.settings = AppSettings(**extra)  # type: ignore[arg-type]
    app.include_router(account_deletion.router)
    app.include_router(erasure_router)
    return app


@pytest.mark.asyncio
async def test_the_deletion_form_acknowledges_once_a_day_per_email(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Message] = []
    app = deletion_app(FakeRedis(decode_responses=True), calls, monkeypatch, resend_api_key=KEY)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test") as client:
        for email in ("ana@example.test", "ana@example.test", "luis@example.test"):
            assert (await client.post("/v1/account/deletion-requests", json={"email": email, "scope": "full"})).status_code == 201

    assert [m.to for m in calls] == ["ana@example.test", "luis@example.test"]
    assert all(m.subject == "Recibimos tu solicitud de eliminación" for m in calls)


@pytest.mark.asyncio
async def test_the_deletion_form_sends_nothing_without_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Message] = []
    app = deletion_app(FakeRedis(decode_responses=True), calls, monkeypatch)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test") as client:
        assert (await client.post("/v1/account/deletion-requests", json={"email": "ana@example.test", "scope": "full"})).status_code == 201
    assert calls == []


@pytest.mark.asyncio
async def test_a_completed_erasure_notifies_the_address_and_does_not_keep_it(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Message] = []
    redis = FakeRedis(decode_responses=True)
    app = deletion_app(redis, calls, monkeypatch, resend_api_key=KEY)
    token = "web-ana-" + "x" * 40
    await redis.set(
        f"seismik:oauth:session:{token}",
        json.dumps({"uid": "ana", "email": "ana@example.test", "name": "Ana", "authenticated_at": str(int(time.time()))}),
        ex=3600,
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test") as client:
        client.cookies.set("seismik_session", token)
        done = await client.post("/v1/account/erasure", json={"confirm": "ELIMINAR"}, headers={"Origin": "https://seismik.org"})

    assert done.status_code == 200
    assert [(m.to, m.subject) for m in calls] == [("ana@example.test", "Tu cuenta de Seismik fue eliminada")]
    assert calls[0].text.count(done.json()["request_id"]) >= 1
    stored = [value for key in await redis.keys("*") for value in [str(await redis.type(key))] if "ana@example.test" in key]
    assert stored == [], "el correo no queda en ninguna clave"
