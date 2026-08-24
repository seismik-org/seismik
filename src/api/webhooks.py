from __future__ import annotations

from typing import TypeVar

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, ValidationError

from api.bus import RedisEventBus
from api.config import AppSettings
from api.dependencies import get_app_settings, get_bus
from api.schemas import AcceptedResponse, EarthquakeCandidate, OfficialReportUpdate
from api.security import verify_signature

router = APIRouter(prefix="/v1/events", tags=["events"])
EventModel = TypeVar("EventModel", bound=BaseModel)


async def _ingest(
    request: Request,
    model: type[EventModel],
    stream: str,
    bus: RedisEventBus,
    settings: AppSettings,
    timestamp: str | None,
    signature: str | None,
) -> AcceptedResponse:
    body = await request.body()
    verify_signature(
        secret=settings.webhook_hmac_secret.get_secret_value(),
        timestamp=timestamp,
        signature=signature,
        body=body,
        max_skew_seconds=settings.webhook_max_skew_seconds,
    )
    try:
        event = model.model_validate_json(body)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.errors()) from exc
    result = await bus.publish_once(stream, event.model_dump(mode="json"))
    return AcceptedResponse(
        accepted=True,
        duplicate=not result.accepted,
        stream_id=result.stream_id,
    )


@router.post(
    "/candidate",
    response_model=AcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": EarthquakeCandidate.model_json_schema()}},
        }
    },
)
async def ingest_candidate(
    request: Request,
    x_webhook_timestamp: str | None = Header(default=None, alias="X-Seismik-Timestamp"),
    x_signature_sha256: str | None = Header(default=None, alias="X-Seismik-Signature"),
    bus: RedisEventBus = Depends(get_bus),
    settings: AppSettings = Depends(get_app_settings),
) -> AcceptedResponse:
    return await _ingest(
        request, EarthquakeCandidate, settings.candidate_stream, bus, settings,
        x_webhook_timestamp, x_signature_sha256,
    )


@router.post(
    "/official-update",
    response_model=AcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": OfficialReportUpdate.model_json_schema()}},
        }
    },
)
async def ingest_official_update(
    request: Request,
    x_webhook_timestamp: str | None = Header(default=None, alias="X-Seismik-Timestamp"),
    x_signature_sha256: str | None = Header(default=None, alias="X-Seismik-Signature"),
    bus: RedisEventBus = Depends(get_bus),
    settings: AppSettings = Depends(get_app_settings),
) -> AcceptedResponse:
    return await _ingest(
        request, OfficialReportUpdate, settings.official_stream, bus, settings,
        x_webhook_timestamp, x_signature_sha256,
    )
