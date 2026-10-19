"""Vincular accesos: cada error dice qué pasó y qué hacer, y la vinculación continúa sola tras volver a entrar."""

from __future__ import annotations

import json
import time
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fakeredis.aioredis import FakeRedis
from fastapi import FastAPI, Request

from api import firebase_login
from api.account_center import ACCOUNT_URL, firebase_binding_key, links_key
from api.account_center import router as center_router
from api.config import AppSettings
from api.oauth import _finish_login, identity_router, router


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    app = FastAPI()
    app.state.settings = AppSettings(email_login_enabled=True)
    app.state.redis = FakeRedis(decode_responses=True)
    app.state.claims = {
        "uid": "firebase-person", "email": "same@example.org", "email_verified": True,
        "auth_time": int(time.time()), "firebase": {"sign_in_provider": "password"},
    }
    app.state.user = SimpleNamespace(disabled=False, email_verified=True, tokens_valid_after_timestamp=0)
    monkeypatch.setattr(firebase_login, "_firebase_app", lambda _: None)
    monkeypatch.setattr(firebase_login.auth, "verify_id_token", lambda token, **kwargs: app.state.claims.copy())
    monkeypatch.setattr(firebase_login.auth, "get_user", lambda *a, **k: app.state.user)
    app.include_router(router)
    app.include_router(identity_router)
    app.include_router(firebase_login.router)
    app.include_router(center_router)
    return app


def client_for(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://auth.seismik.org", headers={"Origin": "https://auth.seismik.org"})


async def exchange(client: httpx.AsyncClient, **kwargs: Any) -> httpx.Response:
    return await client.post("/v1/oauth/email/exchange", json={"id_token": "verified-token" * 3, **kwargs})


async def session(app: FastAPI, client: httpx.AsyncClient, uid: str = "github:123", age: int = 0, **extra: Any) -> None:
    user = {"uid": uid, "email": "same@example.org", "name": "Existing", "authenticated_at": str(int(time.time()) - age), **extra}
    await app.state.redis.set("seismik:oauth:session:legacy", json.dumps(user), ex=3600)
    client.cookies.set("seismik_session", "legacy", domain=".seismik.org")


def detail_of(result: httpx.Response) -> dict[str, str]:
    detail = result.json()["detail"]
    assert isinstance(detail, dict) and detail["message"] and detail["code"]
    return detail


def request_with(app: FastAPI, cookies: dict[str, str]) -> Request:
    header = "; ".join(f"{k}={v}" for k, v in cookies.items()).encode()
    return Request({"type": "http", "app": app, "headers": [(b"cookie", header)] if header else [], "method": "GET", "path": "/", "query_string": b""})


@pytest.mark.asyncio
async def test_link_errors_say_what_happened_and_what_to_do(app: FastAPI) -> None:
    async with client_for(app) as client:
        none = await exchange(client, link=True)
        assert none.status_code == 401 and detail_of(none)["code"] == "link_no_session"
        assert "Mi cuenta" in detail_of(none)["message"]

        await session(app, client, age=5_000)
        old = await exchange(client, link=True)
        assert old.status_code == 401 and detail_of(old)["code"] == "link_reauth"
        assert "10 minutos" in detail_of(old)["message"] and "continuará solo" in detail_of(old)["message"]

        await session(app, client)
        await app.state.redis.set(firebase_login.binding_key("firebase-person"), "other-account")
        taken = await exchange(client, link=True)
        assert taken.status_code == 409 and detail_of(taken)["code"] == "link_taken"


@pytest.mark.asyncio
async def test_a_session_that_already_uses_an_email_is_told_so_instead_of_asking_for_google(app: FastAPI) -> None:
    async with client_for(app) as client:
        await session(app, client, firebase_uid="firebase-person")
        same = await exchange(client, link=True)
        assert same.status_code == 409 and detail_of(same)["code"] == "link_same"
        assert "Ya entraste con este correo" in detail_of(same)["message"]

        await session(app, client, firebase_uid="otro-correo")
        other = await exchange(client, link=True)
        assert other.status_code == 409 and detail_of(other)["code"] == "link_has_email"

    await app.state.redis.sadd("seismik:developer-keys:firebase-person", "k")
    async with client_for(app) as client:
        await session(app, client)
        conflict = await exchange(client, link=True)
        assert conflict.status_code == 409 and detail_of(conflict)["code"] == "link_conflict"
        assert "No fusionamos cuentas" in detail_of(conflict)["message"]


@pytest.mark.asyncio
async def test_a_successful_email_link_is_recorded_in_the_accounts_list(app: FastAPI) -> None:
    async with client_for(app) as client:
        await session(app, client)
        assert (await exchange(client, link=True)).status_code == 200
    saved = json.loads(await app.state.redis.hget(links_key("github:123"), "email"))
    assert saved["puid"] == "firebase-person"


@pytest.mark.asyncio
async def test_after_re_login_the_pending_link_continues_by_itself(app: FastAPI) -> None:
    user = {"uid": "1001", "email": "a@example.test", "name": "A"}
    for method in ("google", "github", "email"):
        back = await _finish_login(request_with(app, {"seismik_after_login": f"account-link-{method}"}), user, None)
        assert back.headers["location"] == f"https://auth.seismik.org/v1/oauth/account/methods/link/{method}"
        assert any(c.startswith("seismik_after_login=") and "Max-Age=0" in c for c in back.headers.getlist("set-cookie"))
    for value in ("account-link-apple", "account-link-", "account-link-google:https://evil.example", "account-link-../x"):
        other = await _finish_login(request_with(app, {"seismik_after_login": value}), user, None)
        assert other.headers["location"] == "https://devs.seismik.org/", value
    async with client_for(app) as client:
        start = await client.get("/v1/oauth/account/login", params={"next": "link-github"})
        assert start.status_code == 303 and "seismik_after_login=account-link-github" in start.headers["set-cookie"]
        assert (await client.get("/v1/oauth/account/login", params={"next": "link-apple"})).status_code == 422
        plain = await client.get("/v1/oauth/account/login")
        assert plain.headers["set-cookie"].startswith("seismik_after_login=account;")


@pytest.mark.asyncio
async def test_a_stale_session_goes_back_to_sign_in_and_a_missing_one_gets_a_notice(app: FastAPI) -> None:
    async with client_for(app) as client:
        none = await client.get("/v1/oauth/account/methods/link/google")
        assert none.status_code == 303 and none.headers["location"] == f"{ACCOUNT_URL}?link=login"
        await session(app, client, uid="1001", age=5_000)
        stale = await client.get("/v1/oauth/account/methods/link/email")
        assert stale.headers["location"] == "/v1/oauth/account/login?next=link-email"


@pytest.mark.asyncio
async def test_the_session_remembers_which_method_was_used_and_the_center_shows_it(app: FastAPI) -> None:
    redis = app.state.redis

    async def method_of(user: dict[str, str]) -> str:
        done = await _finish_login(request_with(app, {}), user, None)
        cookie = next(c for c in done.headers.getlist("set-cookie") if c.startswith("seismik_session="))
        return str(json.loads(await redis.get("seismik:oauth:session:" + cookie.split(";")[0].split("=", 1)[1]))["login_method"])

    assert await method_of({"uid": "1001", "email": "a", "name": "A"}) == "google"
    assert await method_of({"uid": "github:5", "email": "a", "name": "A"}) == "github"
    assert await method_of({"uid": "apple:5", "email": "a", "name": "A"}) == "apple"
    assert await method_of({"uid": "1001", "email": "a", "name": "A", "firebase_uid": "fb"}) == "email"

    async with client_for(app) as client:
        await session(app, client, uid="1001", login_method="github")
        assert (await client.get("/v1/oauth/account/center")).json()["current_method"] == "github"


@pytest.mark.asyncio
async def test_an_email_linked_before_the_list_existed_shows_up_once_the_person_uses_it(app: FastAPI) -> None:
    redis = app.state.redis
    await redis.set(firebase_binding_key("fb-old"), "1001")  # vínculo antiguo, sin registro en la lista
    async with client_for(app) as client:
        await session(app, client, uid="1001")
        before = {m["id"]: m for m in (await client.get("/v1/oauth/account/center")).json()["methods"]}
        assert before["email"]["linked"] is False

        await session(app, client, uid="1001", firebase_uid="fb-old", login_method="email")
        after = {m["id"]: m for m in (await client.get("/v1/oauth/account/center")).json()["methods"]}
        assert after["email"]["linked"] is True and after["email"]["removable"] is True

        # Una sesión cuyo correo NO está vinculado a esta cuenta no lo inventa.
        await redis.delete(links_key("1001"), firebase_binding_key("fb-old"))
        await session(app, client, uid="1001", firebase_uid="fb-ajeno")
        assert {m["id"]: m for m in (await client.get("/v1/oauth/account/center")).json()["methods"]}["email"]["linked"] is False
