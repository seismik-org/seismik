"""Inyecta un sismo simulado en la API de eventos para ejecutar un simulacro.

El evento recorre exactamente la misma ruta que una detección real
(API → Redis Streams → dispatcher → push), por lo que un simulacro contra un
entorno con push habilitado envía notificaciones de verdad. Por eso cualquier
destino que no sea local exige ``--confirm-production``.

Uso:
    python tools/simulate_event.py --profile bogota --base-url http://127.0.0.1:8000
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import requests  # noqa: E402

from eew.simulation import PROFILES, drill_sequence  # noqa: E402

CANDIDATE_PATH = "/v1/events/candidate"
OFFICIAL_PATH = "/v1/events/official-update"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "api", "0.0.0.0"}


def _use_utf8_stdout() -> None:
    """La consola de Windows usa cp1252 y rompe acentos y flechas."""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simulacro sísmico Seismik")
    parser.add_argument("--profile", default="bogota", choices=sorted(PROFILES))
    parser.add_argument("--base-url", default=os.getenv("SEISMIK_API_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument(
        "--secret",
        default=os.getenv("SEISMIK_WEBHOOK_HMAC_SECRET", ""),
        help="Secreto HMAC compartido con la API (por defecto, la variable de entorno)",
    )
    parser.add_argument("--stations", type=int, default=3)
    parser.add_argument("--magnitude", type=float, default=None)
    parser.add_argument(
        "--candidate-only",
        action="store_true",
        help="Envía sólo la alerta temprana, sin la actualización oficial",
    )
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument(
        "--confirm-production",
        action="store_true",
        help="Requerido para apuntar a un destino que no sea local",
    )
    parser.add_argument("--dry-run", action="store_true", help="Imprime el evento sin enviarlo")
    return parser.parse_args()


def post_signed(
    base_url: str, path: str, event: dict[str, Any], secret: str, timeout: float
) -> dict[str, Any]:
    body = json.dumps(event, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    timestamp = str(int(time.time()))
    signature = hmac.new(
        secret.encode("utf-8"), timestamp.encode("ascii") + b"." + body, hashlib.sha256
    ).hexdigest()
    response = requests.post(
        base_url.rstrip("/") + path,
        data=body,
        timeout=timeout,
        headers={
            "User-Agent": "seismik-drill/1.0",
            "Content-Type": "application/json",
            "X-Seismik-Timestamp": timestamp,
            "X-Seismik-Signature": signature,
        },
    )
    response.raise_for_status()
    return dict(response.json())


def main() -> int:
    _use_utf8_stdout()
    args = parse_args()
    hostname = urlparse(args.base_url).hostname or ""
    if hostname not in LOCAL_HOSTS and not args.confirm_production and not args.dry_run:
        print(
            f"Destino no local ({hostname}). Un simulacro allí puede enviar notificaciones "
            "reales; repite con --confirm-production si esa es la intención.",
            file=sys.stderr,
        )
        return 2

    candidate, official = drill_sequence(
        args.profile, station_count=args.stations, magnitude=args.magnitude
    )
    events = [(CANDIDATE_PATH, candidate)]
    if not args.candidate_only:
        events.append((OFFICIAL_PATH, official))

    if args.dry_run:
        for _path, event in events:
            print(json.dumps(event, ensure_ascii=False, indent=2))
        return 0

    if not args.secret:
        print(
            "Falta el secreto HMAC: usa --secret o SEISMIK_WEBHOOK_HMAC_SECRET.",
            file=sys.stderr,
        )
        return 2

    for path, event in events:
        result = post_signed(args.base_url, path, event, args.secret, args.timeout)
        print(
            f"{path} event_id={event['event_id']} "
            f"accepted={result.get('accepted')} duplicate={result.get('duplicate')} "
            f"stream_id={result.get('stream_id')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
