from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import uvicorn
from fastapi import FastAPI
from redis.asyncio import Redis

from api.bus import RedisEventBus
from api.config import AppSettings, get_settings
from api.devices import router as devices_router
from api.devices_store import DeviceRepository
from api.history import router as history_router
from api.integrity import DeviceIntegrityVerifier
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

    app = FastAPI(
        title="Seismik Platform API",
        version="0.3.0",
        lifespan=lifespan,
    )
    app.include_router(webhooks_router)
    app.include_router(devices_router)
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
