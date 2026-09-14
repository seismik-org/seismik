"""Perímetro de sacudida: intensidad esperada según magnitud, profundidad y distancia."""
from __future__ import annotations

import pytest

from api.felt_area import (
    FELT,
    MAX_RADIUS_KM,
    STRONG,
    _allen_2012,
    describe,
    intensity_at,
    intensity_for_place,
    radius_km,
    roman,
)

# mobile_app/test/felt_area_test.dart comprueba los mismos valores: el mapa de
# la app y la alarma del servidor deben dibujar el mismo perímetro.
REFERENCE_INTENSITIES = [
    (4.0, 150.0, 40.0, 3.066),
    (4.0, 150.0, 290.0, 1.652),
    (4.0, 10.0, 0.0, 4.567),
    (6.0, 10.0, 100.0, 4.242),
    (7.0, 10.0, 281.0, 4.308),
    (6.0, 55.0, 0.0, 5.367),
    (4.5, None, 0.0, 5.275),
]
REFERENCE_RADII = [
    (4.0, 10.0, FELT, 28.93),
    (4.0, 150.0, FELT, 60.28),
    (6.0, 10.0, STRONG, 25.19),
    (7.0, 10.0, STRONG, 76.28),
]


@pytest.mark.parametrize(("magnitude", "depth", "distance", "expected"), REFERENCE_INTENSITIES)
def test_intensity_matches_the_shared_reference(
    magnitude: float, depth: float | None, distance: float, expected: float
) -> None:
    assert intensity_at(magnitude, depth, distance) == pytest.approx(expected, abs=0.001)


@pytest.mark.parametrize(("magnitude", "depth", "intensity", "expected"), REFERENCE_RADII)
def test_radius_matches_the_shared_reference(
    magnitude: float, depth: float, intensity: float, expected: float
) -> None:
    assert radius_km(magnitude, depth, intensity) == pytest.approx(expected, abs=0.01)


def test_a_quake_nobody_feels_has_no_perimeter_and_a_huge_one_is_capped() -> None:
    assert radius_km(2.5, 10.0, FELT) is None
    assert radius_km(8.5, 30.0, FELT) == MAX_RADIUS_KM


@pytest.mark.parametrize("depth", [None, 10.0, 45.0, 150.0])
def test_intensity_never_grows_with_distance(depth: float | None) -> None:
    values = [intensity_at(6.0, depth, float(distance)) for distance in range(0, 1_000, 5)]
    assert all(later <= earlier for earlier, later in zip(values, values[1:]))


def test_a_small_bucaramanga_nest_quake_is_felt_nearby_but_not_in_bogota() -> None:
    """Los Santos, M4.0 a 150 km de profundidad, se sintió en Bucaramanga."""

    los_santos = (6.80, -73.10)
    assert intensity_for_place(4.0, 150.0, *los_santos, 7.119, -73.123) >= FELT
    assert intensity_for_place(4.0, 150.0, *los_santos, 4.711, -74.072) < FELT
    # El modelo de sismos someros solo no lo habría sentido en ninguna parte.
    assert _allen_2012(4.0, 150.0) < 1.5


@pytest.mark.parametrize("magnitude", [4.0, 5.0, 6.0, 7.0])
def test_the_crustal_and_intraslab_models_join_without_a_jump(magnitude: float) -> None:
    for boundary in (40.0, 70.0):
        below = intensity_at(magnitude, boundary - 0.1, 0.0)
        above = intensity_at(magnitude, boundary + 0.1, 0.0)
        assert below == pytest.approx(above, abs=0.05)


def test_intensity_names_follow_the_perceived_shaking_scale() -> None:
    assert roman(3.066) == "III"
    assert roman(12.4) == "XII"
    assert describe(1.0) == "no sentido"
    assert describe(2.6) == "débil"
    assert describe(6.2) == "fuerte"
    assert describe(11.0) == "extremo"
