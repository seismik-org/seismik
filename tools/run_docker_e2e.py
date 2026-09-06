#!/usr/bin/env python3
"""Prueba un Docker Compose activo: replay -> API -> Redis -> payload TEST."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import requests
from redis.asyncio import Redis

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from api.security import create_signature  # noqa: E402
from eew.config import Settings  # noqa: E402
from eew.replay import MiniSeedReplay, _manifest_paths  # noqa: E402


def post_json(url: str, payload: dict[str, Any], headers: dict[str, str]) -> requests.Response:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    return requests.post(url, data=body, headers={"Content-Type": "application/json", **headers}, timeout=10)


async def wait_for_audit(redis_url: str, stream: str, event_id: str) -> dict[str, str]:
    redis = Redis.from_url(redis_url, decode_responses=True)
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            for _entry_id, fields in await redis.xrevrange(stream, count=100):
                if fields.get("event_id") == event_id:
                    return fields
            await asyncio.sleep(0.25)
    finally:
        await redis.aclose()
    raise TimeoutError("Dispatcher did not create a TEST audit payload within 15 seconds")


def main() -> int:
    logging.getLogger("eew.processor").setLevel(logging.ERROR)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", default="http://localhost:8000")
    parser.add_argument("--redis-url", default="redis://localhost:6379/0")
    parser.add_argument("--config", type=Path, default=PROJECT_ROOT / "config.json")
    parser.add_argument("--manifest", type=Path, default=PROJECT_ROOT / "data/replay/manifest.json")
    parser.add_argument("--case", default="co-2023-08-17-m6.1")
    parser.add_argument("--webhook-secret", required=True)
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "work/sprint3-e2e.json")
    args = parser.parse_args()

    replay = MiniSeedReplay.from_settings(Settings.load(args.config)).run(
        _manifest_paths(args.manifest, args.case),
        chunk_seconds=5,
        include_event_payload=True,
    )
    if not replay["candidates"]:
        raise RuntimeError(f"Replay case {args.case} did not produce a candidate")
    event = replay["candidates"][0]["event"]
    run_id = uuid4().hex[:12]
    zone_id = f"CO-TEST-{run_id}"
    event["event_id"] = f"{event['event_id']}-{run_id}"
    event["zone_id"] = zone_id
    for station in event["stations"]:
        station["zone_id"] = zone_id

    device_id = f"device-e2e-{run_id}"
    device_payload = {
        "device_id": device_id,
        "platform": "android",
        "fcm_token": "TEST_TOKEN_" + run_id + "x" * 32,
        "zone_id": zone_id,
        "play_integrity_token": "local-app-check-debug-token",
    }
    registered = post_json(
        f"{args.api_base.rstrip('/')}/v1/devices/register", device_payload, {}
    )
    registered.raise_for_status()
    device_headers = {
        "X-Seismik-Device-Session": registered.json()["device_session_token"]
    }
    try:
        body = json.dumps(event, ensure_ascii=False, separators=(",", ":")).encode()
        timestamp = str(time.time())
        webhook_headers = {
            "Content-Type": "application/json",
            "X-Seismik-Timestamp": timestamp,
            "X-Seismik-Signature": create_signature(
                args.webhook_secret, timestamp, body
            ),
        }
        endpoint = f"{args.api_base.rstrip('/')}/v1/events/candidate"
        accepted = requests.post(endpoint, data=body, headers=webhook_headers, timeout=10)
        accepted.raise_for_status()
        duplicate = requests.post(endpoint, data=body, headers=webhook_headers, timeout=10)
        duplicate.raise_for_status()
        audit = asyncio.run(
            wait_for_audit(args.redis_url, "stream:seismik:push-test", event["event_id"])
        )
    finally:
        post_json(
            f"{args.api_base.rstrip('/')}/v1/devices/unregister",
            {"device_id": device_id},
            device_headers,
        )

    audit_payload = json.loads(audit["payload"])
    waveform_inputs = []
    for item in replay["inputs"]:
        source_path = Path(item["path"])
        try:
            portable_path = source_path.relative_to(PROJECT_ROOT).as_posix()
        except ValueError:
            portable_path = source_path.name
        waveform_inputs.append({**item, "path": portable_path})

    evidence = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "TEST",
        "case_id": args.case,
        "waveform_inputs": waveform_inputs,
        "candidate_event_id": event["event_id"],
        "first_ingest": accepted.json(),
        "duplicate_ingest": duplicate.json(),
        "audit": {
            key: value
            for key, value in audit.items()
            if key not in {"target_device_ids"}
        },
        "assertions": {
            "first_accepted": not accepted.json()["duplicate"],
            "duplicate_suppressed": duplicate.json()["duplicate"],
            "payload_marked_test": audit.get("test") == "true",
            "external_push_disabled": audit.get("test") == "true",
            "critical_text_utf8": (
                audit_payload.get("title") == "\u00a1ALERTA S\u00cdSMICA!"
                and "C\u00fabrete" in audit_payload.get("body", "")
            ),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", "utf-8")
    print(json.dumps(evidence, indent=2, ensure_ascii=False))
    return 0 if all(evidence["assertions"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
