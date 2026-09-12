from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fakeredis.aioredis import FakeRedis
from fastapi import FastAPI

from api.config import AppSettings
from api.oauth import identity_router, router


def oauth_app(**overrides: object) -> FastAPI:
    app = FastAPI()
    app.state.redis = FakeRedis(decode_responses=True)
    app.state.settings = AppSettings(
        oauth_google_client_id="google-client",
        oauth_google_client_secret="google-secret",
        **overrides,
    )
    app.include_router(router)
    app.include_router(identity_router)
    return app


@pytest.mark.asyncio
async def test_auth_entry_uses_auth_subdomain_callback_and_pkce() -> None:
    app = oauth_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://auth.seismik.org"
    ) as client:
        response = await client.get("/v1/oauth/login?provider=google", follow_redirects=False)

    assert response.status_code == 307
    target = urlparse(response.headers["location"])
    query = parse_qs(target.query)
    assert target.netloc == "accounts.google.com"
    assert query["redirect_uri"] == ["https://auth.seismik.org/v1/oauth/google/callback"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["state"]


@pytest.mark.asyncio
async def test_mobile_oauth_return_is_strict_and_stored_with_pkce_state() -> None:
    app = oauth_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://auth.seismik.org"
    ) as client:
        response = await client.get(
            "/v1/oauth/login?provider=google&return_to=seismik%3A%2F%2Fauth%2Fcallback",
            follow_redirects=False,
        )
        rejected = await client.get(
            "/v1/oauth/login?provider=google&return_to=https%3A%2F%2Fevil.example",
            follow_redirects=False,
        )

    assert response.status_code == 307
    state = parse_qs(urlparse(response.headers["location"]).query)["state"][0]
    saved = await app.state.redis.get(f"seismik:oauth:state:{state}")
    assert '"return_to": "seismik://auth/callback"' in saved
    assert rejected.status_code == 400


@pytest.mark.asyncio
async def test_identity_url_is_opaque_and_binds_the_app_origin() -> None:
    app = oauth_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://auth.seismik.org"
    ) as client:
        created = await client.get(
            "/v1/oauth/authorize?provider=google&origin=app", follow_redirects=False
        )
        identity_path = created.headers["location"]
        started = await client.get(identity_path, follow_redirects=False)

    assert created.status_code == 303
    assert identity_path.startswith("/id/")
    state = parse_qs(urlparse(started.headers["location"]).query)["state"][0]
    saved = await app.state.redis.get(f"seismik:oauth:state:{state}")
    assert '"return_to": "seismik://auth/callback"' in saved


@pytest.mark.asyncio
async def test_mobile_exchange_is_one_time_and_short_lived() -> None:
    app = oauth_app()
    code = "one-time-mobile-code-123"
    await app.state.redis.set(
        f"seismik:oauth:mobile-code:{code}",
        '{"uid":"u-1","email":"person@example.com","name":"Person"}',
        ex=60,
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://auth.seismik.org"
    ) as client:
        first = await client.post("/v1/oauth/mobile/exchange", json={"code": code})
        replay = await client.post("/v1/oauth/mobile/exchange", json={"code": code})

    assert first.status_code == 200
    assert first.json()["email"] == "person@example.com"
    assert len(first.json()["mobile_session_token"]) >= 64
    assert replay.status_code == 401


@pytest.mark.asyncio
async def test_only_configured_providers_are_advertised() -> None:
    disabled = oauth_app()
    enabled = oauth_app(oauth_github_client_id="github-client", oauth_github_client_secret="github-secret")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=disabled), base_url="https://devs.seismik.org") as client:
        first = await client.get("/v1/oauth/providers")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=enabled), base_url="https://devs.seismik.org") as client:
        second = await client.get("/v1/oauth/providers")

    assert first.json()["providers"] == {"google": {"enabled": True}, "github": {"enabled": False}}
    assert second.json()["providers"]["github"] == {"enabled": True}


@pytest.mark.asyncio
async def test_github_entry_requires_its_own_credentials() -> None:
    app = oauth_app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://auth.seismik.org") as client:
        response = await client.get("/v1/oauth/login?provider=github")
    assert response.status_code == 503
