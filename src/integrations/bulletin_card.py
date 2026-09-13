"""Imagen del boletín sísmico que acompaña cada publicación en X.

Todo sale del reporte oficial. Los contornos son de Natural Earth (dominio
público, ver tools/build_bulletin_geodata.py) y el texto sólo afirma lo que el
reporte dice: no menciona daños ni víctimas, porque los reportes no los traen.
"""
from __future__ import annotations

import gzip
import io
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps

ASSETS = Path(__file__).resolve().parent / "assets"
FONT_PATH = ASSETS / "fonts" / "Montserrat[wght].ttf"
LOGO_PATH = ASSETS / "seismik_logo.png"
GEO_PATH = ASSETS / "bulletin_geo.json.gz"

WIDTH, HEIGHT = 1080, 1350
MARGIN = 36
COLOMBIA = timezone(timedelta(hours=-5))
EARTH_RADIUS_KM = 6371.0088
# Una ciudad sirve de referencia si está habitada y a menos de esta distancia;
# más lejos, «a 1140 km de una base antártica» no orienta a nadie.
REFERENCE_MAX_KM = 600.0
REFERENCE_MIN_POPULATION = 1_000
MONTHS = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)
COMPASS = ("N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSO", "SO", "OSO", "O", "ONO", "NO", "NNO")
USGS_DIRECTIONS = dict(
    zip(("N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"), COMPASS)
)
USGS_PLACE = re.compile(
    r"^(?P<km>\d+(?:\.\d+)?)\s*km\s+(?P<direction>[NSEW]{1,3})\s+of\s+(?P<reference>.+)$", re.IGNORECASE
)
# Estados de revisión de los catálogos (USGS `status`, GeoNet `quality`).
PRELIMINARY_STATUSES = frozenset({"automatic", "preliminary"})
WITHDRAWN_STATUSES = frozenset({"deleted"})

# Nombre corto y nombre en español de cada fuente de official_sources.json.
AGENCIES: dict[str, tuple[str, str]] = {
    "usgs_global": ("USGS", "Servicio Geológico de Estados Unidos (USGS)"),
    "ingv_italy": ("INGV", "Instituto Nacional de Geofísica y Vulcanología de Italia (INGV)"),
    "geonet_new_zealand": ("GeoNet", "GeoNet / GNS Science (Nueva Zelanda)"),
    "bmkg_indonesia": ("BMKG", "Agencia de Meteorología, Climatología y Geofísica de Indonesia (BMKG)"),
    "jma_japan": ("JMA", "Agencia Meteorológica de Japón (JMA)"),
    "sgc_colombia": ("SGC", "Servicio Geológico Colombiano (SGC)"),
    "igp_peru": ("IGP", "Instituto Geofísico del Perú (IGP)"),
}

Rgb = tuple[int, int, int]
Box = tuple[float, float, float, float]
Ring = list[list[float]]
BG_TOP: Rgb = (5, 20, 44)
BG_BOTTOM: Rgb = (11, 42, 86)
PANEL: Rgb = (9, 29, 58)
PANEL_EDGE: Rgb = (38, 78, 128)
WHITE: Rgb = (255, 255, 255)
MUTED: Rgb = (172, 194, 224)
LABEL: Rgb = (122, 178, 255)
OCEAN: Rgb = (15, 50, 92)
LAND: Rgb = (40, 86, 80)
BORDERS: Rgb = (92, 138, 140)
SHADOW: Rgb = (3, 12, 28)


@dataclass(frozen=True)
class Palette:
    panel: tuple[Rgb, Rgb]
    accent: Rgb
    title: Rgb


OFFICIAL = Palette(((206, 28, 50), (118, 12, 30)), (255, 72, 72), LABEL)
PRELIMINARY = Palette(((236, 146, 40), (150, 80, 16)), (255, 168, 56), (255, 184, 84))


@dataclass(frozen=True)
class BulletinFacts:
    event_id: str
    preliminary: bool
    magnitude: float | None
    magnitude_type: str
    title: str
    latitude: float | None
    longitude: float | None
    relative: str | None
    depth_km: float | None
    origin_utc: datetime | None
    agency_short: str
    agency_long: str
    official_url: str
    tsunami: bool | None


# --- Geografía ----------------------------------------------------------------


def _report(event: dict[str, Any]) -> dict[str, Any]:
    report = event.get("preferred_report") or event.get("report") or {}
    return report if isinstance(report, dict) else {}


def _float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


@lru_cache(maxsize=1)
def load_geo() -> dict[str, Any]:
    with gzip.open(GEO_PATH, "rt", encoding="utf-8") as handle:
        data: dict[str, Any] = json.load(handle)
    return data


@lru_cache(maxsize=1)
def _country_names() -> tuple[dict[str, str], dict[str, str]]:
    by_iso: dict[str, str] = {}
    by_english: dict[str, str] = {}
    for country in load_geo()["countries"]:
        if country["iso"]:
            by_iso.setdefault(country["iso"], country["name"])
        by_english[country["name_en"].lower()] = country["name"]
    return by_iso, by_english


@lru_cache(maxsize=1)
def _reference_places() -> list[list[Any]]:
    return [place for place in load_geo()["places"] if place[4] >= REFERENCE_MIN_POPULATION]


def _bbox(ring: Ring) -> Box:
    xs = [point[0] for point in ring]
    ys = [point[1] for point in ring]
    return min(xs), min(ys), max(xs), max(ys)


@lru_cache(maxsize=1)
def _indexed_areas() -> tuple[list[tuple[Box, Ring, str]], list[tuple[Box, Ring, str]]]:
    countries = [(_bbox(ring), ring, c["name"]) for c in load_geo()["countries"] for ring in c["rings"]]
    seas = [(_bbox(ring), ring, s["name"]) for s in load_geo()["seas"] for ring in s["rings"]]
    return countries, seas


def _contains(ring: Ring, lon: float, lat: float) -> bool:
    inside = False
    previous = ring[-1]
    for point in ring:
        (x1, y1), (x2, y2) = point[:2], previous[:2]
        if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
            inside = not inside
        previous = point
    return inside


def _area_at(areas: list[tuple[Box, Ring, str]], lat: float, lon: float) -> str | None:
    matches = [
        ((box[2] - box[0]) * (box[3] - box[1]), name)
        for box, ring, name in areas
        if box[0] <= lon <= box[2] and box[1] <= lat <= box[3] and _contains(ring, lon, lat)
    ]
    return min(matches)[1] if matches else None


def country_at(latitude: float, longitude: float) -> str | None:
    return _area_at(_indexed_areas()[0], latitude, longitude)


@lru_cache(maxsize=1)
def _country_codes() -> list[tuple[Box, Ring, str]]:
    return [(_bbox(ring), ring, c["iso"]) for c in load_geo()["countries"] if c["iso"] for ring in c["rings"]]


def country_code_at(latitude: float, longitude: float) -> str | None:
    """Código ISO del país que contiene el punto; None en el mar."""
    return _area_at(_country_codes(), latitude, longitude)


def sea_at(latitude: float, longitude: float) -> str | None:
    """El mar u océano más específico que contiene el punto."""
    return _area_at(_indexed_areas()[1], latitude, longitude)


def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    half = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(half)))


def _bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2, delta = math.radians(lat1), math.radians(lat2), math.radians(lon2 - lon1)
    x = math.sin(delta) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(delta)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def _nearest_place(latitude: float, longitude: float) -> tuple[list[Any], float] | None:
    places = _reference_places()
    if not places:
        return None
    best = min(places, key=lambda place: _distance_km(latitude, longitude, place[3], place[2]))
    return best, _distance_km(latitude, longitude, best[3], best[2])


def _in_sea(name: str) -> str:
    article = "la" if name.split(" ", 1)[0].lower() in {"bahía", "ensenada", "cuenca"} else "el"
    return f"en {article} {name}"


def describe_position(latitude: float, longitude: float) -> str | None:
    """«a 125 km al ESE de Petropavlovsk-Kamchatsky (Rusia)», «en Chile» o «en el Mar de Escocia»."""
    found = _nearest_place(latitude, longitude)
    if found is not None and found[1] <= REFERENCE_MAX_KM:
        (name, iso, place_lon, place_lat, *_rest), distance = found
        country = _country_names()[0].get(iso)
        reference = f"{name} ({country})" if country and country != name else str(name)
        if distance < 5:
            return f"en {reference}"
        km = round(distance) if distance < 20 else int(5 * round(distance / 5))
        direction = COMPASS[int((_bearing(place_lat, place_lon, latitude, longitude) + 11.25) // 22.5) % 16]
        return f"a {km} km al {direction} de {reference}"
    country = country_at(latitude, longitude)
    if country:
        return f"en {country}"
    sea = sea_at(latitude, longitude)
    return _in_sea(sea) if sea else None


def _spanish_country_suffix(text: str) -> str:
    head, separator, tail = text.rpartition(", ")
    spanish = _country_names()[1].get(tail.lower()) if separator else None
    return f"{head}, {spanish}" if spanish else text


def translate_place(place: str) -> str:
    """Traduce el formato del USGS («96 km ESE of X, Russia»); el resto queda igual."""
    text = " ".join(place.split())
    match = USGS_PLACE.match(text)
    if match is None:
        return _spanish_country_suffix(text)
    km = round(float(match["km"]))
    direction = USGS_DIRECTIONS.get(match["direction"].upper(), match["direction"].upper())
    return f"A {km} km al {direction} de {_spanish_country_suffix(match['reference'])}"


def agency_names(report: dict[str, Any]) -> tuple[str, str]:
    known = AGENCIES.get(str(report.get("source_id") or ""))
    if known:
        return known
    agency = str(report.get("agency") or report.get("source") or "Fuente oficial")
    acronym = re.search(r"\(([^)]+)\)\s*$", agency)
    return (acronym.group(1) if acronym else agency), agency


def is_withdrawn(event: dict[str, Any]) -> bool:
    """La agencia retiró el evento (p. ej. USGS `status: deleted`)."""
    return str(_report(event).get("review_status") or "").strip().lower() in WITHDRAWN_STATUSES


def bulletin_facts(event: dict[str, Any]) -> BulletinFacts:
    report = _report(event)
    latitude, longitude = _float(report.get("latitude")), _float(report.get("longitude"))
    place = " ".join(str(report.get("place") or report.get("title") or "").split())
    title = translate_place(place) if place else ""
    if USGS_PLACE.match(place):
        # La agencia ya da la distancia a su ciudad de referencia: repetir la
        # propia, con otra ciudad y otra cifra, sólo confundiría.
        relative: str | None = title[:1].lower() + title[1:]
    elif latitude is not None and longitude is not None:
        relative = describe_position(latitude, longitude)
    else:
        relative = None
    if not title:
        title = relative[:1].upper() + relative[1:] if relative else "Ubicación en evaluación"
    short, long = agency_names(report)
    tsunami = report.get("tsunami")
    return BulletinFacts(
        event_id=str(report.get("official_event_id") or event.get("event_id") or ""),
        preliminary=str(report.get("review_status") or "").strip().lower() in PRELIMINARY_STATUSES,
        magnitude=_float(report.get("magnitude") or event.get("magnitude")),
        magnitude_type=str(report.get("magnitude_type") or ""),
        title=title,
        latitude=latitude,
        longitude=longitude,
        relative=relative,
        depth_km=_float(report.get("depth_km")),
        origin_utc=_parse_time(report.get("origin_time") or event.get("occurred_at")),
        agency_short=short,
        agency_long=long,
        official_url=str(report.get("official_url") or ""),
        tsunami=tsunami if isinstance(tsunami, bool) else None,
    )


# --- Formato ------------------------------------------------------------------


def spanish_date(moment: datetime) -> str:
    return f"{moment.day} de {MONTHS[moment.month - 1]} de {moment.year}"


def _clock(moment: datetime) -> str:
    hour = moment.hour % 12 or 12
    return f"{hour:02d}:{moment.minute:02d} {'a. m.' if moment.hour < 12 else 'p. m.'}"


def colombia_time(moment: datetime) -> str:
    """La audiencia de Seismik está en Colombia (UTC−5, sin horario de verano)."""
    local, utc = moment.astimezone(COLOMBIA), moment.astimezone(timezone.utc)
    if local.date() == utc.date():
        return f"{_clock(local)} hora de Colombia"
    return f"{_clock(local)} del {local.day} de {MONTHS[local.month - 1]}, hora de Colombia"


def when_text(facts: BulletinFacts) -> str:
    if facts.origin_utc is None:
        return "Hora en evaluación"
    utc = facts.origin_utc.astimezone(timezone.utc)
    return f"{spanish_date(utc)}, {utc:%H:%M} UTC ({colombia_time(utc)})"


def _depth_text(depth_km: float) -> str:
    return f"{depth_km:.0f} km" if depth_km >= 10 else f"{depth_km:.1f} km"


def _coordinates_text(latitude: float, longitude: float) -> str:
    return (
        f"{abs(latitude):.2f}° {'N' if latitude >= 0 else 'S'}, "
        f"{abs(longitude):.2f}° {'E' if longitude >= 0 else 'O'}"
    )


def summary_paragraphs(facts: BulletinFacts) -> list[str]:
    paragraphs = []
    if facts.preliminary:
        paragraphs.append(
            f"Este es un reporte preliminar de {facts.agency_short}. La magnitud, la ubicación y "
            "los demás parámetros pueden ajustarse a medida que se analicen más datos."
        )
    else:
        magnitude = f" de magnitud {facts.magnitude:.1f}" if facts.magnitude is not None else ""
        where = f", {facts.relative}" if facts.relative else ""
        depth = f", a {_depth_text(facts.depth_km)} de profundidad" if facts.depth_km is not None else ""
        paragraphs.append(f"Según el reporte de {facts.agency_short}, se registró un sismo{magnitude}{where}{depth}.")
    if facts.tsunami is True:
        paragraphs.append("La fuente marca posible riesgo de tsunami: sigue las indicaciones de las autoridades locales.")
    elif facts.tsunami is False:
        paragraphs.append("La fuente no marca riesgo de tsunami.")
    paragraphs.append("Seismik seguirá la evolución del evento en las fuentes oficiales.")
    return paragraphs


# --- Texto --------------------------------------------------------------------


@lru_cache(maxsize=64)
def _font(size: int, weight: int = 400) -> ImageFont.FreeTypeFont:
    font = ImageFont.truetype(str(FONT_PATH), size)
    font.set_variation_by_axes([weight])
    return font


def _tracked(draw: ImageDraw.ImageDraw, xy: tuple[float, float], text: str, font: ImageFont.FreeTypeFont,
             fill: Rgb, spacing: float = 2.0) -> None:
    x, y = xy
    for char in text:
        draw.text((x, y), char, font=font, fill=fill)
        x += draw.textlength(char, font=font) + spacing


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, width: float, max_lines: int) -> list[str]:
    # Cada pieza lleva si va separada por espacio de la anterior: una palabra
    # larga (un nombre compuesto, una URL) se parte primero tras sus guiones y
    # barras, y sólo si no alcanza, por letras.
    pieces: list[tuple[str, bool]] = []
    for word in text.split():
        parts = re.findall(r"[^-/]+[-/]|[^-/]+$|[-/]", word) if draw.textlength(word, font=font) > width else [word]
        for index, part in enumerate(parts):
            spaced = index == 0
            while len(part) > 1 and draw.textlength(part, font=font) > width:
                cut = len(part) - 1
                while cut > 1 and draw.textlength(part[:cut], font=font) > width:
                    cut -= 1
                pieces.append((part[:cut], spaced))
                part, spaced = part[cut:], False
            pieces.append((part, spaced))
    lines: list[str] = []
    current = ""
    for piece, spaced in pieces:
        candidate = f"{current}{' ' if spaced and current else ''}{piece}"
        if draw.textlength(candidate, font=font) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = piece
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        last = lines[max_lines - 1]
        while last and draw.textlength(last + "…", font=font) > width:
            last = last[:-1]
        lines = lines[: max_lines - 1] + [last.rstrip() + "…"]
    return lines


def _fit(draw: ImageDraw.ImageDraw, text: str, width: float, max_lines: int, sizes: tuple[int, ...],
         weight: int) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    """El tamaño más grande con el que el texto cabe entero en `max_lines`."""
    for size in sizes:
        font = _font(size, weight)
        lines = _wrap(draw, text, font, width, max_lines=10_000)
        if len(lines) <= max_lines:
            return font, lines
    font = _font(sizes[-1], weight)
    return font, _wrap(draw, text, font, width, max_lines)


def _shadow_text(draw: ImageDraw.ImageDraw, xy: tuple[float, float], text: str, font: ImageFont.FreeTypeFont,
                 fill: Rgb, anchor: str = "la") -> None:
    draw.text((xy[0] + 1, xy[1] + 2), text, font=font, fill=SHADOW, anchor=anchor)
    draw.text(xy, text, font=font, fill=fill, anchor=anchor)


# --- Piezas gráficas ------------------------------------------------------------


def _background() -> Image.Image:
    gradient = Image.linear_gradient("L").resize((WIDTH, HEIGHT))
    return ImageOps.colorize(gradient, BG_TOP, BG_BOTTOM).convert("RGB")


def _rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius, fill=255)
    return mask


def _gradient_panel(canvas: Image.Image, box: tuple[int, int, int, int], colors: tuple[Rgb, Rgb], radius: int = 22) -> None:
    x0, y0, x1, y1 = box
    size = (x1 - x0, y1 - y0)
    gradient = Image.linear_gradient("L").rotate(90, expand=True).resize(size)
    canvas.paste(ImageOps.colorize(gradient, colors[0], colors[1]).convert("RGB"), (x0, y0), _rounded_mask(size, radius))


def _panel(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int]) -> None:
    draw.rounded_rectangle(box, 22, fill=PANEL, outline=PANEL_EDGE, width=2)


def _icon(draw: ImageDraw.ImageDraw, center: tuple[float, float], kind: str, color: Rgb) -> None:
    cx, cy = center
    draw.ellipse((cx - 30, cy - 30, cx + 30, cy + 30), outline=PANEL_EDGE, width=3)
    if kind == "pin":
        draw.ellipse((cx - 10, cy - 18, cx + 10, cy + 2), fill=color)
        draw.polygon([(cx - 9, cy - 5), (cx + 9, cy - 5), (cx, cy + 17)], fill=color)
        draw.ellipse((cx - 4, cy - 12, cx + 4, cy - 4), fill=PANEL)
    elif kind == "layers":
        for dy in (8, 0, -8):
            draw.polygon(
                [(cx - 15, cy + dy), (cx, cy + dy - 7), (cx + 15, cy + dy), (cx, cy + dy + 7)],
                fill=PANEL, outline=color, width=2,
            )
    elif kind == "wave":
        draw.line(
            [(cx - 17, cy), (cx - 9, cy), (cx - 5, cy - 13), (cx + 1, cy + 13), (cx + 6, cy - 7), (cx + 9, cy), (cx + 17, cy)],
            fill=color, width=3, joint="curve",
        )
    elif kind == "doc":
        draw.rounded_rectangle((cx - 11, cy - 15, cx + 11, cy + 15), 3, outline=color, width=2)
        for dy in (-6, 0, 6):
            draw.line([(cx - 6, cy + dy), (cx + 6, cy + dy)], fill=color, width=2)
    elif kind == "info":
        draw.text((cx, cy), "i", font=_font(34, 800), fill=color, anchor="mm")


# --- Mapa ---------------------------------------------------------------------


def _unwrap(ring: Ring, center_lon: float) -> list[tuple[float, float]]:
    """Longitudes relativas y continuas.

    Un anillo que cruza el lado opuesto del globo queda entero a un lado en vez
    de trazar una franja sobre el mapa. Uno que rodea un polo (la Antártida) da
    la vuelta completa: se cierra por el polo, no con una recta que lo corte.
    """
    offsets: list[tuple[float, float]] = []
    previous: float | None = None
    for point in ring:
        lon, lat = point[0], point[1]
        offset = lon - center_lon
        offset = (offset + 180) % 360 - 180 if previous is None else previous + ((offset - previous + 180) % 360 - 180)
        previous = offset
        offsets.append((offset, lat))
    if len(offsets) > 2 and abs(offsets[-1][0] - offsets[0][0]) > 180:
        pole = -90.0 if sum(lat for _, lat in offsets) < 0 else 90.0
        offsets += [(offsets[-1][0], pole), (offsets[0][0], pole)]
    return offsets


class _Projection:
    """Equirrectangular local centrada en el epicentro, en kilómetros."""

    def __init__(self, width: int, height: int, latitude: float, longitude: float, span_km: float) -> None:
        self.width, self.height = width, height
        self.latitude, self.longitude = latitude, longitude
        self.pixels_per_km = width / span_km
        self.km_per_degree_lon = 111.32 * max(math.cos(math.radians(latitude)), 0.05)

    def _xy(self, delta_lon: float, lat: float) -> tuple[float, float]:
        return (
            self.width / 2 + delta_lon * self.km_per_degree_lon * self.pixels_per_km,
            self.height / 2 - (lat - self.latitude) * 110.57 * self.pixels_per_km,
        )

    def point(self, lon: float, lat: float) -> tuple[float, float]:
        return self._xy((lon - self.longitude + 180) % 360 - 180, lat)

    def ring(self, ring: Ring) -> list[tuple[float, float]]:
        return [self._xy(offset, lat) for offset, lat in _unwrap(ring, self.longitude)]

    def visible(self, xy: tuple[float, float], inset: float = 0.0) -> bool:
        return inset <= xy[0] <= self.width - inset and inset <= xy[1] <= self.height - inset


def _off_view(points: list[tuple[float, float]], width: float, height: float) -> bool:
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    return max(xs) < 0 or min(xs) > width or max(ys) < 0 or min(ys) > height


class _Labels:
    """Cajas ya ocupadas del mapa, más el círculo de los anillos del epicentro."""

    def __init__(self, width: int, height: int, rings: tuple[float, float, float]) -> None:
        self.width, self.height = width, height
        self.rings = rings
        self.boxes: list[Box] = []

    def fits(self, box: Box, *, over_rings: bool = False) -> bool:
        if box[0] < 8 or box[1] < 56 or box[2] > self.width - 8 or box[3] > self.height - 52:
            return False
        # Contra el círculo, no contra el cuadrado que lo contiene: con el
        # cuadrado no cabía el nombre de una ciudad a 130 px del epicentro.
        cx, cy, radius = self.rings
        nearest_x, nearest_y = min(max(cx, box[0]), box[2]), min(max(cy, box[1]), box[3])
        if not over_rings and (nearest_x - cx) ** 2 + (nearest_y - cy) ** 2 < radius ** 2:
            return False
        return not any(box[0] < b[2] and box[2] > b[0] and box[1] < b[3] and box[3] > b[1] for b in self.boxes)


def _covered_by(image: Image.Image, box: Box, color: Rgb, share: float) -> bool:
    """Si al menos `share` de la caja es de `color` (tierra o mar), sin etiquetas encima."""
    left, top, right, bottom = (int(value) for value in box)
    crop = image.crop((left, top, right, bottom))
    difference = ImageChops.difference(crop, Image.new("RGB", crop.size, color)).convert("L")
    matching = difference.point(lambda value: 255 if value <= 8 else 0).histogram()[255]
    return matching >= share * crop.width * crop.height


def map_span_km(latitude: float, longitude: float) -> float:
    """Ancho del mapa: lo justo para que se vea la ciudad de referencia."""
    found = _nearest_place(latitude, longitude)
    if found is None or found[1] > 1300:
        return 2600.0
    return max(500.0, min(2600.0, found[1] * 2.8))


def _label_variants(name: str) -> list[list[str]]:
    """El nombre en una línea y, si no cabe, partido por su guion o su primer espacio."""
    split = re.match(r"^(.+?-)(.+)$", name) or re.match(r"^(\S+)\s+(.+)$", name)
    return [[name], [split.group(1), split.group(2)]] if split else [[name]]


def _draw_cities(draw: ImageDraw.ImageDraw, projection: _Projection, labels: _Labels,
                 latitude: float, longitude: float) -> tuple[float, float] | None:
    """Ciudad de referencia y hasta tres más; devuelve dónde quedó la de referencia."""
    nearest = _nearest_place(latitude, longitude)
    reference = nearest[0] if nearest else None
    candidates = sorted(
        (place for place in _reference_places() if projection.visible(projection.point(place[2], place[3]), 16)),
        key=lambda place: (place is not reference, -place[4]),
    )
    font = _font(19, 600)
    line_height = 24
    anchor_xy: tuple[float, float] | None = None
    shown = 0
    for place in candidates:
        if shown >= 4:
            break
        x, y = projection.point(place[2], place[3])
        is_reference = place is reference
        if is_reference:
            # El punto de la ciudad de referencia se reserva siempre, para que
            # el nombre del país no quede encima.
            anchor_xy = (x, y)
            labels.boxes.append((x - 8, y - 8, x + 8, y + 8))
        chosen: tuple[Box, str, list[str]] | None = None
        # La ciudad de referencia puede quedar dentro de los anillos (Bogotá a
        # 35 km del epicentro): su nombre va encima de ellos antes que omitirlo.
        for over_rings in (False, True) if is_reference else (False,):
            for lines in _label_variants(str(place[0])):
                width = max(draw.textlength(line, font=font) for line in lines)
                height = line_height * len(lines)
                options: tuple[tuple[Box, str], ...] = (
                    ((x + 10, y - height / 2, x + 16 + width, y + height / 2), "l"),
                    ((x - 16 - width, y - height / 2, x - 10, y + height / 2), "r"),
                    ((x - width / 2 - 3, y - 10 - height, x + width / 2 + 3, y - 8), "m"),
                    ((x - width / 2 - 3, y + 8, x + width / 2 + 3, y + 10 + height), "m"),
                )
                chosen = next(
                    ((box, align, lines) for box, align in options if labels.fits(box, over_rings=over_rings)), None
                )
                if chosen is not None:
                    break
            if chosen is not None:
                break
        if chosen is None:
            if is_reference:
                draw.ellipse((x - 6, y - 6, x + 6, y + 6), fill=WHITE, outline=SHADOW, width=2)
            continue
        box, align, lines = chosen
        if not is_reference:
            labels.boxes.append((x - 7, y - 7, x + 7, y + 7))
        labels.boxes.append(box)
        draw.ellipse((x - 6, y - 6, x + 6, y + 6), fill=WHITE, outline=SHADOW, width=2)
        text_x = {"l": box[0] + 3, "r": box[2] - 3, "m": (box[0] + box[2]) / 2}[align]
        for index, line in enumerate(lines):
            _shadow_text(draw, (text_x, box[1] + line_height * (index + 0.5)), line, font, WHITE, anchor=f"{align}m")
        shown += 1
    return anchor_xy


def _place_area_label(image: Image.Image, draw: ImageDraw.ImageDraw, labels: _Labels, name: str,
                      font: ImageFont.FreeTypeFont, fill: Rgb, near: tuple[float, float], under: Rgb, share: float) -> None:
    """Etiqueta un país o un mar donde de verdad hay tierra o agua, lo más cerca posible de `near`."""
    lines = name.split(" ", 1) if len(name) > 16 and " " in name else [name]
    line_height = int(font.size) + 6
    width = max(draw.textlength(line, font=font) for line in lines) + 14
    height = line_height * len(lines) + 8
    nx, ny = near
    centers = sorted(
        ((gx - nx) ** 2 + (gy - ny) ** 2, gx, gy)
        for gx in range(int(width / 2) + 8, image.width - int(width / 2) - 8, 20)
        for gy in range(int(height / 2) + 56, image.height - int(height / 2) - 52, 20)
    )
    for _distance, gx, gy in centers[:500]:
        box = (gx - width / 2, gy - height / 2, gx + width / 2, gy + height / 2)
        if labels.fits(box) and _covered_by(image, box, under, share):
            labels.boxes.append(box)
            for index, line in enumerate(lines):
                _shadow_text(draw, (gx, box[1] + 4 + line_height * (index + 0.5)), line, font, fill, anchor="mm")
            return


def _draw_north_arrow(draw: ImageDraw.ImageDraw, top: tuple[float, float]) -> None:
    x, y = top
    draw.text((x, y), "N", font=_font(19, 700), fill=WHITE, anchor="mt")
    draw.polygon([(x, y + 26), (x - 10, y + 50), (x, y + 43), (x + 10, y + 50)], fill=WHITE)


def _draw_scale_bar(draw: ImageDraw.ImageDraw, right: tuple[float, float], pixels_per_km: float) -> None:
    steps = (5, 10, 20, 25, 50, 100, 200, 250, 500, 1000)
    step = next((s for s in reversed(steps) if 2 * s * pixels_per_km <= 200), steps[0])
    length = 2 * step * pixels_per_km
    x1, y = right
    x0 = x1 - length
    font = _font(15, 600)
    draw.line([(x0, y), (x1, y)], fill=WHITE, width=2)
    for tick in (x0, x0 + length / 2, x1):
        draw.line([(tick, y - 7), (tick, y)], fill=WHITE, width=2)
    # Sólo los extremos: con la marca del medio rotulada, las cifras se pisaban.
    _shadow_text(draw, (x0, y - 11), "0", font, WHITE, anchor="ms")
    _shadow_text(draw, (x1, y - 11), f"{2 * step} km", font, WHITE, anchor="rs")


def _render_map(size: tuple[int, int], facts: BulletinFacts, palette: Palette) -> Image.Image:
    width, height = size
    if facts.latitude is None or facts.longitude is None:
        image = Image.new("RGB", size, OCEAN)
        ImageDraw.Draw(image).text((width / 2, height / 2), "Coordenadas en evaluación",
                                   font=_font(24, 600), fill=MUTED, anchor="mm")
        return image
    latitude, longitude = facts.latitude, facts.longitude
    span_km = map_span_km(latitude, longitude)

    # Se dibuja al doble y se reduce: Pillow no suaviza los bordes de polígonos.
    scale = 2
    big = Image.new("RGB", (width * scale, height * scale), OCEAN)
    ink = ImageDraw.Draw(big)
    projection = _Projection(width * scale, height * scale, latitude, longitude, span_km)
    for country in load_geo()["countries"]:
        for ring in country["rings"]:
            points = projection.ring(ring)
            if not _off_view(points, projection.width, projection.height):
                ink.polygon(points, fill=LAND, outline=BORDERS, width=scale)
    cx, cy = projection.width / 2, projection.height / 2
    for radius, line in ((74, 3), (50, 4), (28, 5)):
        r = radius * scale
        ink.ellipse((cx - r, cy - r, cx + r, cy + r), outline=palette.accent, width=line * scale)
    dot = 12 * scale
    ink.ellipse((cx - dot, cy - dot, cx + dot, cy + dot), fill=palette.accent, outline=WHITE, width=2 * scale)
    image = big.resize(size, Image.Resampling.LANCZOS)

    draw = ImageDraw.Draw(image)
    labels = _Labels(width, height, (width / 2, height / 2, 80.0))
    labels.boxes.append((width / 2 - 16, height / 2 - 16, width / 2 + 16, height / 2 + 16))
    plain = _Projection(width, height, latitude, longitude, span_km)
    city = _draw_cities(draw, plain, labels, latitude, longitude)
    center = (width / 2, height / 2)
    country = country_at(latitude, longitude)
    if country is None and city is not None:
        nearest = _nearest_place(latitude, longitude)
        country = _country_names()[0].get(nearest[0][1]) if nearest else None
    if country:
        _place_area_label(image, draw, labels, country, _font(23, 700), WHITE, city or center, LAND, 0.85)
    sea = sea_at(latitude, longitude)
    if sea:
        _place_area_label(image, draw, labels, sea, _font(21, 500), LABEL, center, OCEAN, 0.9)
    _draw_north_arrow(draw, (width - 34, 22))
    _draw_scale_bar(draw, (width - 30, height - 28), plain.pixels_per_km)
    return image


def _render_inset(size: tuple[int, int], facts: BulletinFacts, palette: Palette) -> Image.Image:
    width, height = size
    image = Image.new("RGB", size, (12, 38, 72))
    draw = ImageDraw.Draw(image)
    center_lon = facts.longitude if facts.longitude is not None else 0.0
    top, bottom = 84.0, -75.0

    def xy(delta_lon: float, lat: float) -> tuple[float, float]:
        return width * (delta_lon + 180) / 360, height * (top - lat) / (top - bottom)

    for ring in load_geo()["world"]:
        offsets = _unwrap(ring, center_lon)
        for shift in (-360.0, 0.0, 360.0):
            points = [xy(offset + shift, lat) for offset, lat in offsets]
            if not _off_view(points, width, height):
                draw.polygon(points, fill=(64, 104, 150))
    if facts.latitude is not None and facts.longitude is not None:
        span_km = map_span_km(facts.latitude, facts.longitude)
        cx, cy = xy(0.0, facts.latitude)
        half_w = max(6.0, width * span_km / (111.32 * max(math.cos(math.radians(facts.latitude)), 0.05)) / 720)
        half_h = max(6.0, height * (span_km * 1.1 / 110.57) / (top - bottom) / 2)
        draw.rectangle((cx - half_w, cy - half_h, cx + half_w, cy + half_h), outline=palette.accent, width=2)
        draw.ellipse((cx - 3, cy - 3, cx + 3, cy + 3), fill=palette.accent)
    return image


# --- Composición --------------------------------------------------------------


def _header(canvas: Image.Image, draw: ImageDraw.ImageDraw, facts: BulletinFacts, palette: Palette) -> None:
    logo = Image.open(LOGO_PATH).convert("RGBA").resize((116, 116), Image.Resampling.LANCZOS)
    canvas.paste(logo, (MARGIN, 34), logo)
    _tracked(draw, (168, 58), "SEISMIK", _font(56, 800), WHITE, spacing=3)
    draw.line([(528, 50), (528, 150)], fill=PANEL_EDGE, width=2)
    draw.text((554, 50), "BOLETÍN SÍSMICO", font=_font(42, 800), fill=WHITE)
    subtitle = "INFORMACIÓN PRELIMINAR" if facts.preliminary else f"INFORMACIÓN OFICIAL · {facts.agency_short.upper()}"
    _tracked(draw, (556, 112), subtitle, _font(17, 600), palette.title, spacing=2.5)


def _magnitude_panel(canvas: Image.Image, draw: ImageDraw.ImageDraw, facts: BulletinFacts, palette: Palette) -> None:
    box = (MARGIN, 188, 642, 340)
    _gradient_panel(canvas, box, palette.panel)
    _tracked(draw, (MARGIN + 28, 204), "MAGNITUD", _font(18, 700), (255, 232, 232), spacing=3)
    number = f"{facts.magnitude:.1f}" if facts.magnitude is not None else "—"
    number_font, type_font = _font(98, 800), _font(22, 600)
    draw.text((MARGIN + 24, 322), number, font=number_font, fill=WHITE, anchor="ls")
    edge = MARGIN + 24 + draw.textlength(number, font=number_font)
    if facts.magnitude_type:
        draw.text((edge + 6, 318), facts.magnitude_type, font=type_font, fill=(255, 228, 228), anchor="ls")
        edge += 6 + draw.textlength(facts.magnitude_type, font=type_font)
    divider = edge + 20
    draw.line([(divider, 214), (divider, 318)], fill=(255, 210, 210), width=2)
    font, lines = _fit(draw, facts.title, box[2] - 22 - (divider + 20), 3, (23, 20, 18), 600)
    line_height = int(font.size) + 8
    top = 266 - len(lines) * line_height / 2
    for index, line in enumerate(lines):
        draw.text((divider + 20, top + index * line_height), line, font=font, fill=WHITE)


def _time_panel(draw: ImageDraw.ImageDraw, facts: BulletinFacts) -> None:
    box = (662, 188, WIDTH - MARGIN, 340)
    _panel(draw, box)
    x = box[0] + 26
    _tracked(draw, (x, 206), "FECHA Y HORA", _font(16, 700), LABEL, spacing=2.5)
    if facts.origin_utc is None:
        draw.text((x, 270), "En evaluación", font=_font(24, 600), fill=WHITE, anchor="lm")
        return
    utc = facts.origin_utc.astimezone(timezone.utc)
    draw.text((x, 232), spanish_date(utc), font=_font(22, 700), fill=WHITE)
    draw.text((x, 262), f"{utc:%H:%M} UTC", font=_font(22, 500), fill=WHITE)
    # Si en Colombia aún es el día anterior, la línea ocupa dos renglones.
    font = _font(16, 500)
    for index, line in enumerate(_wrap(draw, f"({colombia_time(utc)})", font, box[2] - 18 - x, 2)):
        draw.text((x, 292 + index * 19), line, font=font, fill=MUTED)


def _details_panel(draw: ImageDraw.ImageDraw, facts: BulletinFacts) -> None:
    box = (MARGIN, 360, 500, 944)
    _panel(draw, box)
    location: list[tuple[str, int, int, Rgb, int]] = []
    if facts.latitude is not None and facts.longitude is not None:
        location.append((_coordinates_text(facts.latitude, facts.longitude), 22, 700, WHITE, 1))
        if facts.relative:
            location.append((facts.relative[:1].upper() + facts.relative[1:], 17, 500, MUTED, 2))
    else:
        location.append(("Coordenadas en evaluación", 20, 600, WHITE, 1))
    depth = _depth_text(facts.depth_km) if facts.depth_km is not None else "En evaluación"
    event: list[tuple[str, int, int, Rgb, int]] = []
    if facts.event_id:
        event.append((facts.event_id.upper(), 21, 700, WHITE, 1))
    if facts.official_url:
        event.append((re.sub(r"^https?://(www\.)?", "", facts.official_url), 16, 500, LABEL, 2))
    rows: list[tuple[str, str, list[tuple[str, int, int, Rgb, int]]]] = [
        ("pin", "UBICACIÓN", location),
        ("layers", "PROFUNDIDAD", [(depth, 24, 700, WHITE, 1)]),
        ("wave", "FUENTE", [(facts.agency_long, 19, 600, WHITE, 3)]),
        ("doc", "EVENTO", event or [("En evaluación", 20, 600, WHITE, 1)]),
    ]
    row_height = (box[3] - box[1]) / len(rows)
    x = box[0] + 106
    for index, (icon, label, blocks) in enumerate(rows):
        top = box[1] + index * row_height
        if index:
            draw.line([(box[0] + 24, top), (box[2] - 24, top)], fill=PANEL_EDGE, width=1)
        _icon(draw, (box[0] + 58, top + 58), icon, WHITE)
        _tracked(draw, (x, top + 24), label, _font(15, 700), LABEL, spacing=2)
        y = top + 52
        for text, size, weight, fill, max_lines in blocks:
            font = _font(size, weight)
            for line in _wrap(draw, text, font, box[2] - 20 - x, max_lines):
                draw.text((x, y), line, font=font, fill=fill)
                y += round(size * 1.32)


def _map_panel(canvas: Image.Image, draw: ImageDraw.ImageDraw, facts: BulletinFacts, palette: Palette) -> None:
    box = (520, 360, WIDTH - MARGIN, 944)
    size = (box[2] - box[0], box[3] - box[1])
    canvas.paste(_render_map(size, facts, palette), (box[0], box[1]), _rounded_mask(size, 22))
    draw.rounded_rectangle(box, 22, outline=(70, 120, 190), width=2)


def _info_panel(canvas: Image.Image, draw: ImageDraw.ImageDraw, facts: BulletinFacts, palette: Palette) -> None:
    box = (MARGIN, 964, WIDTH - MARGIN, 1188)
    _panel(draw, box)
    _icon(draw, (box[0] + 58, box[1] + 62), "info", WHITE)
    x = box[0] + 106
    title = "INFORMACIÓN PRELIMINAR" if facts.preliminary else "INFORMACIÓN ADICIONAL"
    _tracked(draw, (x, box[1] + 26), title, _font(16, 700), palette.title, spacing=2.5)
    inset_box = (798, box[1] + 26, box[2] - 26, box[3] - 26)
    font = _font(18, 500)
    lines: list[str] = []
    for paragraph in summary_paragraphs(facts):
        lines.extend(_wrap(draw, paragraph, font, inset_box[0] - 34 - x, 4))
    for index, line in enumerate(lines[:6]):
        draw.text((x, box[1] + 58 + index * 25), line, font=font, fill=WHITE)
    draw.line([(inset_box[0] - 18, box[1] + 26), (inset_box[0] - 18, box[3] - 26)], fill=PANEL_EDGE, width=1)
    size = (inset_box[2] - inset_box[0], inset_box[3] - inset_box[1])
    canvas.paste(_render_inset(size, facts, palette), (inset_box[0], inset_box[1]), _rounded_mask(size, 12))
    draw.rounded_rectangle(inset_box, 12, outline=PANEL_EDGE, width=2)


def _footer(draw: ImageDraw.ImageDraw, facts: BulletinFacts, generated_at: datetime) -> None:
    y = 1210
    draw.line([(MARGIN, y), (WIDTH - MARGIN, y)], fill=PANEL_EDGE, width=1)
    font = _font(16, 500)
    source = f"Fuente: {facts.agency_long}"
    if facts.event_id:
        source += f" · Evento {facts.event_id.upper()}"
    lines = _wrap(draw, source, font, 640, 2)
    for index, line in enumerate(lines):
        draw.text((MARGIN, y + 22 + index * 22), line, font=font, fill=MUTED)
    stamp = generated_at.astimezone(timezone.utc)
    draw.text((MARGIN, y + 28 + len(lines) * 22), f"Consulta: {spanish_date(stamp)} · {stamp:%H:%M} UTC",
              font=font, fill=MUTED)
    draw.text((WIDTH - MARGIN, y + 30), "seismik.org", font=_font(26, 800), fill=WHITE, anchor="ra")
    draw.text((WIDTH - MARGIN, y + 68), "Boletín automático con datos oficiales", font=_font(15, 500),
              fill=MUTED, anchor="ra")


def render_bulletin_card(event: dict[str, Any], *, generated_at: datetime | None = None) -> bytes:
    """PNG de 1080×1350 (formato vertical que X muestra completo en el timeline)."""
    facts = bulletin_facts(event)
    palette = PRELIMINARY if facts.preliminary else OFFICIAL
    canvas = _background()
    draw = ImageDraw.Draw(canvas)
    _header(canvas, draw, facts, palette)
    _magnitude_panel(canvas, draw, facts, palette)
    _time_panel(draw, facts)
    _details_panel(draw, facts)
    _map_panel(canvas, draw, facts, palette)
    _info_panel(canvas, draw, facts, palette)
    _footer(draw, facts, generated_at or datetime.now(timezone.utc))
    buffer = io.BytesIO()
    canvas.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
