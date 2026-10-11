"""Genera las vistas previas de forma de onda del piloto Waves (sin tocar el archivo privado en la nube).

Lee las grabaciones MiniSEED de la copia local verificada (`work/storage-migration-2026-10-10/staged-data`),
comprueba su SHA-256 contra el catálogo y escribe, por grabación, `previews/<id>.json.gz` con una envolvente
mínimo/máximo de 600 intervalos por canal. Es sólo una reducción para dibujar: sin filtros, sin corrección
instrumental, sin picado de fases ni magnitudes. A cada canal se le resta su promedio (DC) únicamente para
poder dibujarlo; el promedio queda guardado. También escribe `catalog-view.json` con el contexto de cada evento
(fuente de referencia, hora, lugar, magnitud publicada) para que el catálogo sea legible.

Los archivos originales no salen del almacenamiento privado ni se publican; las previas se empaquetan con el
servicio, detrás de la sesión aprobada, y no permiten reconstruir la grabación (600 intervalos de ~0,7 s).

Uso (requiere obspy y numpy):
    python build-previews.py [--staged RUTA]
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import obspy

HERE = Path(__file__).parent
DEFAULT_STAGED = HERE.parent.parent / "storage-migration-2026-10-10" / "staged-data"
BUCKETS = 600
COMPONENT_ORDER = {"Z": 0, "N": 1, "1": 1, "E": 2, "2": 2}


def iso(moment: obspy.UTCDateTime) -> str:
    return moment.datetime.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def millis(value: int) -> str:
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def trace_preview(trace: obspy.Trace) -> dict:
    data = np.asarray(trace.data, dtype=np.float64)
    npts = data.size
    mean = float(data.mean())
    centered = data - mean
    edges = (np.arange(BUCKETS) * npts) // BUCKETS
    mins = np.minimum.reduceat(centered, edges)
    maxs = np.maximum.reduceat(centered, edges)
    return {
        "id": trace.id, "network": trace.stats.network, "station": trace.stats.station,
        "location": trace.stats.location, "channel": trace.stats.channel,
        "rate": float(trace.stats.sampling_rate), "start": iso(trace.stats.starttime), "end": iso(trace.stats.endtime),
        "samples": int(npts), "duration_s": round(float(trace.stats.endtime - trace.stats.starttime), 2),
        "mean_counts": round(mean, 1), "peak_counts": int(np.abs(centered).max()),
        "rms_counts": round(float(np.sqrt(np.mean(centered ** 2))), 1),
        "mins": [int(v) for v in np.floor(mins)], "maxs": [int(v) for v in np.ceil(maxs)],
    }


def traces_of(path: Path) -> list[dict]:
    stream = obspy.read(str(path))
    gaps = len(stream.get_gaps())
    if gaps:  # no ocurre en el archivo actual; se deja tolerante
        stream.merge(method=1, fill_value=0)
    ordered = sorted(stream, key=lambda t: (t.stats.network, t.stats.station, t.stats.location,
                                             COMPONENT_ORDER.get(t.stats.channel[-1], 9), t.stats.channel))
    result = [trace_preview(trace) for trace in ordered]
    for item in result:
        item["gaps_in_file"] = gaps
    return result


def context_for(name: str, notes: dict) -> dict:
    """Qué sismo es, según la fuente de referencia que acompaña al archivo. Nada de lo que calcula Seismik."""
    stem = Path(name).stem
    if "/ml-evaluation-" in name and stem.startswith("noise-"):
        return {"kind": "ruido", "title": f"Ruido sísmico · ventana {stem.removeprefix('noise-')}", "origin_time": None, "latitude": None,
                "longitude": None, "depth_km": None, "magnitude": None, "magnitude_type": None, "place": None,
                "reference": "Ventana de ruido", "reference_url": None,
                "detail": "Ventana sin sismo usada como referencia en la evaluación de magnitud."}
    if "/ml-evaluation-" in name:
        isc = notes["isc"].get(stem.removeprefix("ev-"))
        if isc:
            return {"kind": "evento", "title": f"Evento ISC {isc['isc_event']}", "origin_time": isc["time"], "latitude": isc["lat"],
                    "longitude": isc["lon"], "depth_km": isc["depth_km"], "magnitude": isc["ml"], "magnitude_type": "Ml",
                    "place": None, "reference": "ISC · catálogo RSNC", "reference_url": None,
                    "detail": f"Ml con {isc['ml_nsta']} estaciones, incertidumbre {isc['ml_unc']}"}
    if "/historical-magnitude-" in name and stem.startswith("us"):
        feature = notes["usgs"].get(stem.removeprefix("us"))
        if feature:
            p, (lon, lat, depth) = feature["properties"], feature["geometry"]["coordinates"]
            return {"kind": "evento", "title": p.get("place") or stem, "origin_time": millis(p["time"]), "latitude": lat, "longitude": lon,
                    "depth_km": depth, "magnitude": p.get("mag"), "magnitude_type": p.get("magType"), "place": p.get("place"),
                    "reference": "USGS", "reference_url": p.get("url"), "detail": f"Estado de la revisión: {p.get('status')}"}
    fixture = notes["replay"].get(stem)
    if fixture:
        ambient = fixture["kind"] != "historical_earthquake"
        return {"kind": "ruido" if ambient else "evento", "title": "Ruido ambiente (sin sismo)" if ambient else fixture["place"],
                "origin_time": None if ambient else fixture["origin_time"], "latitude": None, "longitude": None, "depth_km": None,
                "magnitude": None if ambient else fixture["magnitude"], "magnitude_type": None if ambient else "USGS",
                "place": None if ambient else fixture["place"], "reference": "USGS" if not ambient else "Ventana de ruido",
                "reference_url": None if ambient else fixture.get("official_url"),
                "detail": "Ventana de prueba para repetir una misma reproducción del detector."}
    slug = re.sub(r"[-_]+", " ", stem).strip()
    return {"kind": "caso", "title": slug.title(), "origin_time": None, "latitude": None, "longitude": None, "depth_km": None,
            "magnitude": None, "magnitude_type": None, "place": None, "reference": None, "reference_url": None,
            "detail": "Caso de estudio recuperado para analizar fases y latencia."}


def load_notes(staged: Path) -> dict:
    isc = json.loads((staged / "calibration/ml-evaluation-2026-10-03/isc-rsnc-ml-catalog.json").read_text(encoding="utf-8"))
    usgs = json.loads((staged / "calibration/historical-magnitude-2026-10-03/official-catalog.json").read_text(encoding="utf-8"))
    replay = json.loads((staged / "replay/manifest.json").read_text(encoding="utf-8"))
    return {"isc": {str(item["isc_event"]): item for item in isc},
            "usgs": {f["properties"]["code"]: f for f in usgs["features"] if f["properties"].get("net") == "us"},
            "replay": {case["id"]: case for case in replay["cases"]}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--staged", type=Path, default=DEFAULT_STAGED)
    args = parser.parse_args()
    warnings.filterwarnings("ignore")
    catalog = json.loads((HERE / "catalog.json").read_text(encoding="utf-8"))
    notes = load_notes(args.staged)
    out = HERE / "previews"
    out.mkdir(exist_ok=True)
    view: dict[str, dict] = {}
    total = 0
    for record in catalog["records"]:
        path = args.staged / record["name"]
        if sha256(path) != record["sha256"]:
            raise SystemExit(f"La copia local de {record['name']} no coincide con el catálogo; no se genera nada.")
        traces = traces_of(path)
        context = context_for(record["name"], notes)
        payload = {"id": record["id"], "buckets": BUCKETS, "reduction": "min/max por intervalo; promedio (DC) restado sólo para dibujar",
                   "context": context, "traces": traces}
        blob = gzip.compress(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"), 9)
        (out / f"{record['id']}.json.gz").write_bytes(blob)
        total += len(blob)
        stations = sorted({(t["network"], t["station"]) for t in traces})
        view[record["id"]] = {
            **{k: context[k] for k in ("kind", "title", "origin_time", "magnitude", "magnitude_type", "place", "reference")},
            "stations": len(stations), "traces": len(traces), "rate": traces[0]["rate"], "duration_s": max(t["duration_s"] for t in traces),
            "start": min(t["start"] for t in traces),
        }
    (HERE / "catalog-view.json").write_text(json.dumps(view, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    print(f"{len(view)} previas, {total / 1e6:.1f} MB comprimidos, en {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
