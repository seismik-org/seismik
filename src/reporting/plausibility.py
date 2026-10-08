"""Coherencia de un reporte ciudadano con el sismo que dice haber sentido.

Las fórmulas son orientativas, no un modelo de intensidad: sólo separan los
reportes evidentemente imposibles (un M3 «sentido» a 5 000 km, una intensidad
VIII a 400 km de un M4) para que quien los revisa los vea primero. Nunca
rechazan un envío: el reporte se guarda igual y la marca acompaña al dato.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any, Literal, TypedDict

Status = Literal["plausible", "implausible", "unknown"]

# Margen sobre la intensidad esperada antes de considerarla exagerada.
INTENSITY_MARGIN = 3.0
# Un reporte con hora anterior al sismo sólo se tolera por relojes desajustados.
EARLY_TOLERANCE = timedelta(minutes=10)


class Assessment(TypedDict):
    status: Status
    distance_km: float | None
    felt_radius_km: float | None
    expected_mmi: float | None
    reasons: list[str]


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    rad = math.pi / 180
    d_lat, d_lon = (lat2 - lat1) * rad, (lon2 - lon1) * rad
    h = (
        math.sin(d_lat / 2) ** 2
        + math.cos(lat1 * rad) * math.cos(lat2 * rad) * math.sin(d_lon / 2) ** 2
    )
    return 12742 * math.asin(min(1.0, math.sqrt(h)))


def felt_radius_km(magnitude: float) -> float:
    """Distancia a la que una persona suele dejar de notar el sismo."""
    return float(10 ** (0.42 * magnitude + 0.2))


def expected_mmi(magnitude: float, epicentral_km: float, depth_km: float) -> float:
    hypocentral = max(5.0, math.hypot(epicentral_km, depth_km))
    return 1.0 + 1.5 * magnitude - 3.0 * math.log10(hypocentral)


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def _time(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def assess(report: dict[str, Any], event: dict[str, Any] | None) -> Assessment:
    """`event` usa la forma de `recent_web_events` (o el `preferred_report`)."""
    result: Assessment = {
        "status": "unknown",
        "distance_km": None,
        "felt_radius_km": None,
        "expected_mmi": None,
        "reasons": [],
    }
    if event is None:
        result["reasons"].append(
            "No indica un sismo del catálogo" if not report.get("earthquake_event_id")
            else "El sismo ya no está en el catálogo reciente"
        )
        return result
    lat, lon = _number(report.get("latitude")), _number(report.get("longitude"))
    e_lat, e_lon = _number(event.get("latitude")), _number(event.get("longitude"))
    magnitude = _number(event.get("magnitude"))
    if None in (lat, lon, e_lat, e_lon) or magnitude is None:
        result["reasons"].append("Falta la ubicación o la magnitud para comparar")
        return result
    assert lat is not None and lon is not None and e_lat is not None and e_lon is not None
    distance = distance_km(lat, lon, e_lat, e_lon)
    radius = felt_radius_km(magnitude)
    expected = expected_mmi(magnitude, distance, _number(event.get("depth_km")) or 10.0)
    result["distance_km"] = round(distance, 1)
    result["felt_radius_km"] = round(radius, 1)
    result["expected_mmi"] = round(expected, 1)
    result["status"] = "plausible"
    observed, origin = _time(report.get("observed_at")), _time(event.get("origin_time"))
    comparable = observed and origin and observed.tzinfo and origin.tzinfo
    if comparable and observed and origin and observed < origin - EARLY_TOLERANCE:
        result["reasons"].append("La hora del reporte es anterior al sismo")
    # Decir que no se sintió nunca es incoherente: también delimita el alcance.
    if report.get("felt") is True:
        if distance > 2 * radius:
            result["reasons"].append(
                f"Demasiado lejos: {distance:.0f} km para un M {magnitude:.1f} "
                f"(se suele sentir hasta ~{radius:.0f} km)"
            )
        intensity = _number(report.get("intensity_mmi"))
        if intensity is not None and intensity > expected + INTENSITY_MARGIN:
            result["reasons"].append(
                f"Intensidad {intensity:.0f} muy por encima de la esperada (~{max(expected, 1):.0f})"
            )
    if result["reasons"]:
        result["status"] = "implausible"
    return result
