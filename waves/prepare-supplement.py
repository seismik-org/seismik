"""Prepare a reproducible addition; never upload, modify originals or the base manifest.

Generated catalogues/previews and upload copies are build artifacts, not repository data.
Run after prepare.ps1, or repeatedly: counts are recomputed from the original manifest.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
import shutil
from pathlib import Path

HERE = Path(__file__).parent
PREFIX = "supplements/2026-10-18/"
SOURCES = (
    ("work/audits/seedlink-2026-10-17/historical-earthscope.mseed", "MiniSEED",
     "Ventanas de auditoría SeedLink · septiembre–octubre de 2026",
     "EarthScope FDSN dataselect", "https://service.earthscope.org/fdsnws/dataselect/1/",
     "Ventanas discontinuas alrededor de candidatos, no 30 sismos confirmados. Sólo canal vertical; no sustituye los tres componentes necesarios para algunas estimaciones."),
    ("work/station-survey-20261017/islands-response.xml", "StationXML",
     "Respuesta instrumental · estaciones de la búsqueda insular",
     "EarthScope FDSN station", "https://service.earthscope.org/fdsnws/station/1/",
     "Inventario instrumental recuperado en la búsqueda; no implica autorización de streaming ni estación incorporada a producción."),
    ("work/station-survey-20261017/selection-response.xml", "StationXML",
     "Respuesta instrumental · selección de estaciones",
     "EarthScope FDSN station", "https://service.earthscope.org/fdsnws/station/1/",
     "Metadatos y respuestas por canal; revisar época de validez antes de corregir una señal."),
    ("work/seismik-mobile-adaptive/data/stations/central-colombia-access-2026-10-17.json", "JSON",
     "Acceso y latencia · centro de Colombia", "Seismik · mediciones del 17 de octubre", None,
     "Pruebas cortas desde PC y nube; no garantizan latencia futura ni validación científica."),
    ("work/seismik-mobile-adaptive/data/stations/central-other-providers-2026-10-17.json", "JSON",
     "Búsqueda de otros proveedores · centro de Colombia", "Seismik · búsqueda del 17 de octubre", None,
     "Resultados de disponibilidad; encontrar metadatos no equivale a acceso en vivo ni permiso de redistribución."),
    ("work/seismik-mobile-adaptive/data/stations/colombia-open-selection-2026-10-17.json", "JSON",
     "Selección y calidad de estaciones abiertas", "Seismik · mediciones del 17 de octubre", None,
     "Instantánea técnica, sin activar estaciones nuevas ni modificar alertas."),
)


def prepare(workspace: Path, output: Path) -> dict:
    base = json.loads((workspace / "work/storage-migration-2026-10-10/manifest.json").read_text("utf-8"))
    catalog = json.loads((HERE / "catalog.json").read_text("utf-8"))
    catalog["records"] = [r for r in catalog["records"] if not r["name"].startswith(PREFIX)]
    views = json.loads((HERE / "catalog-view.json").read_text("utf-8"))
    spec = importlib.util.spec_from_file_location("wave_previews", HERE / "build-previews.py")
    previews = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(previews)
    items, entries = [], []
    for source, fmt, title, provider, url, description in SOURCES:
        path = workspace / source
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        name = PREFIX + path.name
        record = {"id": digest[:24], "name": name, "bytes": len(raw), "sha256": digest,
                  "category": "supplements", "format": fmt, "live": False,
                  "validation_status": "research_not_validated", "redistribution": "requires_source_review",
                  "title": title, "provider": provider, "source_url": url, "description": description,
                  "retrieved_on": "2026-10-17"}
        target = output / "data" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        entries.append(record)
        if fmt != "MiniSEED":
            items.append(record)
            continue
        traces = previews.traces_of(path)
        context = {"kind": "caso", "title": title, "origin_time": None, "magnitude": None,
                   "magnitude_type": None, "place": None, "latitude": None, "longitude": None,
                   "depth_km": None, "reference": provider, "reference_url": url, "detail": description}
        payload = {"id": record["id"], "buckets": previews.BUCKETS,
                   "reduction": "min/max por segmento; promedio restado sólo para dibujar; huecos sin rellenar",
                   "context": context, "traces": traces}
        (HERE / "previews" / f"{record['id']}.json.gz").write_bytes(
            gzip.compress(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(), mtime=0))
        views[record["id"]] = {**context, "stations": len({t["network"] + t["station"] for t in traces}),
                              "traces": len(traces), "rate": traces[0]["rate"],
                              "duration_s": max(t["duration_s"] for t in traces),
                              "start": min(t["start"] for t in traces)}
        catalog["records"].append(record)
    catalog.update(files=base["files"] + len(entries), bytes=base["bytes"] + sum(e["bytes"] for e in entries),
                   snapshot_date="2026-10-18")
    metadata = {"updated_on": "2026-10-18", "items": items, "scientific_validation": "not_validated"}
    for name, data in (("catalog.json", catalog), ("catalog-view.json", views), ("resources.json", metadata)):
        (HERE / name).write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), "utf-8")
    manifest = {"base_import": "local-2026-10-10", "added_on": "2026-10-18", "entries": entries,
                "files": len(entries), "bytes": sum(e["bytes"] for e in entries),
                "live": False, "scientific_validation": "not_validated"}
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = prepare(args.workspace.resolve(), args.output.resolve())
    print(f"Prepared {result['files']} additional files, {result['bytes']} bytes; originals untouched.")
