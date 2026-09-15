"""Iniciar sesión con Apple en auth.seismik.org."""
from __future__ import annotations

import json
import time
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from fakeredis.aioredis import FakeRedis
from fastapi import FastAPI
from jwt.algorithms import RSAAlgorithm

from api import oauth
from api.config import AppSettings
from api.oauth import identity_router, router

CLIENT_ID = "org.seismik.auth"
# Claves fabricadas en cada ejecución: la .p8 de Seismik nunca entra al repositorio.
TEAM_KEY = ec.generate_private_key(ec.SECP256R1())
TEAM_P8 = TEAM_KEY.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption(),
).decode()
APPLE_SIGNING_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
JWKS = {
    "keys": [
        {
            **json.loads(RSAAlgorithm.to_jwk(APPLE_SIGNING_KEY.public_key())),
            "kid": "apple-test-kid",
            "alg": "RS256",
            "use": "sig",
        }
    ]
}
APP_CHALLENGE = "a" * 43


def apple_settings(**overrides: object) -> AppSettings:
    values: dict[str, object] = {
        "oauth_apple_client_id": CLIENT_ID,
        "oauth_apple_team_id": "TEAM123456",
        "oauth_apple_key_id": "KEY1234567",
        "oauth_apple_private_key": TEAM_P8,
        **overrides,
    }
    return AppSettings(**values)  # type: ignore[arg-type]


def apple_app(**overrides: object) -> FastAPI:
    app = FastAPI()
    app.state.redis = FakeRedis(decode_responses=True)
    app.state.settings = apple_settings(**overrides)
    app.include_router(router)
    app.include_router(identity_router)
    return app


def id_token(**claims: object) -> str:
    now = int(time.time())
    payload = {
        "iss": "https://appleid.apple.com",
        "aud": CLIENT_ID,
        "sub": "001234.apple-user",
        "iat": now,
        "exp": now + 600,
        "email": "ana@privaterelay.appleid.com",
        "email_verified": "true",
        **claims,
    }
    return jwt.encode(payload, APPLE_SIGNING_KEY, algorithm="RS256", headers={"kid": "apple-test-kid"})


def client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://auth.seismik.org")


async def start_app_flow(http: httpx.AsyncClient) -> dict[str, str]:
    created = await http.get(
        f"/v1/oauth/authorize?provider=apple&origin=app&app_challenge={APP_CHALLENGE}",
        follow_redirects=False,
    )
    started = await http.get(created.headers["location"], follow_redirects=False)
    query = parse_qs(urlparse(started.headers["location"]).query)
    return {key: values[0] for key, values in query.items()}


async def post_callback(http: httpx.AsyncClient, form: dict[str, str]) -> httpx.Response:
    return await http.post(
        "/v1/oauth/apple/callback",
        content=urlencode(form),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        follow_redirects=False,
    )


def apple_returns(monkeypatch: pytest.MonkeyPatch, token: str) -> None:
    async def token_and_keys(_settings: object, code: str) -> tuple[dict, dict]:
        assert code == "apple-code"
        return {"id_token": token}, JWKS

    monkeypatch.setattr(oauth, "_apple_token_and_keys", token_and_keys)


@pytest.mark.asyncio
async def test_apple_is_advertised_only_when_fully_configured() -> None:
    async with client(apple_app()) as http:
        configured = await http.get("/v1/oauth/providers")
    async with client(apple_app(oauth_apple_key_id="")) as http:
        partial = await http.get("/v1/oauth/providers")
        refused = await http.get("/v1/oauth/login?provider=apple")

    assert configured.json()["providers"]["apple"] == {"enabled": True}
    assert partial.json()["providers"]["apple"] == {"enabled": False}
    assert refused.status_code == 503


@pytest.mark.asyncio
async def test_apple_login_asks_for_name_and_email_with_a_form_post_and_a_nonce() -> None:
    app = apple_app()
    async with client(app) as http:
        response = await http.get("/v1/oauth/login?provider=apple", follow_redirects=False)

    target = urlparse(response.headers["location"])
    query = parse_qs(target.query)
    assert f"{target.scheme}://{target.netloc}{target.path}" == "https://appleid.apple.com/auth/authorize"
    assert query["client_id"] == [CLIENT_ID]
    assert query["redirect_uri"] == ["https://auth.seismik.org/v1/oauth/apple/callback"]
    assert query["response_mode"] == ["form_post"]
    assert query["scope"] == ["name email"]
    saved = json.loads(await app.state.redis.get(f"seismik:oauth:state:{query['state'][0]}"))
    assert saved["provider"] == "apple"
    assert saved["nonce"] == query["nonce"][0]


def test_client_secret_is_a_short_lived_es256_jwt_signed_with_the_p8_key() -> None:
    for key in (TEAM_P8, TEAM_P8.replace("\n", "\\n")):
        secret = oauth.apple_client_secret(apple_settings(oauth_apple_private_key=key))
        claims = jwt.decode(
            secret, TEAM_KEY.public_key(), algorithms=["ES256"], audience="https://appleid.apple.com"
        )
        assert jwt.get_unverified_header(secret)["kid"] == "KEY1234567"
        assert claims["iss"] == "TEAM123456"
        assert claims["sub"] == CLIENT_ID
        assert claims["exp"] - claims["iat"] == 300


@pytest.mark.asyncio
async def test_a_verified_apple_identity_signs_in_to_the_app(monkeypatch: pytest.MonkeyPatch) -> None:
    app = apple_app()
    async with client(app) as http:
        flow = await start_app_flow(http)
        apple_returns(monkeypatch, id_token(nonce=flow["nonce"]))
        response = await post_callback(
            http,
            {
                "code": "apple-code",
                "state": flow["state"],
                "user": json.dumps({"name": {"firstName": "Ana", "lastName": "Pérez"}}),
            },
        )

    assert response.status_code == 303
    target = urlparse(response.headers["location"])
    assert f"{target.scheme}://{target.netloc}{target.path}" == "seismik://auth/callback"
    code = parse_qs(target.query)["code"][0]
    saved = json.loads(await app.state.redis.get(f"seismik:oauth:mobile-code:{code}"))
    assert saved["uid"] == "apple:001234.apple-user"
    assert saved["email"] == "ana@privaterelay.appleid.com"
    assert saved["name"] == "Ana Pérez"
    assert saved["app_challenge"] == APP_CHALLENGE
    # El estado es de un solo uso: repetir el POST no vuelve a iniciar sesión.
    async with client(app) as http:
        replay = await post_callback(http, {"code": "apple-code", "state": flow["state"]})
    assert replay.status_code == 400


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "claims",
    [
        {"nonce": "otro-inicio"},
        {"aud": "com.otra.app"},
        {"iss": "https://appleid.example"},
        {"exp": int(time.time()) - 3_600},
    ],
)
async def test_an_identity_token_that_does_not_belong_to_this_login_is_rejected(
    monkeypatch: pytest.MonkeyPatch, claims: dict[str, object]
) -> None:
    app = apple_app()
    async with client(app) as http:
        flow = await start_app_flow(http)
        apple_returns(monkeypatch, id_token(**{"nonce": flow["nonce"], **claims}))
        response = await post_callback(http, {"code": "apple-code", "state": flow["state"]})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_a_token_signed_by_another_key_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    impostor = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    app = apple_app()
    async with client(app) as http:
        flow = await start_app_flow(http)
        now = int(time.time())
        forged = jwt.encode(
            {"iss": "https://appleid.apple.com", "aud": CLIENT_ID, "sub": "x", "iat": now,
             "exp": now + 600, "nonce": flow["nonce"], "email": "x@example.com", "email_verified": "true"},
            impostor,
            algorithm="RS256",
            headers={"kid": "apple-test-kid"},
        )
        apple_returns(monkeypatch, forged)
        response = await post_callback(http, {"code": "apple-code", "state": flow["state"]})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_an_unverified_email_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    app = apple_app()
    async with client(app) as http:
        flow = await start_app_flow(http)
        apple_returns(monkeypatch, id_token(nonce=flow["nonce"], email_verified="false"))
        response = await post_callback(http, {"code": "apple-code", "state": flow["state"]})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_closing_the_apple_sheet_returns_to_the_app_without_an_error_page() -> None:
    app = apple_app()
    async with client(app) as http:
        flow = await start_app_flow(http)
        response = await post_callback(http, {"error": "user_cancelled_authorize", "state": flow["state"]})
        unknown = await post_callback(http, {"code": "apple-code", "state": "desconocido"})

    assert response.status_code == 303
    assert response.headers["location"] == "seismik://auth/callback?error=cancelled"
    assert unknown.status_code == 400
