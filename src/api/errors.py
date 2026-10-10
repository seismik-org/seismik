"""Códigos de error estables para quien integra la API.

El cuerpo conserva `detail` tal como siempre y añade `code`: una cadena corta y estable que no cambia
aunque se reescriba el mensaje. Es aditivo: los clientes que sólo leen `detail` siguen funcionando.

    {"detail": "Daily API quota exceeded", "code": "quota_daily"}
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

# (estado HTTP, mensaje exacto) -> código. Lo que no esté aquí recibe el código genérico de su estado.
KNOWN: dict[tuple[int, str], str] = {
    (401, "Missing or invalid Seismik API key"): "api_key_missing_or_invalid",
    (401, "Invalid Seismik API key"): "api_key_invalid",
    (403, "API key scope is insufficient"): "scope_insufficient",
    (429, "Per-minute API quota exceeded"): "rate_limit_minute",
    (429, "Daily API quota exceeded"): "quota_daily",
    (429, "Monthly API quota exceeded"): "quota_monthly",
    (429, "Demasiadas solicitudes; espera un minuto"): "rate_limit_ip",
    (503, "Station catalog is unavailable"): "station_catalog_unavailable",
    (503, "Usage meter busy; retry shortly"): "usage_meter_busy",
}

GENERIC: dict[int, str] = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    422: "invalid_parameter",
    429: "too_many_requests",
    500: "internal_error",
    502: "bad_gateway",
    503: "service_unavailable",
    504: "gateway_timeout",
}


def error_code(status_code: int, detail: Any) -> str:
    if isinstance(detail, str) and (status_code, detail) in KNOWN:
        return KNOWN[(status_code, detail)]
    if status_code in GENERIC:
        return GENERIC[status_code]
    return "client_error" if 400 <= status_code < 500 else "server_error"


async def _http_error(_request: Request, exc: Exception) -> Response:
    assert isinstance(exc, StarletteHTTPException)
    if exc.status_code in {204, 304}:  # sin cuerpo, igual que el manejador por defecto
        return Response(status_code=exc.status_code, headers=getattr(exc, "headers", None))
    return JSONResponse(
        {"detail": exc.detail, "code": error_code(exc.status_code, exc.detail)},
        status_code=exc.status_code,
        headers=getattr(exc, "headers", None),
    )


async def _validation_error(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    return JSONResponse(
        {"detail": jsonable_encoder(exc.errors()), "code": "invalid_parameter"}, status_code=422
    )


def install(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
