"""Un canje OAuth rechazado deja rastro útil y no expone secretos."""
from __future__ import annotations

import json
import logging

import httpx
import pytest
from fakeredis.aioredis import FakeRedis
from fastapi import FastAPI

from api.config import AppSettings
from api.oauth import identity_router, router


def oauth_app() -> FastAPI:
    app = FastAPI()
    app.state.redis = FakeRedis(decode_responses=True)
    app.state.settings = AppSettings(
        oauth_google_client_id="google-client", oauth_google_client_secret="google-secret-value"
    )
    app.include_router(router)
    app.include_router(identity_router)
    return app


def test_oauth_client_credentials_ignore_surrounding_whitespace() -> None:
    settings = AppSettings(
        oauth_google_client_id=" client.apps.googleusercontent.com\n",
        oauth_google_client_secret="secreto-del-cliente\n",
        oauth_github_client_secret="  otro-secreto \r\n",
    )

    assert settings.oauth_google_client_id == "client.apps.googleusercontent.com"
    assert settings.oauth_google_client_secret.get_secret_value() == "secreto-del-cliente"
    assert settings.oauth_github_client_secret.get_secret_value() == "otro-secreto"


class _RejectedToken:
    is_error = True
    status_code = 401

    def json(self) -> dict[str, str]:
        return {"error": "invalid_client", "error_description": "Unauthorized"}


class _GoogleRejectsClient:
    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    async def __aenter__(self) -> "_GoogleRejectsClient":
        return self

    async def __aexit__(self, *args: object) -> bool:
        return False

    async def post(self, *args: object, **kwargs: object) -> _RejectedToken:
        return _RejectedToken()


@pytest.mark.asyncio
async def test_a_rejected_google_exchange_logs_the_provider_error(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    app = oauth_app()
    await app.state.redis.set(
        "seismik:oauth:state:estado-1",
        json.dumps({"verifier": "v" * 43, "return_to": None}),
        ex=600,
    )
    # El cliente de la prueba se crea antes de sustituir httpx para el servidor.
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://auth.seismik.org")
    monkeypatch.setattr("api.oauth.httpx.AsyncClient", _GoogleRejectsClient)

    with caplog.at_level(logging.WARNING, logger="api.oauth"):
        async with client:
            response = await client.get("/v1/oauth/google/callback?code=codigo&state=estado-1")

    assert response.status_code == 401
    assert "invalid_client" in caplog.text
    assert "google-secret-value" not in caplog.text
    assert "codigo" not in caplog.text
