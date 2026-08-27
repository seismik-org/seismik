"""Reproduccion determinista de MiniSEED para validar el motor sin esperar sismos."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from dataclasses import asdict, dataclass
from datetime import timezone
from pathlib import Path
from typing import Any

import numpy as np
from obspy import Stream, Trace, read  # type: ignore[import-untyped]

from eew.coincidence import ZoneCoincidenceRouter
from eew.config import CoincidenceSettings, DetectionSettings, Settings, StationSubscription
from eew.processor import StationProcessor


@dataclass(frozen=True)
class ReplayTrigger:
    station_id: str
    stream_id: str
    zone_id: str
    trigger_time: str
    sta_lta_ratio: float


@dataclass(frozen=True)
class ReplayCandidate:
    replay_event_id: str
    zone_id: str
    detected_at: str
    stations: tuple[str, ...]


class ReplayClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


class MiniSeedReplay:
    """Ejecuta el mismo procesador y correlador con un reloj derivado de la onda."""

    def __init__(
        self,
        subscriptions: tuple[StationSubscription, ...],
        detection: DetectionSettings,
        coincidence: CoincidenceSettings,
    ) -> None:
        self._clock = ReplayClock()
        self._processors = {
            self._key(item.network, item.station, item.location, item.channel): StationProcessor(
                item,
                detection.for_stream(item.network, item.channel),
                provider_id="replay",
                country_code=item.country_code or "XX",
                zone_id=item.zone_id or item.country_code or "XX",
                monotonic_clock=self._clock,
            )
            for item in subscriptions
        }
        self._router = ZoneCoincidenceRouter(coincidence, self._clock)

    @classmethod
    def from_settings(cls, settings: Settings) -> MiniSeedReplay:
        subscriptions = tuple(
            station
            for provider in settings.seedlink.providers
            if provider.enabled
            for station in provider.stations
        )
        return cls(subscriptions, settings.detection, settings.coincidence)

    def run(
        self,
        paths: list[Path],
        chunk_seconds: float = 1.0,
        *,
        include_event_payload: bool = False,
    ) -> dict[str, Any]:
        if chunk_seconds <= 0:
            raise ValueError("chunk_seconds debe ser positivo")
        chunks: list[Trace] = []
        inputs = []
        for path in sorted((item.resolve() for item in paths), key=str):
            content = path.read_bytes()
            inputs.append(
                {
                    "path": str(path),
                    "bytes": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                }
            )
            chunks.extend(self._chunks(read(path), chunk_seconds))
        chunks.sort(key=lambda trace: (float(trace.stats.starttime), trace.id))

        triggers: list[ReplayTrigger] = []
        candidates: list[ReplayCandidate] = []
        candidate_payloads: dict[str, dict[str, Any]] = {}
        for trace in chunks:
            self._clock.value = float(trace.stats.endtime)
            processor = self._processors.get(
                self._key(
                    trace.stats.network,
                    trace.stats.station,
                    trace.stats.location or None,
                    trace.stats.channel,
                )
            )
            if processor is None:
                processor = self._processors.get(
                    self._key(
                        trace.stats.network,
                        trace.stats.station,
                        None,
                        trace.stats.channel,
                    )
                )
            if processor is None:
                continue
            trigger = processor.process(
                trace,
                received_at=trace.stats.endtime.datetime.replace(tzinfo=timezone.utc),
            )
            if trigger is None:
                continue
            triggers.append(
                ReplayTrigger(
                    station_id=trigger.station_id,
                    stream_id=trigger.stream_id,
                    zone_id=trigger.zone_id,
                    trigger_time=trigger.trigger_time,
                    sta_lta_ratio=trigger.sta_lta_ratio,
                )
            )
            candidate = self._router.add(trigger)
            if candidate is None:
                continue
            station_ids = tuple(sorted(item.station_id for item in candidate.stations))
            detected_at = max(item.trigger_time for item in candidate.stations)
            identity = "|".join((candidate.zone_id, detected_at, *station_ids))
            replay_event_id = hashlib.sha256(identity.encode()).hexdigest()[:24]
            candidates.append(
                ReplayCandidate(
                    replay_event_id=replay_event_id,
                    zone_id=candidate.zone_id,
                    detected_at=detected_at,
                    stations=station_ids,
                )
            )
            if include_event_payload:
                payload = asdict(candidate)
                payload["event_id"] = replay_event_id
                payload["detected_at"] = detected_at
                candidate_payloads[replay_event_id] = payload

        return {
            "schema_version": 1,
            "clock": "waveform_timestamps",
            "chunk_seconds": chunk_seconds,
            "inputs": inputs,
            "chunk_count": len(chunks),
            "triggers": [asdict(item) for item in triggers],
            "candidates": [
                {
                    **asdict(item),
                    **(
                        {"event": candidate_payloads[item.replay_event_id]}
                        if include_event_payload
                        else {}
                    ),
                }
                for item in candidates
            ],
        }

    @staticmethod
    def _chunks(stream: Stream, chunk_seconds: float) -> list[Trace]:
        result: list[Trace] = []
        for trace in stream:
            rate = float(trace.stats.sampling_rate)
            chunk_samples = max(1, round(chunk_seconds * rate))
            data = np.asarray(trace.data)
            for start in range(0, data.size, chunk_samples):
                chunk = Trace(data=data[start : start + chunk_samples].copy())
                chunk.stats.network = trace.stats.network
                chunk.stats.station = trace.stats.station
                chunk.stats.location = trace.stats.location
                chunk.stats.channel = trace.stats.channel
                chunk.stats.sampling_rate = rate
                chunk.stats.starttime = trace.stats.starttime + start / rate
                result.append(chunk)
        return result

    @staticmethod
    def _key(network: str, station: str, location: str | None, channel: str) -> str:
        return f"{network}.{station}.{location if location is not None else '*'}.{channel}"


def _manifest_paths(manifest_path: Path, case_id: str) -> list[Path]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    selected = next((case for case in manifest["cases"] if case["id"] == case_id), None)
    if selected is None:
        raise ValueError(f"Caso no encontrado: {case_id}")
    paths = []
    for waveform in selected.get("waveforms", []):
        path = Path(waveform["path"])
        if not path.is_absolute():
            path = manifest_path.parent / path
        paths.append(path)
    if not paths:
        raise ValueError(f"Caso sin waveforms locales: {case_id}")
    return paths


def main() -> None:
    logging.getLogger("eew.processor").setLevel(logging.ERROR)
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("config.json"))
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--case", required=True)
    parser.add_argument("--chunk-seconds", type=float, default=1.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = MiniSeedReplay.from_settings(Settings.load(args.config)).run(
        _manifest_paths(args.manifest, args.case), args.chunk_seconds
    )
    rendered = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
