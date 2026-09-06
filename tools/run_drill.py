#!/usr/bin/env python3
"""Ejecuta un simulacro completo sobre HTTP real y deja evidencia reproducible.

Levanta la API con uvicorn en un puerto local, registra dispositivos con
umbrales distintos, inyecta el sismo firmado, consume el stream con el
dispatcher real y consulta la bitácora de alertas. Todo el camino —firma HMAC,
validación de contrato, Redis Streams, política de alertamiento y sincronización
offline— se recorre sin atajos.

Dos fuentes de sismo:

    --profile bogota                  evento simulado (`drill-…`)
    --replay-case co-2023-08-17-m6.1  onda real grabada, a través del detector

Redis se sustituye por `fakeredis` para que el simulacro corra sin Docker. Es la
única pieza simulada y queda declarada en la evidencia.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import socket
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import httpx  # noqa: E402
import uvicorn  # noqa: E402
from fakeredis.aioredis import FakeRedis  # noqa: E402
from fastapi import FastAPI  # noqa: E402

from api.alerts import router as alerts_router  # noqa: E402
from api.bus import RedisEventBus  # noqa: E402
from api.config import AppSettings  # noqa: E402
from api.dependencies import get_app_settings, get_bus  # noqa: E402
from api.devices import router as devices_router  # noqa: E402
from api.devices_store import DeviceRepository  # noqa: E402
from api.integrity import DeviceIntegrityVerifier  # noqa: E402
from api.security import create_signature  # noqa: E402
from api.webhooks import router as webhooks_router  # noqa: E402
from dispatcher.consumer import StreamConsumer  # noqa: E402
from dispatcher.policy import AlertPolicy  # noqa: E402
from dispatcher.push import PushDispatcher  # noqa: E402
from eew.config import Settings  # noqa: E402
from eew.replay import MiniSeedReplay, _manifest_paths  # noqa: E402
from eew.simulation import drill_sequence  # noqa: E402

DRILL_SECRET = "drill-local-hmac-secret"

# Perfiles de dispositivo del simulacro: cubren el caso que debe recibir, el que
# está demasiado lejos, el que pidió una magnitud alta y el que apagó los avisos.
DEVICE_PROFILES: tuple[dict[str, Any], ...] = (
    {
        "device_id": "drill-device-cerca",
        "latitude": 4.70,
        "longitude": -74.00,
        "alert_radius_km": 250.0,
        "minimum_notification_magnitude": 3.0,
        "receive_early_alerts": True,
        "expectation": "recibe la alerta temprana y la actualización oficial",
    },
    {
        "device_id": "drill-device-lejos",
        "latitude": 6.25,
        "longitude": -75.57,
        "alert_radius_km": 50.0,
        "minimum_notification_magnitude": 3.0,
        "receive_early_alerts": True,
        "expectation": "queda fuera del radio elegido",
    },
    {
        "device_id": "drill-device-umbral-alto",
        "latitude": 4.66,
        "longitude": -74.04,
        "alert_radius_km": 250.0,
        "minimum_notification_magnitude": 7.5,
        "receive_early_alerts": True,
        "expectation": "recibe la alerta temprana pero no la oficial",
    },
    {
        "device_id": "drill-device-silenciado",
        "latitude": 4.67,
        "longitude": -74.03,
        "alert_radius_km": 250.0,
        "minimum_notification_magnitude": 3.0,
        "receive_early_alerts": False,
        "expectation": "desactivó las alertas tempranas",
    },
)


def _use_utf8_stdout() -> None:
    """La consola de Windows usa cp1252 y rompe acentos y flechas."""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")

def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def build_app(settings: AppSettings, redis: FakeRedis) -> FastAPI:
    app = FastAPI(title="Seismik drill")
    app.state.settings = settings
    app.state.redis = redis
    app.state.devices = DeviceRepository(redis)
    app.state.integrity_verifier = DeviceIntegrityVerifier(settings)
    bus = RedisEventBus(redis, settings.stream_maxlen, settings.webhook_idempotency_seconds)
    app.state.bus = bus
    app.dependency_overrides[get_bus] = lambda: bus
    app.dependency_overrides[get_app_settings] = lambda: settings
    app.include_router(webhooks_router)
    app.include_router(devices_router)
    app.include_router(alerts_router)
    return app


class BackgroundServer:
    """uvicorn en un hilo: el simulacro habla HTTP real, no ASGI en memoria."""

    def __init__(self, app: FastAPI, port: int):
        config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def __enter__(self) -> "BackgroundServer":
        self.thread.start()
        deadline = time.monotonic() + 30
        while not self.server.started and time.monotonic() < deadline:
            time.sleep(0.05)
        if not self.server.started:
            raise RuntimeError("uvicorn no arrancó a tiempo")
        return self

    def __exit__(self, *_exc: object) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=10)


def signed_headers(body: bytes) -> dict[str, str]:
    timestamp = str(int(time.time()))
    return {
        "Content-Type": "application/json",
        "X-Seismik-Timestamp": timestamp,
        "X-Seismik-Signature": create_signature(DRILL_SECRET, timestamp, body),
    }


def replay_candidate(
    case_id: str, config_path: Path, *, allow_silence: bool
) -> dict[str, Any] | None:
    """Reproduce una grabación real y devuelve su primer candidato.

    Un caso de ruido ambiental debe terminar en silencio: ahí la ausencia de
    candidato es el resultado buscado, no un fallo del ensayo.
    """

    settings = Settings.load(config_path)
    manifest = PROJECT_ROOT / "data/replay/manifest.json"
    paths = _manifest_paths(manifest, case_id)
    result = MiniSeedReplay.from_settings(settings).run(paths, include_event_payload=True)
    if not result["candidates"]:
        if allow_silence:
            return None
        raise SystemExit(
            f"El caso {case_id} no produjo candidatos con el perfil actual. "
            "Si el silencio es lo esperado, repite con --expect-silence."
        )
    return dict(result["candidates"][0]["event"])


async def register_devices(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    registered = []
    for index, profile in enumerate(DEVICE_PROFILES):
        payload = {
            "device_id": profile["device_id"],
            "platform": "android",
            "fcm_token": f"{profile['device_id']}-token".ljust(64, "0")[:64],
            "zone_id": "andes",
            "latitude": profile["latitude"],
            "longitude": profile["longitude"],
            "alert_radius_km": profile["alert_radius_km"],
            "minimum_notification_magnitude": profile["minimum_notification_magnitude"],
            "receive_early_alerts": profile["receive_early_alerts"],
            "receive_official_updates": True,
            "play_integrity_token": f"drill-integrity-token-{index}",
        }
        response = await client.post("/v1/devices/register", json=payload)
        response.raise_for_status()
        registered.append(
            {
                "device_id": profile["device_id"],
                "expectation": profile["expectation"],
                "device_session_token": response.json()["device_session_token"],
            }
        )
    return registered


async def drain(redis: FakeRedis, settings: AppSettings) -> list[dict[str, Any]]:
    """Consume ambos streams con el dispatcher real y anota a quién alcanzó."""

    delivered: list[dict[str, Any]] = []
    push = PushDispatcher(settings)
    original_send = push.send

    async def recording_send(event, targets, *, critical):  # type: ignore[no-untyped-def]
        target_list = list(targets)
        result = await original_send(event, target_list, critical=critical)
        delivered.append(
            {
                "event_id": event["event_id"],
                "critical": critical,
                "targets": sorted(item.device_id for item in target_list),
                "dry_run": result.dry_run,
            }
        )
        return result

    push.send = recording_send  # type: ignore[method-assign]
    consumer = StreamConsumer(
        redis, settings, DeviceRepository(redis), push, AlertPolicy(redis, settings)
    )
    await consumer.ensure_groups()
    messages = await redis.xreadgroup(
        settings.dispatcher_group,
        settings.consumer_name,
        {stream: ">" for stream in consumer.streams},
        count=100,
        block=50,
    )
    for stream, entries in messages or []:
        for message_id, fields in entries:
            await consumer._handle(stream, message_id, fields)
    return delivered


async def run_drill(args: argparse.Namespace) -> dict[str, Any]:
    redis = FakeRedis(decode_responses=True)
    settings = AppSettings(
        webhook_hmac_secret=DRILL_SECRET,
        push_enabled=False,
        push_mode="dry_run",
        integrity_verification_enabled=False,
        alert_cooldown_seconds=args.cooldown_seconds,
    )
    port = free_port()
    app = build_app(settings, redis)

    if args.replay_case:
        candidate = replay_candidate(
            args.replay_case, args.config, allow_silence=args.expect_silence
        )
        official = None
        source = {"kind": "replay", "case": args.replay_case}
        if candidate is None:
            return {
                "schema_version": 1,
                "executed_at": datetime.now(timezone.utc)
                .isoformat(timespec="seconds")
                .replace("+00:00", "Z"),
                "source": source,
                "candidate_event_id": None,
                "official_event_id": None,
                "outcome": "silence",
                "note": (
                    "La grabación no superó la coincidencia multiestación: "
                    "ninguna alerta salió, que es el resultado esperado para "
                    "ruido ambiental."
                ),
                "push_attempts": [],
                "alert_ledger_by_device": {},
                "timings_ms": {},
                "limitations": [
                    "Un solo caso grabado no caracteriza la tasa de falsos disparos.",
                ],
            }
    else:
        candidate, official = drill_sequence(args.profile, magnitude=args.magnitude)
        source = {"kind": "simulation", "profile": args.profile}

    timings: dict[str, float] = {}
    with BackgroundServer(app, port):
        base_url = f"http://127.0.0.1:{port}"
        async with httpx.AsyncClient(base_url=base_url, timeout=20) as client:
            devices = await register_devices(client)

            body = json.dumps(candidate, ensure_ascii=False, separators=(",", ":")).encode()
            started = time.perf_counter()
            accepted = await client.post(
                "/v1/events/candidate", content=body, headers=signed_headers(body)
            )
            timings["candidate_ingest_ms"] = round((time.perf_counter() - started) * 1000, 2)
            accepted.raise_for_status()

            repeated = await client.post(
                "/v1/events/candidate", content=body, headers=signed_headers(body)
            )

            official_response = None
            if official is not None:
                official_body = json.dumps(
                    official, ensure_ascii=False, separators=(",", ":")
                ).encode()
                started = time.perf_counter()
                official_response = await client.post(
                    "/v1/events/official-update",
                    content=official_body,
                    headers=signed_headers(official_body),
                )
                timings["official_ingest_ms"] = round((time.perf_counter() - started) * 1000, 2)
                official_response.raise_for_status()

            started = time.perf_counter()
            delivered = await drain(redis, settings)
            timings["dispatch_ms"] = round((time.perf_counter() - started) * 1000, 2)

            ledger: dict[str, list[str]] = {}
            for profile, registered_device in zip(DEVICE_PROFILES, devices, strict=True):
                response = await client.get(
                    "/v1/alerts/recent",
                    params={"device_id": profile["device_id"]},
                    headers={
                        "X-Seismik-Device-Session": registered_device[
                            "device_session_token"
                        ]
                    },
                )
                response.raise_for_status()
                ledger[profile["device_id"]] = [
                    alert["event_id"] for alert in response.json()["alerts"]
                ]

    return {
        "schema_version": 1,
        "executed_at": datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "source": source,
        "candidate_event_id": candidate["event_id"],
        "official_event_id": official["event_id"] if official else None,
        "devices": [
            {"device_id": item["device_id"], "expectation": item["expectation"]}
            for item in devices
        ],
        "ingest": {
            "candidate_accepted": accepted.json(),
            "candidate_repeated": repeated.json(),
            "official_accepted": official_response.json() if official_response else None,
        },
        "push_attempts": delivered,
        "alert_ledger_by_device": ledger,
        "timings_ms": timings,
        "limitations": [
            "Redis se sustituye por fakeredis: el simulacro no mide durabilidad real.",
            "El push queda en dry_run; ningún teléfono recibió una notificación.",
            "No reemplaza el simulacro con testers y dispositivos reales.",
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--profile", default="bogota", help="Perfil de sismo simulado")
    source.add_argument("--replay-case", help="Identificador en data/replay/manifest.json")
    parser.add_argument("--config", type=Path, default=PROJECT_ROOT / "config.json")
    parser.add_argument("--magnitude", type=float, default=None)
    parser.add_argument("--cooldown-seconds", type=int, default=60)
    parser.add_argument(
        "--expect-silence",
        action="store_true",
        help="El caso no debe disparar: registra el silencio como evidencia",
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    _use_utf8_stdout()
    args = parse_args()
    evidence = asyncio.run(run_drill(args))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(args.output)
    for attempt in evidence["push_attempts"]:
        kind = "crítica" if attempt["critical"] else "oficial"
        print(f"  alerta {kind:<8} → {attempt['targets'] or 'sin destinatarios'}")
    print(f"  latencias: {evidence['timings_ms']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
