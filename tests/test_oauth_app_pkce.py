"""PKCE generado por la app para el retorno `seismik://auth/callback`.

En Android cualquier app puede declarar el mismo esquema y recibir el código de
un solo uso. El código sólo se canjea con el verificador que generó la app que
empezó el inicio de sesión, así que interceptarlo no sirve de nada.
"""
from __future__ import annotations

import base64
import hashlib
import json
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fakeredis.aioredis import FakeRedis
from fastapi import FastAPI

from api.config import AppSettings
from api.oauth import _finish_login, identity_router, router

VERIFIER = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"  # RFC 7636, apéndice B


def oauth_app() -> FastAPI:
    app = FastAPI()
    app.state.redis = FakeRedis(decode_responses=True)
    app.state.settings = AppSettings(
        oauth_google_client_id="google-client", oauth_google_client_secret="google-secret"
    )
    app.include_router(router)
    app.include_router(identity_router)
    return app


def client_for(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://auth.seismik.org")


def test_the_reference_vector_matches_s256() -> None:
    digest = hashlib.sha256(VERIFIER.encode()).digest()
    assert base64.urlsafe_b64encode(digest).rstrip(b"=").decode() == CHALLENGE


@pytest.mark.asyncio
async def test_the_app_challenge_travels_from_authorize_to_the_provider_state() -> None:
    app = oauth_app()
    async with client_for(app) as client:
        started = await client.get(
            f"/v1/oauth/authorize?provider=google&origin=app&app_challenge={CHALLENGE}",
            follow_redirects=False,
        )
        flow_path = started.headers["location"]
        provider = await client.get(flow_path, follow_redirects=False)

    state = parse_qs(urlparse(provider.headers["location"]).query)["state"][0]
    saved = json.loads(await app.state.redis.get(f"seismik:oauth:state:{state}"))
    assert saved["app_challenge"] == CHALLENGE
    assert saved["return_to"] == "seismik://auth/callback"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query",
    [
        f"provider=google&origin=devs&app_challenge={CHALLENGE}",  # sin retorno móvil
        "provider=google&origin=app&app_challenge=corto",
        "provider=google&origin=app&app_challenge=" + "%2F" * 50,
    ],
)
async def test_an_invalid_or_misplaced_challenge_is_rejected(query: str) -> None:
    async with client_for(oauth_app()) as client:
        response = await client.get(f"/v1/oauth/authorize?{query}", follow_redirects=False)
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_the_callback_code_carries_the_challenge() -> None:
    redis = FakeRedis(decode_responses=True)
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(redis=redis, settings=AppSettings()))
    )
    response = await _finish_login(
        request,  # type: ignore[arg-type]
        {"uid": "google-1", "email": "ana@example.test", "name": "Ana"},
        "seismik://auth/callback",
        CHALLENGE,
    )
    code = parse_qs(urlparse(response.headers["location"]).query)["code"][0]
    stored = json.loads(await redis.get(f"seismik:oauth:mobile-code:{code}"))
    assert stored["app_challenge"] == CHALLENGE


async def issue_code(app: FastAPI, name: str) -> str:
    code = f"mobile-code-{name}-" + "c" * 24
    await app.state.redis.set(
        f"seismik:oauth:mobile-code:{code}",
        json.dumps({"uid": "google-1", "email": "ana@example.test", "name": "Ana", "app_challenge": CHALLENGE}),
        ex=60,
    )
    return code


@pytest.mark.asyncio
async def test_a_stolen_code_cannot_be_exchanged_without_the_verifier() -> None:
    app = oauth_app()
    async with client_for(app) as client:
        missing = await client.post("/v1/oauth/mobile/exchange", json={"code": await issue_code(app, "a")})
        wrong = await client.post(
            "/v1/oauth/mobile/exchange",
            json={"code": await issue_code(app, "b"), "code_verifier": "x" * 43},
        )
        good = await client.post(
            "/v1/oauth/mobile/exchange",
            json={"code": await issue_code(app, "c"), "code_verifier": VERIFIER},
        )

    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert good.status_code == 200
    token = good.json()["mobile_session_token"]
    session = json.loads(await app.state.redis.get(f"seismik:oauth:mobile-session:{token}"))
    assert "app_challenge" not in session
    ttl = await app.state.redis.ttl(f"seismik:oauth:mobile-session:{token}")
    assert ttl > 86_400, "la sesión de la app dura más que la del navegador"
