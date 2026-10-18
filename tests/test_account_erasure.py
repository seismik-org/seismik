"""Eliminación de cuenta por su dueño: qué borra, qué conserva y quién puede pedirla."""

from __future__ import annotations

import json
import time
from typing import Any

import httpx
import pytest
from fakeredis.aioredis import FakeRedis
from fastapi import FastAPI, Request

from api import account_erasure
from api.account_erasure import erase_account, erased_marker_key, router, session_was_erased
from api.accounts import account_devices_key, device_account_key
from api.config import AppSettings
from api.device_sessions import DeviceSessionRepository
from api.family import account_router
from api.family import router as family_router
from api.oauth import _finish_login

ORIGIN = {"Origin": "https://seismik.org"}


def build(redis: FakeRedis) -> FastAPI:
    app = FastAPI()
    app.state.redis = redis
    app.state.settings = AppSettings()
    for item in (router, family_router, account_router):
        app.include_router(item)
    return app


def client_for(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://test")


async def web_session(redis: FakeRedis, uid: str, *, age: int = 5, **extra: str) -> str:
    token = f"web-{uid}-" + "x" * 40
    user = {"uid": uid, "email": f"{uid}@example.test", "name": uid.title(),
            "authenticated_at": str(int(time.time()) - age), **extra}
    await redis.set(f"seismik:oauth:session:{token}", json.dumps(user), ex=3600)
    return token


async def mobile_session(redis: FakeRedis, uid: str, *, authenticated_at: int) -> dict[str, str]:
    token = f"mobile-{uid}-{authenticated_at}-" + "y" * 40
    await redis.set(
        f"seismik:oauth:mobile-session:{token}",
        json.dumps({"uid": uid, "email": f"{uid}@example.test", "name": uid, "authenticated_at": str(authenticated_at)}),
        ex=3600,
    )
    return {"X-Seismik-Account-Session": token}


async def seed_device(redis: FakeRedis, uid: str, device_id: str) -> None:
    await redis.hset(f"seismik:device:{device_id}", mapping={
        "device_id": device_id, "platform": "android", "token": f"token-{device_id}",
        "zone_id": "co-bogota", "latitude": "4.6", "longitude": "-74.0",
    })
    await redis.set(f"seismik:device-token:android:{__import__('hashlib').sha256(f'token-{device_id}'.encode()).hexdigest()}", device_id)
    await redis.sadd("seismik:devices:zone:co-bogota", device_id)
    await redis.geoadd("seismik:devices:geo", [-74.0, 4.6, device_id])
    await redis.sadd(account_devices_key(uid), device_id)
    await redis.set(device_account_key(device_id), uid)


async def seed_developer(redis: FakeRedis, uid: str, key_id: str) -> None:
    digest = f"digest-{key_id}"
    await redis.hset(f"seismik:developer-key:{digest}", mapping={"uid": uid, "key_id": key_id, "status": "active"})
    await redis.set(f"seismik:developer-key-id:{key_id}", digest)
    await redis.sadd(f"seismik:developer-keys:{uid}", key_id)
    await redis.hset(f"seismik:developer-profile:{uid}", mapping={"terms_version": "1"})
    await redis.set(f"seismik:developer-usage:day:{digest}:20261018", "7")
    await redis.set(f"seismik:developer-key-creations:{uid}:20261018", "1")
    webhook = f"wh-{key_id}"
    await redis.hset(f"seismik:webhook:{webhook}", mapping={"uid": uid, "url": "https://example.test/hook"})
    await redis.sadd(f"seismik:webhooks:{uid}", webhook)
    await redis.sadd("seismik:webhooks:active", webhook)


async def report(redis: FakeRedis, stream: str, device_id: str, report_id: str) -> None:
    await redis.xadd(stream, {"payload": json.dumps({"device_id": device_id, "report_id": report_id}),
                              "event_id": report_id, "event_type": "felt"})


def keys_mentioning(keys: list[str], *needles: str) -> list[str]:
    return sorted(key for key in keys if any(needle in key for needle in needles))


@pytest.mark.asyncio
async def test_erasure_needs_a_session_the_confirmation_word_a_recent_login_and_the_site_origin() -> None:
    redis = FakeRedis(decode_responses=True)
    async with client_for(build(redis)) as client:
        assert (await client.post("/v1/account/erasure", json={"confirm": "ELIMINAR"}, headers=ORIGIN)).status_code == 401

        fresh = await web_session(redis, "ana")
        client.cookies.set("seismik_session", fresh)
        assert (await client.post("/v1/account/erasure", json={"confirm": "si"}, headers=ORIGIN)).status_code == 422
        assert (await client.post("/v1/account/erasure", json={}, headers=ORIGIN)).status_code == 422
        for foreign in ({}, {"Origin": "https://evil.example"}, {"Origin": "https://devs.seismik.org"}):
            assert (await client.post("/v1/account/erasure", json={"confirm": "ELIMINAR"}, headers=foreign)).status_code == 403

        old = await web_session(redis, "luis", age=3_000)
        client.cookies.set("seismik_session", old)
        stale = await client.post("/v1/account/erasure", json={"confirm": "ELIMINAR"}, headers=ORIGIN)
        assert stale.status_code == 401 and stale.json()["detail"] == "reauth_required"
        assert await redis.get(erased_marker_key("luis")) is None, "sin inicio de sesión reciente no se borra nada"
        assert await redis.get(erased_marker_key("ana")) is None


@pytest.mark.asyncio
async def test_summary_shows_what_will_be_erased_without_exposing_the_email() -> None:
    redis = FakeRedis(decode_responses=True)
    await seed_device(redis, "ana", "phone-1")
    await seed_developer(redis, "ana", "key-1")
    async with client_for(build(redis)) as client:
        client.cookies.set("seismik_session", await web_session(redis, "ana"))
        summary = (await client.get("/v1/account/erasure")).json()

    assert summary["email"] == "a•••@example.test"
    assert summary["recent_login"] is True
    assert (summary["devices"], summary["api_keys"], summary["in_family_circle"]) == (1, 1, False)
    assert summary["erased"] and summary["retained"]


@pytest.mark.asyncio
async def test_erasure_removes_everything_the_account_owns_and_nothing_else() -> None:
    redis = FakeRedis(decode_responses=True)
    settings = AppSettings()
    sessions = DeviceSessionRepository(redis, ttl_seconds=3600)
    for device in ("ana-phone", "ana-watch"):
        await seed_device(redis, "ana", device)
    tokens = [await sessions.issue(device) for device in ("ana-phone", "ana-watch")]
    luis_token = await sessions.issue("luis-phone")
    await seed_device(redis, "luis", "luis-phone")
    await seed_developer(redis, "ana", "ana-key")
    await seed_developer(redis, "luis", "luis-key")
    await redis.set("seismik:billing:ledger:ana", "[]")
    for device, rid in (("ana-phone", "r1"), ("ana-watch", "r2"), ("luis-phone", "r3"), ("ana-phone", "r4")):
        await report(redis, settings.felt_reports_stream, device, rid)
    await report(redis, settings.damage_reports_stream, "ana-phone", "r5")
    await report(redis, settings.damage_reports_stream, "luis-phone", "r6")
    before_luis = {key for key in await redis.keys("*") if "luis" in key}

    async with client_for(build(redis)) as client:
        client.cookies.set("seismik_session", await web_session(redis, "ana"))
        done = await client.post("/v1/account/erasure", json={"confirm": "ELIMINAR"}, headers=ORIGIN)

    assert done.status_code == 200, done.text
    body = done.json()
    assert (body["devices"], body["api_keys"], body["webhooks"], body["reports"]) == (2, 1, 1, 4)
    assert body["billing_retained"] is True and body["pending"] == []
    assert [await sessions.resolve(token) for token in tokens] == [None, None], "las sesiones de sus teléfonos se revocan"
    assert await sessions.resolve(luis_token) == "luis-phone"
    remaining = await redis.keys("*")
    assert keys_mentioning(remaining, "ana-phone", "ana-watch", "ana-key", "wh-ana-key", "digest-ana-key") == []
    assert not await redis.exists(account_devices_key("ana"), "seismik:developer-keys:ana", "seismik:developer-profile:ana",
                                  "seismik:webhooks:ana", "seismik:developer-key-creations:ana:20261018")
    assert await redis.zscore("seismik:devices:geo", "ana-phone") is None
    assert "ana-phone" not in await redis.smembers("seismik:devices:zone:co-bogota")
    assert "wh-ana-key" not in await redis.smembers("seismik:webhooks:active")
    assert await redis.exists("seismik:billing:ledger:ana"), "los registros contables se conservan"
    survivors = [json.loads(e[1]["payload"])["report_id"] for s in (settings.felt_reports_stream, settings.damage_reports_stream)
                 for e in await redis.xrange(s)]
    assert sorted(survivors) == ["r3", "r6"], "sólo quedan los reportes de otra persona"
    assert {key for key in await redis.keys("*") if "luis" in key} == before_luis, "los datos de otra cuenta no se tocan"
    assert not await redis.exists(f"seismik:oauth:session:web-ana-{'x' * 40}"), "la sesión usada se cierra"
    assert await redis.hget("seismik:admin:deletions", body["request_id"]) is not None
    entry = (await redis.xrange(settings.account_deletion_request_stream))[-1][1]["payload"]
    assert "ana@example.test" not in entry, "la bitácora no guarda el correo"


@pytest.mark.asyncio
async def test_erasing_the_owner_hands_the_circle_to_the_member_who_joined_first_and_the_last_one_closes_it() -> None:
    redis = FakeRedis(decode_responses=True)
    app = build(redis)
    async with client_for(app) as client:
        owner = await mobile_session(redis, "owner", authenticated_at=int(time.time()) - 5)
        ana = await mobile_session(redis, "ana", authenticated_at=int(time.time()) - 5)
        bea = await mobile_session(redis, "bea", authenticated_at=int(time.time()) - 5)
        await client.post("/v1/family/circle", headers=owner, json={"display_name": "Óscar"})
        for headers, name in ((ana, "Ana"), (bea, "Bea")):
            invite = (await client.post("/v1/family/circle/invitations", headers=owner, json={"display_name": name})).json()
            joined = await client.post("/v1/family/join", headers=headers, json={"invite_code": invite["invite_code"], "display_name": name})
            assert joined.status_code == 200
        circle = await redis.get("seismik:family:account:owner")
        await redis.hset(f"seismik:family:member:{circle}:ana", "joined_at", "2026-01-01T00:00:00+00:00")
        await redis.hset(f"seismik:family:member:{circle}:bea", "joined_at", "2026-02-01T00:00:00+00:00")
        await redis.set(f"seismik:family:location:{circle}:owner", "{}", ex=600)
        await redis.set(f"seismik:family:status:{circle}:owner", "{}", ex=600)
        await redis.set("seismik:family:auto-location:owner", "1")

        result = await erase_account(redis, app.state.settings, uid="owner")
        assert result["family_circle"] is True
        assert await redis.hget(f"seismik:family:circle:{circle}", "owner_uid") == "ana"
        assert await redis.smembers(f"seismik:family:members:{circle}") == {"ana", "bea"}
        assert not await redis.exists(f"seismik:family:member:{circle}:owner", f"seismik:family:location:{circle}:owner",
                                      f"seismik:family:status:{circle}:owner", "seismik:family:account:owner",
                                      "seismik:family:auto-location:owner")

        await erase_account(redis, app.state.settings, uid="ana")
        await erase_account(redis, app.state.settings, uid="bea")
        assert not await redis.exists(f"seismik:family:circle:{circle}", f"seismik:family:members:{circle}")


@pytest.mark.asyncio
async def test_sessions_issued_before_the_erasure_stop_working_and_a_new_login_does_too() -> None:
    redis = FakeRedis(decode_responses=True)
    app = build(redis)
    now = int(time.time())
    async with client_for(app) as client:
        old = await mobile_session(redis, "ana", authenticated_at=now - 60)
        assert (await client.post("/v1/family/circle", headers=old, json={"display_name": "Ana"})).status_code == 201

        await erase_account(redis, app.state.settings, uid="ana")

        assert (await client.get("/v1/family/circle", headers=old)).status_code == 401, "la sesión anterior queda inválida"
        later = await mobile_session(redis, "ana", authenticated_at=now + 30)
        assert (await client.post("/v1/family/circle", headers=later, json={"display_name": "Ana"})).status_code == 201

    assert await session_was_erased(redis, {"uid": "ana", "authenticated_at": str(now - 1)}) is True
    assert await session_was_erased(redis, {"uid": "ana", "authenticated_at": str(now + 30)}) is False
    assert await session_was_erased(redis, {"uid": "otra", "authenticated_at": "1"}) is False


@pytest.mark.asyncio
async def test_firebase_user_is_deleted_and_a_failure_is_reported_instead_of_hidden() -> None:
    redis = FakeRedis(decode_responses=True)
    settings = AppSettings()
    deleted: list[str] = []

    async def works(firebase_uid: str) -> None:
        deleted.append(firebase_uid)

    async def fails(firebase_uid: str) -> None:
        raise RuntimeError("Firebase no responde")

    await redis.set("seismik:identity:firebase:" + __import__("hashlib").sha256(b"fb-1").hexdigest(), "ana")
    ok = await erase_account(redis, settings, uid="ana", firebase_uid="fb-1", delete_firebase_user=works)
    assert deleted == ["fb-1"] and ok["pending"] == []
    assert not await redis.keys("seismik:identity:firebase:*"), "el vínculo de identidad se borra"

    bad = await erase_account(redis, settings, uid="ana", firebase_uid="fb-1", delete_firebase_user=fails)
    assert bad["pending"] == ["firebase_authentication"], "el fallo queda a la vista para repetirlo"
    again = await erase_account(redis, settings, uid="ana")
    assert again["devices"] == 0, "repetir el borrado no rompe nada"


@pytest.mark.asyncio
async def test_a_person_can_only_try_five_times_an_hour() -> None:
    redis = FakeRedis(decode_responses=True)
    async with client_for(build(redis)) as client:
        codes = []
        for _ in range(6):
            client.cookies.set("seismik_session", await web_session(redis, "ana", age=0))
            codes.append((await client.post("/v1/account/erasure", json={"confirm": "ELIMINAR"}, headers=ORIGIN)).status_code)
    assert codes == [200] * 5 + [429]


@pytest.mark.asyncio
async def test_login_for_erasure_sets_a_fixed_marker_and_returns_to_the_deletion_page() -> None:
    redis = FakeRedis(decode_responses=True)
    async with client_for(build(redis)) as client:
        start = await client.get("/v1/account/erasure/login")
    assert start.status_code == 303 and start.headers["location"] == "https://auth.seismik.org/id"
    cookie = start.headers["set-cookie"]
    assert "seismik_after_login=delete-account" in cookie and "HttpOnly" in cookie and "Domain=.seismik.org" in cookie

    def request(cookie_header: str) -> Request:
        app = FastAPI()
        app.state.settings = AppSettings()
        app.state.redis = FakeRedis(decode_responses=True)
        return Request({"type": "http", "app": app, "headers": [(b"cookie", cookie_header.encode())],
                        "method": "GET", "path": "/", "query_string": b""})

    user = {"uid": "u-1", "email": "a@example.test", "name": "Ana"}
    back = await _finish_login(request("seismik_after_login=delete-account"), user, None)
    assert back.headers["location"] == "https://seismik.org/delete-account/#confirmar"
    cleared = next(item for item in back.headers.getlist("set-cookie") if item.startswith("seismik_after_login="))
    assert "Max-Age=0" in cleared
    for value in ("delete-account:https://evil.example", "DELETE-ACCOUNT", "https://evil.example"):
        other = await _finish_login(request(f"seismik_after_login={value}"), user, None)
        assert other.headers["location"] == "https://devs.seismik.org/", value
    mobile = await _finish_login(request("seismik_after_login=delete-account"), user, "seismik://auth/callback")
    assert mobile.headers["location"].startswith("seismik://auth/callback?code="), "la app nunca se desvía a la web"


def test_every_kind_of_personal_key_is_listed_as_erased_or_retained() -> None:
    """Si alguien añade datos por cuenta, esta lista debe decirlo: la política promete lo que aquí se borra."""

    assert len(account_erasure.ERASED) == 5 and account_erasure.RETAINED
    source: Any = open("src/api/account_erasure.py", encoding="utf-8").read()
    for fragment in ("account_devices_key", "_erase_family", "_erase_developer", "_erase_reports", "erased_marker_key"):
        assert fragment in source
