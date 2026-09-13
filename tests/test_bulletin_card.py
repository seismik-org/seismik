from __future__ import annotations

import re
from datetime import datetime, timezone
from io import BytesIO
from typing import Any

import pytest
from PIL import Image, ImageDraw

from integrations.bulletin_card import (
    LAND,
    OFFICIAL,
    _font,
    _render_map,
    _wrap,
    bulletin_facts,
    describe_position,
    is_withdrawn,
    render_bulletin_card,
    summary_paragraphs,
    translate_place,
    when_text,
)

GENERATED = datetime(2026, 9, 10, 11, 30, tzinfo=timezone.utc)


def usgs_event(**overrides: Any) -> dict[str, Any]:
    """Mismos campos que `eew.models.OfficialReportUpdate.to_dict()`."""
    report = {
        "source_id": "usgs_global",
        "agency": "United States Geological Survey (USGS)",
        "jurisdiction": "Global fallback",
        "official_event_id": "us7000th16",
        "origin_time": "2026-09-10T11:16:00Z",
        "updated_at": "2026-09-10T11:40:00Z",
        "latitude": 52.5,
        "longitude": 160.2,
        "depth_km": 58.0,
        "magnitude": 6.4,
        "magnitude_type": "mww",
        "place": "96 km ESE of Petropavlovsk-Kamchatsky, Russia",
        "review_status": "reviewed",
        "official_url": "https://earthquake.usgs.gov/earthquakes/eventpage/us7000th16",
        "tsunami": False,
    }
    report.update(overrides)
    return {
        "event_id": "official-us7000th16",
        "candidate_event_id": "candidate-1",
        "type": "official_report_update",
        "status": "official_report_available",
        "preferred_report": report,
        "reports": [report],
    }


def test_usgs_places_are_translated() -> None:
    assert translate_place("96 km ESE of Petropavlovsk-Kamchatsky, Russia") == (
        "A 96 km al ESE de Petropavlovsk-Kamchatsky, Rusia"
    )
    assert translate_place("12 km SSW of Tobelo, Indonesia") == "A 12 km al SSO de Tobelo, Indonesia"
    assert translate_place("Región de Nariño, Colombia") == "Región de Nariño, Colombia"


def test_the_position_is_described_from_the_nearest_city() -> None:
    text = describe_position(52.5, 160.2)

    assert text is not None
    assert re.fullmatch(r"a \d+ km al ESE de Petropavlovsk-Kamchatsky \(Rusia\)", text)


def test_far_from_any_town_the_position_names_the_sea() -> None:
    """Sin ciudad habitada a menos de 600 km, «a 1140 km de una base antártica» no orienta."""
    text = describe_position(-57.8, -25.4)

    assert text is not None
    assert re.fullmatch(r"en (el|la) \S.+", text), text


def test_the_agency_distance_is_not_contradicted_by_our_own() -> None:
    facts = bulletin_facts(usgs_event())

    assert facts.title == "A 96 km al ESE de Petropavlovsk-Kamchatsky, Rusia"
    assert facts.relative == "a 96 km al ESE de Petropavlovsk-Kamchatsky, Rusia"


def test_long_words_break_at_their_hyphen() -> None:
    image = Image.new("RGB", (10, 10))
    draw = ImageDraw.Draw(image)
    font = _font(23, 600)
    width = draw.textlength("Petropavlovsk-", font=font) + 4

    assert _wrap(draw, "Petropavlovsk-Kamchatsky", font, width, 3) == ["Petropavlovsk-", "Kamchatsky"]


def test_urls_break_after_a_slash() -> None:
    image = Image.new("RGB", (10, 10))
    draw = ImageDraw.Draw(image)
    font = _font(16, 500)
    url = "sgc.gov.co/detallesismo/SGC2026rkt4p1/resumen"
    width = draw.textlength("sgc.gov.co/detallesismo/", font=font) + 4

    lines = _wrap(draw, url, font, width, 3)

    assert "".join(lines) == url, "sin espacios ni letras perdidas"
    assert all(line.endswith("/") for line in lines[:-1])


def test_a_ring_around_the_pole_does_not_paint_a_band_of_land_across_the_ocean() -> None:
    """La Antártida cerrada con una recta pintaba de tierra el fondo del mapa del Atlántico Sur."""
    facts = bulletin_facts(usgs_event(latitude=-57.8, longitude=-25.4, place=None))

    image = _render_map((524, 584), facts, OFFICIAL)

    for y in (480, 540, 575):
        assert image.getpixel((140, y)) != LAND


def test_facts_name_the_agency_in_spanish_and_give_the_time_in_colombia() -> None:
    facts = bulletin_facts(usgs_event())

    assert (facts.agency_short, facts.agency_long) == ("USGS", "Servicio Geológico de Estados Unidos (USGS)")
    assert not facts.preliminary
    assert when_text(facts) == "10 de septiembre de 2026, 11:16 UTC (06:16 a. m. hora de Colombia)"


def test_colombia_time_names_the_day_when_it_is_not_the_utc_date() -> None:
    facts = bulletin_facts(usgs_event(origin_time="2026-09-10T02:05:00Z"))

    assert "(09:05 p. m. del 9 de septiembre, hora de Colombia)" in when_text(facts)


def test_automatic_reports_are_preliminary_and_deleted_ones_are_withdrawn() -> None:
    assert bulletin_facts(usgs_event(review_status="automatic")).preliminary
    assert is_withdrawn(usgs_event(review_status="deleted"))
    assert not is_withdrawn(usgs_event())


def test_the_summary_only_states_what_the_report_says() -> None:
    text = " ".join(summary_paragraphs(bulletin_facts(usgs_event())))

    assert "magnitud 6.4" in text and "58 km de profundidad" in text
    assert "no marca riesgo de tsunami" in text
    assert "daño" not in text.lower(), "los reportes no traen daños: no se afirman"
    unknown = " ".join(summary_paragraphs(bulletin_facts(usgs_event(tsunami=None))))
    assert "tsunami" not in unknown


@pytest.mark.parametrize(
    "event",
    [
        usgs_event(),
        usgs_event(review_status="automatic", place="South Sandwich Islands region",
                   latitude=-57.8, longitude=-25.4, depth_km=None, tsunami=None),
        usgs_event(latitude=-17.9, longitude=179.9, place=None, tsunami=True),
        usgs_event(source_id="sgc_colombia", agency="Servicio Geológico Colombiano (SGC)",
                   latitude=4.6, longitude=-74.1, place="Bogotá, Colombia", magnitude=None,
                   official_url="https://www.sgc.gov.co/detallesismo/SGC2026abcd/resumen"),
        usgs_event(latitude=None, longitude=None, origin_time=None),
    ],
    ids=["oficial", "preliminar-oceano", "antimeridiano", "sin-magnitud", "sin-coordenadas"],
)
def test_the_card_renders_for_every_shape_of_report(event: dict[str, Any]) -> None:
    png = render_bulletin_card(event, generated_at=GENERATED)

    image = Image.open(BytesIO(png))
    assert image.format == "PNG"
    assert image.size == (1080, 1350)
    assert len(png) < 5_000_000, "límite de imágenes de X"
