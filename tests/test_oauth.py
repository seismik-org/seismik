from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fakeredis.aioredis import FakeRedis
from fastapi import FastAPI

from api.config import AppSettings
from api.oauth import router


def oauth_app(**overrides: object) -> FastAPI:
    app = FastAPI()
    app.state.redis = FakeRedis(decode_responses=True)
    app.state.settings = AppSettings(
        oauth_google_client_id="google-client",
        oauth_google_client_secret="google-secret",
        **overrides,
    )
    app.include_router(router)
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
