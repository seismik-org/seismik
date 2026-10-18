"""Centro de la cuenta: datos, accesos vinculados y borrado por categorías."""

from __future__ import annotations

import json
import time
from typing import Any

import httpx
import pytest
from fakeredis.aioredis import FakeRedis
from fastapi import FastAPI, Request

from api.account_center import (
    ACCOUNT_URL,
    collect_data,
    complete_link,
    firebase_binding_key,
    link_token_key,
    links_key,
    methods_for,
    provider_link_key,
    router,
)
from api.accounts import account_devices_key, device_account_key
from api.config import AppSettings
from api.oauth import _finish_login
from api.oauth import router as oauth_router

ORIGIN = {"Origin": "https://auth.seismik.org"}


def build(redis: FakeRedis, **extra: Any) -> FastAPI:
    app = FastAPI()
    app.state.redis = redis
    app.state.settings = AppSettings(**extra)
    app.include_router(router)
    app.include_router(oauth_router)
    return app


def client_for(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://auth.seismik.org")


async def session(redis: FakeRedis, uid: str, *, age: int = 5, **extra: str) -> str:
    token = f"web-{uid}-{age}-" + "x" * 40
    user = {"uid": uid, "email": f"{uid}@example.test", "name": uid.title(), "authenticated_at": str(int(time.time()) - age), **extra}
    await redis.set(f"seismik:oauth:session:{token}", json.dumps(user), ex=3600)
    return token


async def seed(redis: FakeRedis, uid: str) -> None:
    await redis.hset(f"seismik:device:{uid}-phone", mapping={
        "device_id": f"{uid}-phone", "platform": "android", "token": "SECRETTOKEN", "zone_id": "co", "latitude": "4.6", "longitude": "-74.0",
        "receive_early_alerts": "1", "alert_radius_km": "100", "updated_at": "2026-10-18T12:00:00+00:00", "integrity_verified": "1",
    })
    await redis.sadd(account_devices_key(uid), f"{uid}-phone")
    await redis.set(device_account_key(f"{uid}-phone"), uid)
    await redis.hset(f"seismik:developer-key:digest-{uid}", mapping={"key_id": f"k-{uid}", "name": "Mi clave", "prefix": "sk_live_ab…", "plan": "free", "status": "active", "uid": uid})
    await redis.set(f"seismik:developer-key-id:k-{uid}", f"digest-{uid}")
    await redis.sadd(f"seismik:developer-keys:{uid}", f"k-{uid}")
    await redis.hset(f"seismik:webhook:wh-{uid}", mapping={"uid": uid, "url": "https://example.test/hook", "status": "active", "secret_digest": "ABC"})
    await redis.sadd(f"seismik:webhooks:{uid}", f"wh-{uid}")
    await redis.sadd("seismik:webhooks:active", f"wh-{uid}")
    await redis.xadd("stream:seismik:felt-reports", {"payload": json.dumps({"device_id": f"{uid}-phone", "report_id": f"r-{uid}", "intensity": 4}), "event_id": "e", "event_type": "felt"})
    circle = f"circle-{uid}"
    await redis.set(f"seismik:family:account:{uid}", circle)
    await redis.hset(f"seismik:family:circle:{circle}", mapping={"circle_name": "Casa", "owner_uid": uid})
    await redis.sadd(f"seismik:family:members:{circle}", uid)
    await redis.hset(f"seismik:family:member:{circle}:{uid}", mapping={"display_name": "Ana", "joined_at": "2026-10-01T00:00:00+00:00"})


@pytest.mark.asyncio
async def test_the_center_needs_a_session_and_lists_methods_and_counts() -> None:
    redis = FakeRedis(decode_responses=True)
    await seed(redis, "1001")
    await redis.hset(links_key("1001"), "github", json.dumps({"puid": "github:5", "added_at": "2026-10-10T00:00:00+00:00"}))
    async with client_for(build(redis)) as client:
        assert (await client.get("/v1/oauth/account/center")).status_code == 401
        client.cookies.set("seismik_session", await session(redis, "1001"))
        body = (await client.get("/v1/oauth/account/center")).json()

    assert body["email"] == "1001@example.test" and body["recent_login"] is True and len(body["account_id"]) == 12
    methods = {m["id"]: m for m in body["methods"]}
    assert methods["google"]["primary"] and methods["google"]["linked"] and not methods["google"]["removable"]
    assert methods["github"]["linked"] and methods["github"]["removable"] and not methods["github"]["primary"]
    assert not methods["email"]["linked"] and methods["email"]["linkable"] and not methods["apple"]["linkable"]
    assert body["data"] == {"devices": 1, "family_circle": True, "api_keys": 1, "webhooks": 1, "reports": 1, "billing": False}


@pytest.mark.asyncio
async def test_the_export_shows_what_is_stored_without_secrets_or_other_accounts() -> None:
    redis = FakeRedis(decode_responses=True)
    await seed(redis, "1001")
    await seed(redis, "2002")
    async with client_for(build(redis)) as client:
        client.cookies.set("seismik_session", await session(redis, "1001"))
        response = await client.get("/v1/oauth/account/data", params={"download": "true"})

    assert response.status_code == 200 and "attachment" in response.headers["content-disposition"]
    text = response.text
    data = response.json()
    assert "SECRETTOKEN" not in text and "ABC" not in text, "ni el token de notificaciones ni el secreto del webhook"
    assert "2002" not in text, "nada de otra cuenta"
    [device] = data["dispositivos"]
    assert device["id"] == "1001-phone" and device["token_de_notificaciones_guardado"] is True
    assert device["ubicacion_guardada"] == {"latitud": "4.6", "longitud": "-74.0"}
    assert data["familia"]["rol"] == "dueño" and data["familia"]["alias"] == "Ana"
    assert data["desarrollador"]["claves_de_api"][0]["name"] == "Mi clave"
    assert data["desarrollador"]["webhooks"][0]["url"] == "https://example.test/hook"
    assert [r["report_id"] for r in data["reportes"]] == ["r-1001"] and "device_id" not in data["reportes"][0]
    assert data["no_guardamos"] and data["cuenta"]["identificador"] != "1001"


@pytest.mark.asyncio
async def test_deleting_a_category_removes_only_that_category_and_needs_a_recent_login_and_origin() -> None:
    redis = FakeRedis(decode_responses=True)
    await seed(redis, "1001")
    async with client_for(build(redis)) as client:
        client.cookies.set("seismik_session", await session(redis, "1001"))
        assert (await client.delete("/v1/oauth/account/data/devices")).status_code == 403
        assert (await client.delete("/v1/oauth/account/data/todo", headers=ORIGIN)).status_code == 422

        client.cookies.set("seismik_session", await session(redis, "1001", age=3_000))
        assert (await client.delete("/v1/oauth/account/data/devices", headers=ORIGIN)).json()["detail"] == "reauth_required"
        assert await redis.exists("seismik:device:1001-phone")

        client.cookies.set("seismik_session", await session(redis, "1001"))
        assert (await client.delete("/v1/oauth/account/data/reports", headers=ORIGIN)).json() == {"category": "reports", "reports": 1}
        assert not await redis.xrange("stream:seismik:felt-reports") and await redis.exists("seismik:device:1001-phone")
        assert (await client.delete("/v1/oauth/account/data/developer", headers=ORIGIN)).json()["api_keys"] == 1
        assert not await redis.exists("seismik:developer-keys:1001", "seismik:webhooks:1001") and await redis.exists("seismik:family:account:1001")
        assert (await client.delete("/v1/oauth/account/data/family", headers=ORIGIN)).json()["family_circle"] is True
        assert not await redis.exists("seismik:family:account:1001") and await redis.exists("seismik:device:1001-phone")
        assert (await client.delete("/v1/oauth/account/data/devices", headers=ORIGIN)).json()["devices"] == 1
        assert not await redis.exists("seismik:device:1001-phone", account_devices_key("1001"))


def request_with(app: FastAPI, cookies: dict[str, str]) -> Request:
    header = "; ".join(f"{k}={v}" for k, v in cookies.items()).encode()
    return Request({"type": "http", "app": app, "headers": [(b"cookie", header)] if header else [], "method": "GET", "path": "/", "query_string": b""})


async def start_link_token(redis: FakeRedis, uid: str, provider: str) -> str:
    token = "link-token-" + "z" * 30
    await redis.set(link_token_key(token), json.dumps({"uid": uid, "provider": provider}), ex=600)
    return token


@pytest.mark.asyncio
async def test_starting_a_link_sets_a_browser_bound_cookie_and_goes_to_the_provider_start() -> None:
    redis = FakeRedis(decode_responses=True)
    async with client_for(build(redis)) as client:
        client.cookies.set("seismik_session", await session(redis, "1001"))
        start = await client.get("/v1/oauth/account/methods/link/github")
        assert start.status_code == 303 and start.headers["location"].startswith("/v1/oauth/github/start?link=")
        token = start.headers["location"].split("link=")[1]
        assert f"seismik_link={token}" in start.headers["set-cookie"] and "HttpOnly" in start.headers["set-cookie"]
        assert await redis.exists(link_token_key(token))

        old = await session(redis, "1001", age=3_000)
        client.cookies.set("seismik_session", old)
        assert (await client.get("/v1/oauth/account/methods/link/github")).headers["location"] == f"{ACCOUNT_URL}?link=reauth"

        client.cookies.set("seismik_session", await session(redis, "1001"))
        email = await client.get("/v1/oauth/account/methods/link/email")
        assert email.headers["location"] == "https://auth.seismik.org/id?link=1" and "seismik_after_login=account" in email.headers["set-cookie"]
        assert (await client.get("/v1/oauth/account/methods/link/apple")).status_code == 422


@pytest.mark.asyncio
async def test_the_oauth_start_only_accepts_a_link_token_bound_to_the_same_browser() -> None:
    redis = FakeRedis(decode_responses=True)
    app = build(redis, oauth_github_client_id="client", oauth_github_client_secret="secret", oauth_github_redirect_uri="https://auth.seismik.org/v1/oauth/github/callback")
    token = await start_link_token(redis, "1001", "github")
    async with client_for(app) as client:
        assert (await client.get("/v1/oauth/github/start", params={"link": token})).status_code == 400, "sin la cookie del navegador"
        client.cookies.set("seismik_link", "otro-token")
        assert (await client.get("/v1/oauth/github/start", params={"link": token})).status_code == 400
        client.cookies.set("seismik_link", token, domain="auth.seismik.org")
        good = await client.get("/v1/oauth/github/start", params={"link": token})
        assert good.status_code == 307 and good.headers["location"].startswith("https://github.com/login/oauth/authorize")
        plain = await client.get("/v1/oauth/github/start")
        assert plain.status_code == 307, "el inicio de sesión normal no cambia"
    saved = [json.loads(await redis.get(k)) for k in await redis.keys("seismik:oauth:state:*")]
    assert sum(1 for item in saved if item.get("link_token") == token) == 1


@pytest.mark.asyncio
async def test_completing_a_link_binds_the_new_identity_to_the_account_and_logins_land_in_it() -> None:
    redis = FakeRedis(decode_responses=True)
    app = build(redis)
    web = await session(redis, "1001")
    token = await start_link_token(redis, "1001", "github")
    done = await complete_link(request_with(app, {"seismik_link": token, "seismik_session": web}), "github", {"uid": "github:77", "email": "g@example.test"}, token)

    assert done.headers["location"] == f"{ACCOUNT_URL}?link=ok"
    assert await redis.get(provider_link_key("github:77")) == "1001"
    assert {m["id"]: m["linked"] for m in await methods_for(redis, "1001")}["github"] is True
    assert not await redis.exists(link_token_key(token)), "el token sirve una sola vez"

    # Ahora entrar con ese GitHub lleva a la cuenta de Google original.
    login = await _finish_login(request_with(app, {}), {"uid": "github:77", "email": "g@example.test", "name": "G"}, None)
    cookie = next(c for c in login.headers.getlist("set-cookie") if c.startswith("seismik_session="))
    stored = json.loads(await redis.get("seismik:oauth:session:" + cookie.split(";")[0].split("=", 1)[1]))
    assert stored["uid"] == "1001"
    # Y una identidad que no está enlazada sigue entrando como siempre.
    plain = await _finish_login(request_with(app, {}), {"uid": "github:88", "email": "x@example.test", "name": "X"}, None)
    other = next(c for c in plain.headers.getlist("set-cookie") if c.startswith("seismik_session="))
    assert json.loads(await redis.get("seismik:oauth:session:" + other.split(";")[0].split("=", 1)[1]))["uid"] == "github:88"


@pytest.mark.asyncio
async def test_a_link_is_refused_when_it_could_merge_accounts_or_was_not_started_by_this_browser() -> None:
    redis = FakeRedis(decode_responses=True)
    app = build(redis)
    web = await session(redis, "1001")

    async def attempt(identity: dict[str, str], *, cookies: dict[str, str] | None = None, record_uid: str = "1001", provider: str = "github", record_provider: str | None = None) -> str:
        token = "tok-" + str(time.time_ns())
        await redis.set(link_token_key(token), json.dumps({"uid": record_uid, "provider": record_provider or provider}), ex=600)
        jar = cookies if cookies is not None else {"seismik_link": token, "seismik_session": web}
        jar = {k: (token if k == "seismik_link" else v) for k, v in jar.items()}
        answer = await complete_link(request_with(app, jar), provider, identity, token)
        return answer.headers["location"].rsplit("link=", 1)[1]

    # La identidad nueva ya tiene sus propios datos: no se fusiona.
    await redis.sadd("seismik:account:devices:github:9", "d")
    assert await attempt({"uid": "github:9", "email": "x"}) == "conflict"
    assert not await redis.exists(provider_link_key("github:9"))
    # Vinculada a otra cuenta.
    await redis.set(provider_link_key("github:10"), "3003")
    assert await attempt({"uid": "github:10", "email": "x"}) == "conflict"
    # Otra persona termina el flujo en SU navegador: sin la cookie del enlace no pasa.
    assert await attempt({"uid": "github:11", "email": "x"}, cookies={"seismik_session": web}) == "expired"
    # La sesión de ese navegador es de otra cuenta.
    assert await attempt({"uid": "github:12", "email": "x"}, record_uid="3003") == "expired"
    # El proveedor del flujo no coincide con el del enlace.
    assert await attempt({"uid": "github:13", "email": "x"}, record_provider="google") == "expired"
    assert not await redis.exists(provider_link_key("github:11"), provider_link_key("github:12"), provider_link_key("github:13"))
    # La misma identidad principal, o un segundo GitHub, no hacen nada nuevo.
    assert await attempt({"uid": "1001", "email": "x"}, provider="google") == "already"
    assert await attempt({"uid": "github:14", "email": "x"}) == "ok"
    assert await attempt({"uid": "github:15", "email": "x"}) == "duplicate", "un solo GitHub por cuenta"
    stale = await session(redis, "1001", age=5_000)
    assert await attempt({"uid": "github:16", "email": "x"}, cookies={"seismik_link": "t", "seismik_session": stale}) == "expired"


@pytest.mark.asyncio
async def test_unlinking_frees_the_identity_and_never_removes_the_last_access() -> None:
    redis = FakeRedis(decode_responses=True)
    app = build(redis)
    await redis.set(provider_link_key("github:77"), "1001")
    await redis.hset(links_key("1001"), "github", json.dumps({"puid": "github:77", "added_at": "x"}))
    await redis.set(firebase_binding_key("fb-1"), "1001")
    await redis.hset(links_key("1001"), "email", json.dumps({"puid": "fb-1", "added_at": "x"}))
    async with client_for(app) as client:
        client.cookies.set("seismik_session", await session(redis, "1001"))
        assert (await client.post("/v1/oauth/account/methods/unlink", json={"method": "github"})).status_code == 403
        done = await client.post("/v1/oauth/account/methods/unlink", json={"method": "github"}, headers=ORIGIN)
        assert done.status_code == 200 and not await redis.exists(provider_link_key("github:77"))
        assert {m["id"]: m["linked"] for m in done.json()["methods"]}["github"] is False
        assert (await client.post("/v1/oauth/account/methods/unlink", json={"method": "google"}, headers=ORIGIN)).status_code == 409
        assert (await client.post("/v1/oauth/account/methods/unlink", json={"method": "github"}, headers=ORIGIN)).status_code == 409
        assert (await client.post("/v1/oauth/account/methods/unlink", json={"method": "apple"}, headers=ORIGIN)).status_code == 422
        await client.post("/v1/oauth/account/methods/unlink", json={"method": "email"}, headers=ORIGIN)
        assert not await redis.exists(firebase_binding_key("fb-1"))


@pytest.mark.asyncio
async def test_the_account_marker_returns_to_the_center_and_nothing_else_is_followed() -> None:
    redis = FakeRedis(decode_responses=True)
    app = build(redis)
    user = {"uid": "1001", "email": "a@example.test", "name": "A"}
    back = await _finish_login(request_with(app, {"seismik_after_login": "account"}), user, None)
    assert back.headers["location"] == ACCOUNT_URL
    assert any(c.startswith("seismik_after_login=") and "Max-Age=0" in c for c in back.headers.getlist("set-cookie"))
    for value in ("account:https://evil.example", "ACCOUNT", "https://evil.example"):
        other = await _finish_login(request_with(app, {"seismik_after_login": value}), user, None)
        assert other.headers["location"] == "https://devs.seismik.org/", value
    mobile = await _finish_login(request_with(app, {"seismik_after_login": "account"}), user, "seismik://auth/callback")
    assert mobile.headers["location"].startswith("seismik://auth/callback?code=")
    async with client_for(app) as client:
        start = await client.get("/v1/oauth/account/login")
    assert start.headers["location"] == "https://auth.seismik.org/id" and "seismik_after_login=account" in start.headers["set-cookie"]


@pytest.mark.asyncio
async def test_an_email_primary_account_is_recognized_and_the_erasure_routes_work_from_the_auth_domain() -> None:
    redis = FakeRedis(decode_responses=True)
    await redis.set(firebase_binding_key("fbuid"), "fbuid")
    assert {m["id"]: m["primary"] for m in await methods_for(redis, "fbuid")}["email"] is True
    assert {m["id"]: m["primary"] for m in await methods_for(redis, "github:1")}["github"] is True
    assert {m["id"]: m["primary"] for m in await methods_for(redis, "apple:1")}["apple"] is True

    await seed(redis, "1001")
    async with client_for(build(redis)) as client:
        client.cookies.set("seismik_session", await session(redis, "1001"))
        summary = await client.get("/v1/oauth/account/erasure")
        assert summary.status_code == 200 and summary.json()["devices"] == 1
        done = await client.post("/v1/oauth/account/erasure", json={"confirm": "ELIMINAR"}, headers=ORIGIN)
        assert done.status_code == 200 and done.json()["erased"] is True
    assert not await redis.exists("seismik:device:1001-phone")
    assert collect_data is not None
