"""Prueba acotada de un paquete SeedLink y registra su lag observado."""

from __future__ import annotations

import argparse
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from obspy import Trace  # type: ignore[import-untyped]
from obspy.clients.seedlink.easyseedlink import create_client  # type: ignore[import-untyped]


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", default="rtserve.earthscope.org:18000")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result: dict[str, Any] = {
        "schema_version": 1,
        "server": args.server,
        "selection": "CM_ARGC_HHZ",
        "received": False,
    }
    clients: list[Any] = []

    def on_data(trace: Trace) -> None:
        received_at = datetime.now(timezone.utc)
        sample_end = trace.stats.endtime.datetime.replace(tzinfo=timezone.utc)
        result.update(
            {
                "received": True,
                "received_at": _iso(received_at),
                "stream_id": trace.id,
                "samples": int(trace.stats.npts),
                "sample_rate_hz": float(trace.stats.sampling_rate),
                "packet_start": _iso(trace.stats.starttime.datetime.replace(tzinfo=timezone.utc)),
                "packet_end": _iso(sample_end),
                "observed_packet_lag_seconds": round(
                    (received_at - sample_end).total_seconds(), 3
                ),
            }
        )
        if clients:
            clients[0].conn.terminate()

    def connect_and_read() -> None:
        try:
            client = create_client(args.server, on_data=on_data)
            clients.append(client)
            client.select_stream("CM", "ARGC", "HHZ")
            client.conn.set_net_timeout(args.timeout)
            client.run()
        except Exception as exc:
            result["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            if clients:
                clients[0].conn.terminate()

    worker = threading.Thread(target=connect_and_read, name="seedlink-probe", daemon=True)
    worker.start()
    worker.join(args.timeout)
    if worker.is_alive():
        if not result["received"]:
            result["error"] = "probe_timeout"
        else:
            result["termination_pending"] = True
        if clients:
            clients[0].conn.terminate()
    result["completed_at"] = _iso(datetime.now(timezone.utc))
    result["limitation"] = "Single-packet point-in-time probe; not an uptime guarantee."
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(args.output)
    if not result["received"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
