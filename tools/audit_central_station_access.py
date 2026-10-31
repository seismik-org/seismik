"""Bounded passive access/latency audit; does not run detection or emit events."""
from __future__ import annotations

import argparse
import json
import math
import socket
import statistics
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import numpy as np
from obspy.clients.seedlink.easyseedlink import EasySeedLinkClient


def select_advertised(xml: str, requested: list[str]) -> list[str]:
    available = {
        ".".join((s.get("network", ""), s.get("name", ""),
                  c.get("location", ""), c.get("seedname", "")))
        for s in ElementTree.fromstring(xml).findall(".//station")
        for c in s.findall("stream")
        if c.get("type", "D") == "D"
    }
    return list(dict.fromkeys(key for key in requested if key in available))


def lag_summary(lags: list[float]) -> dict[str, Any]:
    finite = sorted(x for x in lags if math.isfinite(x))
    result: dict[str, Any] = {"packets": len(lags), "invalid_lags": len(lags)-len(finite),
                              "mean_seconds": None, "p50_seconds": None,
                              "p95_seconds": None, "min_seconds": None,
                              "max_seconds": None, "transport_short_probe_pass": False}
    if finite:
        p95 = finite[math.ceil(.95*len(finite))-1]
        result.update(mean_seconds=round(statistics.fmean(finite), 3),
                      p50_seconds=round(statistics.median(finite), 3),
                      p95_seconds=round(p95, 3), min_seconds=round(finite[0], 3),
                      max_seconds=round(finite[-1], 3),
                      transport_short_probe_pass=(len(finite) >= 5 and finite[0] >= 0
                                                  and p95 <= 15 and len(finite) == len(lags)))
    return result


def selector(stream_id: str) -> tuple[str, str, str]:
    network, station, location, channel = stream_id.split(".")
    if not network or not station or len(channel) != 3 or location and len(location) != 2:
        raise ValueError("Expected exact NETWORK.STATION.LOCATION.CHANNEL (location may be empty)")
    return network, station, location + channel


def audit(server: str, streams: list[str], seconds: float) -> dict[str, Any]:
    for key in streams:
        selector(key)
    started = datetime.now(timezone.utc)
    lock = threading.Lock()
    stopped = threading.Event()
    clients: list[Any] = []
    rows: dict[str, dict[str, Any]] = {
        key: {"access": "not_checked", "lags": [], "last_end": None,
              "gaps": 0, "overlaps": 0, "nonfinite_samples": 0}
        for key in dict.fromkeys(streams)
    }
    errors: list[str] = []

    def on_data(trace: Any) -> None:
        key = trace.id
        if key not in rows or stopped.is_set():
            return
        now = datetime.now(timezone.utc)
        end = float(trace.stats.endtime)
        with lock:
            r = rows[key]
            # Keep the requested audit bounded even if an unexpectedly fast stream arrives.
            if len(r["lags"]) >= 10000:
                return
            r["access"] = "packets_received"
            r["lags"].append(now.timestamp()-end)
            r["nonfinite_samples"] += int(np.count_nonzero(~np.isfinite(trace.data)))
            if r["last_end"] is not None:
                dt = float(trace.stats.delta)
                difference = float(trace.stats.starttime)-r["last_end"]-dt
                r["gaps"] += int(difference > dt*1.5)
                r["overlaps"] += int(difference < -dt*1.5)
            r["last_end"] = end
            r["first_received_at"] = r.get("first_received_at", now.isoformat())
            r["last_received_at"] = now.isoformat()
            r["sample_rate_hz"] = float(trace.stats.sampling_rate)

    def run() -> None:
        try:
            def connect() -> Any:
                client = EasySeedLinkClient(server, autoconnect=False)
                clients.append(client)
                client.on_data = on_data
                client.conn.timeout = min(10, seconds)
                client.conn.set_net_timeout(min(20, seconds))
                client.connect()
                return client

            info = connect()
            selected = select_advertised(info.get_info("STREAMS"), streams)
            # INFO may leave the protocol in streaming state. Never reuse that
            # session for a measurement: negotiate subscriptions on a fresh socket.
            info.close()
            clients.remove(info)
            with lock:
                for key, row in rows.items():
                    row["access"] = "advertised_no_packets" if key in selected else "not_advertised"
            if selected and not stopped.is_set():
                c = connect()
                for key in selected:
                    c.select_stream(*selector(key))
                # ObsPy's timeout bounds each collect() call, not just connect().
                # A quiet stream can take >10 s between records. The external
                # audit deadline bounds runtime; sample-age acceptance stays 15 s.
                c.conn.timeout = max(30, seconds + 3)
                c.run()
                if not stopped.is_set():
                    with lock:
                        errors.append("stream_ended_before_audit_deadline")
        except Exception as exc:  # Audit reports errors without hiding unavailable routes.
            if not stopped.is_set():
                with lock:
                    errors.append(type(exc).__name__ + ": " + str(exc))
        finally:
            for client in clients:
                client.conn.terminate()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    stopped.wait(seconds)
    stopped.set()
    for c in clients:
        # collect() resets terminate_flag at entry; a small shutdown-only timeout
        # also bounds the race between a callback and the next collect() call.
        c.conn.timeout = .1
        c.conn.terminate()
        connection_socket = getattr(c.conn, "socket", None)
        if connection_socket is not None:
            try:
                connection_socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass  # Already disconnected; don't turn controlled shutdown into an error.
    thread.join(3)
    with lock:
        report = {}
        for key, row in rows.items():
            data = {k: v for k, v in row.items() if k not in {"lags", "last_end"}}
            data.update(lag_summary(row["lags"]))
            if errors or thread.is_alive():
                data["transport_short_probe_pass"] = False
            data["scientifically_validated"] = False
            report[key] = data
    return {"server": server, "started_at": started.isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "measurement_vantage": "machine_running_this_command_not_necessarily_GCP",
            "requested_seconds": seconds, "streams": report, "errors": errors,
            "worker_stopped": not thread.is_alive(), "events_published": 0,
            "limitations": ["Short passive probe; not station/earthquake validation or SLA.",
                            "Lag is sample-end age on arrival, not earthquake-to-alert latency.",
                            "Missing packets produce null latency, never zero.",
                            "Availability, instrument response and regional geometry need separate QC."]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", default="rtserve.earthscope.org:18000")
    parser.add_argument("--stream", action="append", required=True)
    parser.add_argument("--seconds", type=float, default=120)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 3600 or len(args.stream) > 20:
        parser.error("Use 1..3600 seconds and at most 20 exact streams")
    result = audit(args.server, args.stream, args.seconds)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
