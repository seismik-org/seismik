from __future__ import annotations

import json
import time
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fakeredis.aioredis import FakeRedis
from fastapi import Depends, FastAPI

from api import firebase_login
from api.accounts import require_account_session
from api.config import AppSettings
from api.oauth import _challenge, identity_router, router


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

    def verify(token: str, **kwargs: Any) -> dict[str, Any]:
        assert kwargs["check_revoked"] is True
        if token == "invalid" * 5:
            raise ValueError("invalid")
        return app.state.claims.copy()

    monkeypatch.setattr(firebase_login.auth, "verify_id_token", verify)
    monkeypatch.setattr(firebase_login.auth, "get_user", lambda *a, **k: app.state.user)
    app.include_router(router)
    app.include_router(identity_router)
    app.include_router(firebase_login.router)

    @app.get("/protected-mobile")
    async def protected(account: Any = Depends(require_account_session)) -> dict[str, str]:
        return {"uid": account.uid}

    return app


def client_for(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://auth.seismik.org", headers={"Origin": "https://auth.seismik.org"})


async def exchange(client: httpx.AsyncClient, **kwargs: Any) -> httpx.Response:
    return await client.post("/v1/oauth/email/exchange", json={"id_token": "verified-token" * 3, **kwargs})


async def legacy_session(app: FastAPI, client: httpx.AsyncClient, **changes: Any) -> None:
    user = {"uid": "github:123", "email": "same@example.org", "name": "Existing", "authenticated_at": str(int(time.time())), **changes}
    await app.state.redis.set("seismik:oauth:session:legacy", json.dumps(user), ex=300)
    client.cookies.set("seismik_session", "legacy", domain=".seismik.org")


async def test_verified_login_cookie_logout_and_expiry(app: FastAPI) -> None:
    async with client_for(app) as client:
        result = await exchange(client)
        assert result.status_code == 200
        assert result.json()["redirect"] == "https://devs.seismik.org/"
        cookie = result.headers["set-cookie"].lower()
        assert "httponly" in cookie and "secure" in cookie and "samesite=lax" in cookie
        assert (await client.get("/v1/oauth/session")).json()["uid"] == "firebase-person"
        assert (await client.post("/v1/oauth/logout")).status_code == 204
        assert (await client.get("/v1/oauth/session")).status_code == 401
        await exchange(client)
        await app.state.redis.delete("seismik:oauth:session:" + client.cookies.get("seismik_session"))
        assert (await client.get("/v1/oauth/session")).status_code == 401


@pytest.mark.parametrize("claims", [{"email_verified": False}, {"email": ""}, {"auth_time": 1}, {"firebase": {"sign_in_provider": "google.com"}}])
async def test_rejects_unverified_stale_or_other_provider(app: FastAPI, claims: dict[str, Any]) -> None:
    app.state.claims.update(claims)
    async with client_for(app) as client:
        result = await exchange(client)
    assert result.status_code in (401, 403)
    assert not await app.state.redis.keys("seismik:oauth:session:*")


async def test_invalid_token_and_cross_origin_do_not_issue_session(app: FastAPI) -> None:
    async with client_for(app) as client:
        assert (await client.post("/v1/oauth/email/exchange", json={"id_token": "invalid" * 5})).status_code == 401
        client.headers["origin"] = "https://attacker.example"
        assert (await exchange(client, link=True)).status_code == 403


async def test_email_match_alone_never_links_existing_account(app: FastAPI) -> None:
    async with client_for(app) as client:
        await legacy_session(app, client)
        await exchange(client)
        assert (await client.get("/v1/oauth/session")).json()["uid"] == "firebase-person"


async def test_explicit_link_preserves_family_devices_and_api_keys(app: FastAPI) -> None:
    redis = app.state.redis
    await redis.set("seismik:family:account:github:123", "circle")
    await redis.sadd("seismik:account:devices:github:123", "phone")
    await redis.sadd("seismik:developer-keys:github:123", "api-key")
    async with client_for(app) as client:
        await legacy_session(app, client)
        assert (await exchange(client, link=True)).status_code == 200
        assert (await client.get("/v1/oauth/session")).json()["uid"] == "github:123"
        await client.post("/v1/oauth/logout")
        await exchange(client)
        assert (await client.get("/v1/oauth/session")).json()["uid"] == "github:123"
    assert await redis.get("seismik:family:account:github:123") == "circle"
    assert await redis.smembers("seismik:account:devices:github:123") == {"phone"}
    assert await redis.smembers("seismik:developer-keys:github:123") == {"api-key"}


async def test_link_requires_recent_other_identity_and_rejects_existing_binding(app: FastAPI) -> None:
    async with client_for(app) as client:
        assert (await exchange(client, link=True)).status_code == 401
        await legacy_session(app, client, authenticated_at="1")
        assert (await exchange(client, link=True)).status_code == 401
        await legacy_session(app, client)
        await app.state.redis.set(firebase_login.binding_key("firebase-person"), "other-account")
        assert (await exchange(client, link=True)).status_code == 409
        assert await app.state.redis.get(firebase_login.binding_key("firebase-person")) == "other-account"


async def test_link_refuses_to_orphan_firebase_data(app: FastAPI) -> None:
    await app.state.redis.sadd("seismik:developer-keys:firebase-person", "existing-key")
    async with client_for(app) as client:
        await legacy_session(app, client)
        assert (await exchange(client, link=True)).status_code == 409
    assert await app.state.redis.smembers("seismik:developer-keys:firebase-person") == {"existing-key"}


@pytest.mark.parametrize("change", [{"disabled": True}, {"email_verified": False}, {"tokens_valid_after_timestamp": (time.time() + 10) * 1000}])
async def test_reset_disabled_or_unverified_revokes_existing_cookie(app: FastAPI, change: dict[str, Any]) -> None:
    async with client_for(app) as client:
        await exchange(client)
        for key, value in change.items():
            setattr(app.state.user, key, value)
        assert (await client.get("/v1/oauth/session")).status_code == 401


async def test_mobile_preserves_pkce_one_time_exchange_and_revocation(app: FastAPI) -> None:
    verifier = "v" * 64
    async with client_for(app) as client:
        start = await client.get("/v1/oauth/authorize", params={"provider": "email", "origin": "app", "app_challenge": _challenge(verifier)})
        flow_id = start.headers["location"].rsplit("/", 1)[1]
        page = await client.get(start.headers["location"])
        assert flow_id in page.headers["location"]
        result = await exchange(client, flow_id=flow_id)
        assert result.status_code == 200
        code = parse_qs(urlparse(result.json()["redirect"]).query)["code"][0]
        assert (await exchange(client, flow_id=flow_id)).status_code == 410
        mobile = await client.post("/v1/oauth/mobile/exchange", json={"code": code, "code_verifier": verifier})
        assert mobile.status_code == 200
        assert (await client.post("/v1/oauth/mobile/exchange", json={"code": code, "code_verifier": verifier})).status_code == 401
        headers = {"X-Seismik-Account-Session": mobile.json()["mobile_session_token"]}
        assert (await client.get("/protected-mobile", headers=headers)).json()["uid"] == "firebase-person"
        app.state.user.disabled = True
        assert (await client.get("/protected-mobile", headers=headers)).status_code == 401


async def test_mobile_requires_pkce_and_rate_limit_blocks_abuse(app: FastAPI) -> None:
    async with client_for(app) as client:
        assert (await client.get("/v1/oauth/authorize?provider=email&origin=app")).status_code == 400
        app.state.claims["email_verified"] = False
        for _ in range(20):
            assert (await exchange(client)).status_code == 403
        result = await exchange(client)
        assert result.status_code == 429
        assert result.headers["retry-after"] == "60"
