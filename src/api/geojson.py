"""Salida GeoJSON (RFC 7946) para los endpoints públicos de eventos y estaciones.

Convenciones:

- Las coordenadas son ``[longitud, latitud]`` en WGS 84, siempre en dos dimensiones. La profundidad
  no va como tercera coordenada: en RFC 7946 es altitud (positiva hacia arriba) y confundiría a
  quien la lea como profundidad; viaja en ``properties.depth_km``.
- Un evento sin coordenadas válidas no se descarta: sale con ``geometry: null``, que el estándar permite.
- Los campos que no son de un evento (fuentes, errores parciales, caché) van en el miembro
  ``metadata`` de la colección, un miembro externo permitido por el estándar.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import Query
from fastapi.responses import JSONResponse

GEOJSON_MEDIA_TYPE = "application/geo+json"

OutputFormat = Literal["json", "geojson"]

# Documentado en OpenAPI y reutilizado por todos los endpoints que ofrecen el formato.
FORMAT_QUERY = Query(
    default="json",
    description="`json` (por defecto) o `geojson`: una FeatureCollection RFC 7946 con `Content-Type: application/geo+json`.",
)

GEOJSON_RESPONSE: dict[int | str, dict[str, Any]] = {
    200: {"content": {GEOJSON_MEDIA_TYPE: {"schema": {"type": "object"}}}, "description": "JSON, o GeoJSON con `format=geojson`."}
}


class GeoJSONResponse(JSONResponse):
    media_type = GEOJSON_MEDIA_TYPE


def _point(latitude: Any, longitude: Any) -> dict[str, Any] | None:
    if isinstance(latitude, bool) or isinstance(longitude, bool):
        return None
    if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
        return None
    if not (-90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0):
        return None
    return {"type": "Point", "coordinates": [float(longitude), float(latitude)]}


def feature(item: dict[str, Any], *, identifier: str | None) -> dict[str, Any]:
    """Un registro con `latitude` y `longitude` como Feature; el resto de campos son las propiedades."""

    properties = {name: value for name, value in item.items() if name not in {"latitude", "longitude"}}
    result: dict[str, Any] = {
        "type": "Feature",
        "geometry": _point(item.get("latitude"), item.get("longitude")),
        "properties": properties,
    }
    if identifier:
        result["id"] = identifier
    return result


def feature_collection(
    items: list[dict[str, Any]], *, id_field: str, metadata: dict[str, Any] | None = None
) -> GeoJSONResponse:
    collection: dict[str, Any] = {
        "type": "FeatureCollection",
        "features": [feature(item, identifier=_text(item.get(id_field))) for item in items],
    }
    if metadata:
        collection["metadata"] = metadata
    return GeoJSONResponse(collection)


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None
