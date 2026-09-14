"""Perímetro de sacudida: dónde se siente un sismo y con qué intensidad.

La intensidad de Mercalli modificada (MMI) describe lo que la gente siente en
un lugar, no el tamaño del sismo. Se estima con modelos publicados según la
profundidad del foco:

- Corticales (hasta 40 km): Allen, Wald y Worden (2012), versión con distancia
  hipocentral, ajustada con reportes «¿Lo sentiste?» del USGS.
- Intermedios (desde 70 km), como el Nido de Bucaramanga: aceleración de Zhao
  et al. (2006) para sismos intraplaca en suelo firme, convertida a MMI con
  Worden et al. (2012). Allen 2012 se calibró con sismos someros: para un M4 a
  150 km de profundidad predice que no se siente, y en Bucaramanga sí se siente.
- Entre 40 y 70 km se interpola linealmente para no crear un salto.

Coeficientes de OpenQuake (allen_2012_ipe.py, zhao_2006.py) y de ShakeLib
(gmice/wgrw12.py). La app replica este módulo en
mobile_app/lib/core/felt_area.dart y las pruebas de ambos comparten valores.
"""
from __future__ import annotations

import math

EARTH_RADIUS_KM = 6371.0088
# Profundidad habitual de un sismo cortical cuando el reporte no la trae.
DEFAULT_DEPTH_KM = 10.0
CRUSTAL_UNTIL_KM = 40.0
INTRASLAB_FROM_KM = 70.0
MAX_RADIUS_KM = 2_000.0

# Umbrales de la escala MMI que usan la alarma y el mapa.
FELT = 3.0  # III: se siente dentro de las casas.
LIGHT = 4.0  # IV: lo siente casi todo el que está bajo techo.
STRONG = 6.0  # VI: lo siente todo el mundo; puede haber daños leves.
SEVERE = 8.0  # VIII: daños considerables.

_ROMAN = ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII")


def haversine_km(
    latitude_a: float, longitude_a: float, latitude_b: float, longitude_b: float
) -> float:
    phi_a, phi_b = math.radians(latitude_a), math.radians(latitude_b)
    delta_phi = math.radians(latitude_b - latitude_a)
    delta_lambda = math.radians(longitude_b - longitude_a)
    inner = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi_a) * math.cos(phi_b) * math.sin(delta_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(inner)))


def _allen_2012(magnitude: float, hypocentral_km: float) -> float:
    distance = max(hypocentral_km, 1.0)
    near_source = -0.209 + 2.042 * math.exp(magnitude - 5.0)
    mmi = (
        2.085
        + 1.428 * magnitude
        - 1.402 * math.log(math.sqrt(distance**2 + near_source**2))
    )
    if distance > 50.0:
        mmi += 0.078 * math.log(distance / 50.0)
    return mmi


def _zhao_2006_intraslab(magnitude: float, depth_km: float, hypocentral_km: float) -> float:
    distance = max(hypocentral_km, 1.0)
    depth = min(depth_km, 125.0)  # Zhao acota el término de profundidad.
    ln_pga = (
        1.101 * magnitude
        - 0.00564 * distance
        - math.log(distance + 0.0055 * math.exp(1.080 * magnitude))
        + (0.01412 * (depth - 15.0) if depth >= 15.0 else 0.0)
        + 1.344  # Suelo firme (Vs30 de 300 a 600 m/s), el más común en ciudades.
        + 0.1392 * (magnitude - 6.5)
        + 0.1584 * (magnitude - 6.5) ** 2
        - 0.0529
        + 2.607
        - 0.528 * math.log(distance)
    )
    log_pga = ln_pga / math.log(10.0)  # cm/s²
    if log_pga <= 1.57:
        return 1.78 + 1.55 * log_pga
    return -1.60 + 3.70 * log_pga


def intensity_at(magnitude: float, depth_km: float | None, distance_km: float) -> float:
    """MMI esperada a ``distance_km`` del epicentro, entre 1 y 12."""

    depth = DEFAULT_DEPTH_KM if depth_km is None or depth_km < 0 else depth_km
    hypocentral = math.hypot(distance_km, depth)
    weight = min(
        1.0,
        max(0.0, (depth - CRUSTAL_UNTIL_KM) / (INTRASLAB_FROM_KM - CRUSTAL_UNTIL_KM)),
    )
    mmi = 0.0
    if weight < 1.0:
        mmi += (1.0 - weight) * _allen_2012(magnitude, hypocentral)
    if weight > 0.0:
        mmi += weight * _zhao_2006_intraslab(magnitude, depth, hypocentral)
    return min(12.0, max(1.0, mmi))


def radius_km(magnitude: float, depth_km: float | None, intensity: float) -> float | None:
    """Distancia epicentral hasta donde se espera al menos ``intensity``.

    ``None`` cuando ni siquiera sobre el epicentro se alcanza. La intensidad
    baja siempre con la distancia, así que basta una bisección.
    """

    if intensity_at(magnitude, depth_km, 0.0) < intensity:
        return None
    if intensity_at(magnitude, depth_km, MAX_RADIUS_KM) >= intensity:
        return MAX_RADIUS_KM
    low, high = 0.0, MAX_RADIUS_KM
    for _ in range(40):
        middle = (low + high) / 2
        if intensity_at(magnitude, depth_km, middle) >= intensity:
            low = middle
        else:
            high = middle
    return low


def intensity_for_place(
    magnitude: float,
    depth_km: float | None,
    epicenter_latitude: float,
    epicenter_longitude: float,
    latitude: float,
    longitude: float,
) -> float:
    distance = haversine_km(epicenter_latitude, epicenter_longitude, latitude, longitude)
    return intensity_at(magnitude, depth_km, distance)


def roman(intensity: float) -> str:
    return _ROMAN[min(12, max(1, int(intensity + 0.5))) - 1]


def describe(intensity: float) -> str:
    """Nombre de la sacudida percibida, como en los mapas del USGS."""

    level = min(12, max(1, int(intensity + 0.5)))
    if level <= 1:
        return "no sentido"
    if level <= 3:
        return "débil"
    return {4: "ligero", 5: "moderado", 6: "fuerte", 7: "muy fuerte", 8: "severo", 9: "violento"}.get(
        level, "extremo"
    )
