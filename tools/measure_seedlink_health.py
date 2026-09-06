#!/usr/bin/env python3
"""Mide la salud real de los proveedores SeedLink configurados.

Responde las preguntas que SA2-01 exige medir por región: cuánto tarda cada
proveedor en aceptar la conexión, cuánto en entregar el primer paquete, qué lag
trae ese paquete y si la reconexión se recupera. Con esos números se decide el
orden de respaldo entre proveedores en lugar de suponerlo.

Uso:
    python tools/measure_seedlink_health.py --config config.json \\
        --output work/seedlink-health.json
"""
from __future__ import annotations

import argparse
import json
import socket
import statistics
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from obspy import Trace  # type: ignore[import-untyped]  # noqa: E402
from obspy.clients.seedlink.easyseedlink import (  # type: ignore[import-untyped]  # noqa: E402
    create_client,
)

from eew.config import SeedLinkProvider, Settings, StationSubscription  # noqa: E402


def _use_utf8_stdout() -> None:
    """La consola de Windows usa cp1252 y rompe acentos y flechas."""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")

def _iso(value: datetime) -> str:
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def measure_tcp_connect(server: str, timeout: float) -> dict[str, Any]:
    """Separa el costo de red del costo del protocolo SeedLink."""

    host, _, port = server.partition(":")
    started = time.monotonic()
    try:
        with socket.create_connection((host, int(port or 18000)), timeout=timeout):
            return {"reachable": True, "connect_seconds": round(time.monotonic() - started, 3)}
    except OSError as error:
        return {
            "reachable": False,
            "connect_seconds": round(time.monotonic() - started, 3),
            "error": f"{type(error).__name__}: {error}",
        }


def measure_first_packet(
    server: str, station: StationSubscription, timeout: float
) -> dict[str, Any]:
    """Espera un único paquete y devuelve su latencia y lag observados."""

    result: dict[str, Any] = {
        "station_id": station.station_id,
        "channel": station.channel,
        "received": False,
    }
    clients: list[Any] = []
    started = time.monotonic()

    def on_data(trace: Trace) -> None:
        received_at = datetime.now(timezone.utc)
        packet_end = trace.stats.endtime.datetime.replace(tzinfo=timezone.utc)
        result.update(
            {
                "received": True,
                "stream_id": trace.id,
                "received_at": _iso(received_at),
                "samples": int(trace.stats.npts),
                "sample_rate_hz": float(trace.stats.sampling_rate),
                "first_packet_seconds": round(time.monotonic() - started, 3),
                "packet_lag_seconds": round((received_at - packet_end).total_seconds(), 3),
            }
        )
        if clients:
            clients[0].conn.terminate()

    def run() -> None:
        try:
            client = create_client(server, on_data=on_data)
            clients.append(client)
            client.select_stream(station.network, station.station, station.channel)
            client.conn.set_net_timeout(timeout)
            client.run()
        except Exception as error:  # noqa: BLE001 - la medición no debe abortar el barrido
            result["error"] = f"{type(error).__name__}: {error}"
        finally:
            if clients:
                clients[0].conn.terminate()

    worker = threading.Thread(target=run, name="seedlink-measure", daemon=True)
    worker.start()
    worker.join(timeout)
    if worker.is_alive():
        if not result["received"]:
            result["error"] = "timeout"
        if clients:
            clients[0].conn.terminate()
    return result


def measure_provider(
    provider: SeedLinkProvider,
    *,
    stations: int,
    timeout: float,
    reconnect: bool,
) -> dict[str, Any]:
    selected = provider.stations[:stations]
    report: dict[str, Any] = {
        "provider_id": provider.id,
        "server": provider.server,
        "country_code": provider.country_code,
        "required": provider.required,
        "tcp": measure_tcp_connect(provider.server, timeout),
        "stations": [],
    }
    if not report["tcp"]["reachable"]:
        report["healthy"] = False
        return report

    for station in selected:
        report["stations"].append(measure_first_packet(provider.server, station, timeout))

    if reconnect and selected and report["stations"][0].get("received"):
        # Una reconexión inmediata mide lo que ocurre tras un corte de red: es
        # el escenario que decide si conviene cambiar de proveedor o esperar.
        report["reconnect"] = measure_first_packet(provider.server, selected[0], timeout)

    lags = [
        item["packet_lag_seconds"]
        for item in report["stations"]
        if item.get("packet_lag_seconds") is not None
    ]
    delivered = sum(1 for item in report["stations"] if item.get("received"))
    report["stations_probed"] = len(report["stations"])
    report["stations_delivering"] = delivered
    report["delivery_ratio"] = (
        round(delivered / len(report["stations"]), 3) if report["stations"] else 0.0
    )
    report["median_packet_lag_seconds"] = round(statistics.median(lags), 3) if lags else None
    report["healthy"] = delivered > 0
    return report


def rank_providers(reports: list[dict[str, Any]]) -> list[str]:
    """Orden de respaldo sugerido: primero entrega, después lag."""

    def key(report: dict[str, Any]) -> tuple[int, float, float]:
        lag = report.get("median_packet_lag_seconds")
        return (
            0 if report.get("healthy") else 1,
            -float(report.get("delivery_ratio") or 0.0),
            float(lag) if lag is not None else 9_999.0,
        )

    return [report["provider_id"] for report in sorted(reports, key=key)]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=PROJECT_ROOT / "config.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stations-per-provider", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--provider", action="append", help="Limita el barrido a estos ids")
    parser.add_argument(
        "--no-reconnect",
        action="store_true",
        help="Omite la segunda conexión que mide la recuperación",
    )
    return parser.parse_args()


def main() -> int:
    _use_utf8_stdout()
    args = parse_args()
    settings = Settings.load(args.config)
    providers = [provider for provider in settings.seedlink.providers if provider.enabled]
    if args.provider:
        wanted = set(args.provider)
        providers = [provider for provider in providers if provider.id in wanted]
    if not providers:
        print("No hay proveedores habilitados que medir", file=sys.stderr)
        return 2

    started = datetime.now(timezone.utc)
    reports = [
        measure_provider(
            provider,
            stations=max(1, args.stations_per_provider),
            timeout=args.timeout,
            reconnect=not args.no_reconnect,
        )
        for provider in providers
    ]
    document = {
        "schema_version": 1,
        "started_at": _iso(started),
        "completed_at": _iso(datetime.now(timezone.utc)),
        "config": str(args.config),
        "providers": reports,
        "suggested_failover_order": rank_providers(reports),
        "healthy_providers": sum(1 for report in reports if report.get("healthy")),
        "limitation": (
            "Medición puntual: describe el momento de la ejecución, no un "
            "acuerdo de disponibilidad ni la latencia sostenida del proveedor."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(args.output)
    for report in reports:
        print(
            f"{report['provider_id']:<24} healthy={str(report.get('healthy')):<5} "
            f"entrega={report.get('stations_delivering', 0)}/{report.get('stations_probed', 0)} "
            f"lag_mediano={report.get('median_packet_lag_seconds')}"
        )
    return 0 if document["healthy_providers"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
