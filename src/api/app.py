from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis

from api.alerts import router as alerts_router
from api.bus import RedisEventBus
from api.config import AppSettings, get_settings
from api.developer_keys import router as developer_keys_router
from api.devices import router as devices_router
from api.devices_store import DeviceRepository
from api.family import router as family_router
from api.history import router as history_router
from api.integrations import router as integrations_router
from api.integrity import DeviceIntegrityVerifier
from api.oauth import identity_router as oauth_identity_router
from api.oauth import router as oauth_router
from api.public import router as public_router
from api.webhooks import router as webhooks_router
from crowdsourcing.cluster import CrowdClusterEngine
from crowdsourcing.ingest import router as crowd_router
from reporting.ingest import router as reporting_router


def create_app(settings: AppSettings | None = None) -> FastAPI:
    resolved = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        redis = Redis.from_url(resolved.redis_url, decode_responses=True)
        await redis.ping()
        app.state.redis = redis
        app.state.settings = resolved
        app.state.bus = RedisEventBus(
            redis, resolved.stream_maxlen, resolved.webhook_idempotency_seconds
        )
        app.state.devices = DeviceRepository(redis)
        app.state.integrity_verifier = DeviceIntegrityVerifier(resolved)
        app.state.crowd_cluster = CrowdClusterEngine(redis, resolved)
        try:
            yield
        finally:
            await redis.aclose()

    # `/docs` y `/openapi.json` publican el esquema exacto de todos los
    # endpoints, incluidos los de ingesta firmada (`/v1/events/candidate`,
    # `/v1/events/official-update`). Eso es útil mientras se desarrolla y es
    # material de reconocimiento en un servidor expuesto: quien quiera
    # inyectar un sismo falso ya no tiene que adivinar el cuerpo. El portal
    # documenta por su cuenta lo que las personas desarrolladoras necesitan.
    is_development = resolved.environment.lower() == "development"
    app = FastAPI(
        title="Seismik Platform API",
        version="0.4.0",
        lifespan=lifespan,
        docs_url="/docs" if is_development else None,
        redoc_url="/redoc" if is_development else None,
        openapi_url="/openapi.json" if is_development else None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved.developer_portal_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Seismik-API-Key"],
        max_age=600,
    )
    app.include_router(webhooks_router)
    app.include_router(devices_router)
    app.include_router(family_router)
    app.include_router(alerts_router)
    app.include_router(developer_keys_router)
    app.include_router(integrations_router)
    app.include_router(oauth_router)
    app.include_router(oauth_identity_router)
    app.include_router(crowd_router)
    app.include_router(public_router)
    app.include_router(history_router)
    app.include_router(reporting_router)

    @app.get("/health/live", tags=["health"])
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready", tags=["health"])
    async def ready() -> dict[str, str]:
        await app.state.redis.ping()
        return {"status": "ready"}

    return app


app = create_app()


def main() -> None:
    uvicorn.run("api.app:app", host="0.0.0.0", port=8000, proxy_headers=True)


if __name__ == "__main__":
    main()
