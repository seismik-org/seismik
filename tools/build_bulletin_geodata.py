"""Genera la cartografía compacta de los boletines de X desde Natural Earth.

Natural Earth es de dominio público. Sus GeoJSON originales pesan casi 6 MB;
el boletín sólo necesita contornos simplificados y puntos para las etiquetas,
así que el repositorio guarda `src/integrations/assets/bulletin_geo.json.gz`.

Uso (con los GeoJSON de nvkelso/natural-earth-vector en un directorio):

    python tools/build_bulletin_geodata.py <directorio>

Archivos de entrada:
    ne_50m_admin_0_countries.geojson        contornos y nombres de países
    ne_110m_admin_0_countries.geojson       mapa mundial del recuadro
    ne_50m_populated_places_simple.geojson  ciudades de referencia
    ne_50m_geography_marine_polys.geojson   nombres de océanos y mares
"""
from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path
from typing import Any

OUTPUT = Path(__file__).resolve().parents[1] / "src/integrations/assets/bulletin_geo.json.gz"

Ring = list[list[float]]


def _load(directory: Path, name: str) -> list[dict[str, Any]]:
    with (directory / name).open(encoding="utf-8") as handle:
        return list(json.load(handle)["features"])


def _exterior_rings(geometry: dict[str, Any]) -> list[Ring]:
    if geometry["type"] == "Polygon":
        return [geometry["coordinates"][0]]
    if geometry["type"] == "MultiPolygon":
        return [polygon[0] for polygon in geometry["coordinates"]]
    return []


def _simplify(points: Ring, tolerance: float) -> Ring:
    """Douglas-Peucker iterativo; conserva siempre el primer y el último punto."""
    if len(points) < 4:
        return points
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        start, end = stack.pop()
        (x1, y1), (x2, y2) = points[start][:2], points[end][:2]
        dx, dy = x2 - x1, y2 - y1
        length = (dx * dx + dy * dy) ** 0.5
        farthest, distance = -1, tolerance
        for index in range(start + 1, end):
            px, py = points[index][:2]
            if length == 0:
                offset = ((px - x1) ** 2 + (py - y1) ** 2) ** 0.5
            else:
                offset = abs(dy * px - dx * py + x2 * y1 - y2 * x1) / length
            if offset > distance:
                farthest, distance = index, offset
        if farthest != -1:
            keep[farthest] = True
            stack.extend([(start, farthest), (farthest, end)])
    return [point for point, kept in zip(points, keep) if kept]


def _compact(ring: Ring, tolerance: float, digits: int) -> Ring | None:
    simplified = _simplify(ring, tolerance)
    compact: Ring = []
    for lon, lat in (point[:2] for point in simplified):
        rounded = [round(lon, digits), round(lat, digits)]
        if not compact or compact[-1] != rounded:
            compact.append(rounded)
    return compact if len(compact) >= 4 else None


def _centroid(ring: Ring) -> tuple[float, float, float]:
    """Centroide y área (grados²) de un anillo; el área decide qué parte etiquetar."""
    area = cx = cy = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        cross = x1 * y2 - x2 * y1
        area += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    if area == 0:
        xs, ys = zip(*ring)
        return sum(xs) / len(xs), sum(ys) / len(ys), 0.0
    return cx / (3 * area), cy / (3 * area), abs(area) / 2


def _capitalize(name: str) -> str:
    return name[:1].upper() + name[1:] if name else name


def build(directory: Path) -> dict[str, Any]:
    countries = []
    for feature in _load(directory, "ne_50m_admin_0_countries.geojson"):
        props = feature["properties"]
        rings = [
            ring
            for ring in (_compact(r, 0.01, 2) for r in _exterior_rings(feature["geometry"]))
            if ring
        ]
        if not rings:
            continue
        iso = props.get("ISO_A2_EH") if props.get("ISO_A2") in (None, "-99") else props["ISO_A2"]
        countries.append({
            "iso": iso if iso and iso != "-99" else "",
            "name": props.get("NAME_ES") or props["NAME"],
            "name_en": props["NAME"],
            "label": [round(props["LABEL_X"], 2), round(props["LABEL_Y"], 2)],
            "rank": props.get("LABELRANK", 5),
            "rings": rings,
        })

    world = [
        ring
        for feature in _load(directory, "ne_110m_admin_0_countries.geojson")
        for ring in (_compact(r, 0.2, 1) for r in _exterior_rings(feature["geometry"]))
        if ring
    ]

    places = [
        [
            props["name"],
            props.get("iso_a2") or "",
            round(props["longitude"], 3),
            round(props["latitude"], 3),
            int(props.get("pop_max") or 0),
            int(props.get("scalerank") or 10),
        ]
        for props in (f["properties"] for f in _load(directory, "ne_50m_populated_places_simple.geojson"))
    ]

    seas = []
    for feature in _load(directory, "ne_50m_geography_marine_polys.geojson"):
        props = feature["properties"]
        name = props.get("name_es") or props.get("name")
        rings = _exterior_rings(feature["geometry"])
        if not name or not rings:
            continue
        x, y, _area = max((_centroid([p[:2] for p in ring]) for ring in rings), key=lambda c: c[2])
        # Los contornos permiten saber en qué mar está un epicentro lejos de
        # toda ciudad; basta una simplificación gruesa.
        seas.append({
            "name": _capitalize(name),
            "label": [round(x, 2), round(y, 2)],
            "min_label": float(props.get("min_label") or 5),
            "kind": props.get("featurecla") or "",
            "rings": [ring for ring in (_compact(r, 0.05, 2) for r in rings) if ring],
        })

    return {
        "source": "Natural Earth (dominio público), https://www.naturalearthdata.com/",
        "countries": countries,
        "world": world,
        "places": places,
        "seas": seas,
    }


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    data = build(Path(sys.argv[1]))
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_bytes(gzip.compress(raw, compresslevel=9, mtime=0))
    points = sum(len(ring) for country in data["countries"] for ring in country["rings"])
    print(
        f"{OUTPUT}: {OUTPUT.stat().st_size} bytes gzip ({len(raw)} sin comprimir); "
        f"{len(data['countries'])} países, {points} puntos, {len(data['places'])} ciudades, "
        f"{len(data['seas'])} mares"
    )


if __name__ == "__main__":
    main()
