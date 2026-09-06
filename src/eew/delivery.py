"""Entrega durable de eventos del detector hacia la API de eventos Seismik.

El hilo SeedLink no puede bloquearse ni perder candidatos cuando la API está
reiniciándose. Esta cola persiste cada intento en disco, reintenta con espera
exponencial y expone contadores para la salud del proceso detector.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

LOGGER = logging.getLogger(__name__)

# Un candidato deja de ser accionable mucho antes de este límite; el spool sólo
# evita perder trazabilidad mientras la API vuelve.
DEFAULT_MAX_AGE_SECONDS = 900.0


@dataclass
class DeliveryMetrics:
    """Contadores del enlace detector → API expuestos en la salud del proceso."""

    queued: int = 0
    delivered: int = 0
    duplicates: int = 0
    failed_attempts: int = 0
    spooled: int = 0
    expired: int = 0
    last_error: str | None = None
    last_delivery_epoch: float | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record(self, **increments: int) -> None:
        with self._lock:
            for name, delta in increments.items():
                setattr(self, name, getattr(self, name) + delta)

    def mark_delivered(self, *, duplicate: bool) -> None:
        with self._lock:
            self.delivered += 1
            if duplicate:
                self.duplicates += 1
            self.last_delivery_epoch = time.time()
            self.last_error = None

    def mark_error(self, message: str) -> None:
        with self._lock:
            self.failed_attempts += 1
            self.last_error = message[:300]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "queued": self.queued,
                "delivered": self.delivered,
                "duplicates": self.duplicates,
                "failed_attempts": self.failed_attempts,
                "spooled": self.spooled,
                "expired": self.expired,
                "last_error": self.last_error,
                "last_delivery_epoch": self.last_delivery_epoch,
            }


class DeliverySpool:
    """Cola en disco, ordenada y atómica, para eventos pendientes de entrega.

    Cada evento se escribe con os.replace sobre un archivo temporal del mismo
    directorio, de modo que un apagado abrupto nunca deja un JSON truncado.
    """

    def __init__(self, directory: str | Path, max_entries: int = 500):
        self.directory = Path(directory)
        self.max_entries = max_entries
        self._lock = threading.Lock()
        self._sequence = 0
        self.directory.mkdir(parents=True, exist_ok=True)

    def append(self, payload: dict[str, Any], *, event_type: str, event_id: str) -> Path | None:
        record = {
            "event_id": event_id,
            "event_type": event_type,
            "enqueued_at": time.time(),
            "payload": payload,
        }
        body = json.dumps(record, ensure_ascii=False, separators=(",", ":"), default=str)
        with self._lock:
            self._prune_locked()
            self._sequence += 1
            name = f"{int(time.time() * 1000):015d}-{self._sequence:04d}.json"
            target = self.directory / name
            handle, temporary = tempfile.mkstemp(dir=self.directory, suffix=".tmp")
            try:
                with os.fdopen(handle, "w", encoding="utf-8") as stream:
                    stream.write(body)
                os.replace(temporary, target)
            except OSError as error:
                Path(temporary).unlink(missing_ok=True)
                LOGGER.error("No se pudo persistir el evento en el spool: %s", error)
                return None
            return target

    def pending(self) -> list[Path]:
        with self._lock:
            return sorted(path for path in self.directory.glob("*.json"))

    def read(self, path: Path) -> dict[str, Any] | None:
        try:
            decoded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            LOGGER.error("Entrada de spool ilegible %s: %s", path.name, error)
            path.unlink(missing_ok=True)
            return None
        if not isinstance(decoded, dict) or "payload" not in decoded:
            path.unlink(missing_ok=True)
            return None
        return decoded

    def remove(self, path: Path) -> None:
        path.unlink(missing_ok=True)

    def _prune_locked(self) -> None:
        entries = sorted(self.directory.glob("*.json"))
        excess = len(entries) - self.max_entries + 1
        for path in entries[:excess] if excess > 0 else []:
            LOGGER.warning("Spool lleno; se descarta la entrada más antigua %s", path.name)
            path.unlink(missing_ok=True)


@dataclass(frozen=True)
class DeliveryOutcome:
    """Resultado de un intento de POST hacia la API de eventos."""

    delivered: bool
    duplicate: bool = False
    retryable: bool = True
    detail: str | None = None


class DurableEventDelivery:
    """Reintenta los eventos pendientes fuera del hilo de adquisición."""

    def __init__(
        self,
        sender: Callable[[str, dict[str, Any]], DeliveryOutcome],
        spool: DeliverySpool,
        metrics: DeliveryMetrics | None = None,
        *,
        retry_interval_seconds: float = 5.0,
        max_age_seconds: float = DEFAULT_MAX_AGE_SECONDS,
    ):
        self.sender = sender
        self.spool = spool
        self.metrics = metrics or DeliveryMetrics()
        self.retry_interval_seconds = retry_interval_seconds
        self.max_age_seconds = max_age_seconds

    def submit(self, payload: dict[str, Any], *, event_type: str, event_id: str) -> bool:
        """Intenta entregar de inmediato y persiste el evento si no se logra."""

        self.metrics.record(queued=1)
        outcome = self._attempt(event_type, payload)
        if outcome.delivered:
            self.metrics.mark_delivered(duplicate=outcome.duplicate)
            return True
        if not outcome.retryable:
            LOGGER.error(
                "La API rechazó el evento sin posibilidad de reintento event_id=%s detail=%s",
                event_id,
                outcome.detail,
            )
            return False
        if self.spool.append(payload, event_type=event_type, event_id=event_id) is not None:
            self.metrics.record(spooled=1)
        return False

    def drain(self) -> int:
        """Reenvía las entradas pendientes; devuelve cuántas quedaron entregadas."""

        delivered = 0
        for path in self.spool.pending():
            record = self.spool.read(path)
            if record is None:
                continue
            age = time.time() - float(record.get("enqueued_at", 0.0))
            if age > self.max_age_seconds:
                LOGGER.warning(
                    "Evento vencido en el spool event_id=%s age=%.0fs",
                    record.get("event_id"),
                    age,
                )
                self.metrics.record(expired=1)
                self.spool.remove(path)
                continue
            outcome = self._attempt(str(record["event_type"]), dict(record["payload"]))
            if outcome.delivered:
                self.metrics.mark_delivered(duplicate=outcome.duplicate)
                self.spool.remove(path)
                delivered += 1
                continue
            if not outcome.retryable:
                self.spool.remove(path)
                continue
            break  # La API sigue caída; conserva el orden de la cola.
        return delivered

    def pending_count(self) -> int:
        return len(self.spool.pending())

    def _attempt(self, event_type: str, payload: dict[str, Any]) -> DeliveryOutcome:
        try:
            return self.sender(event_type, payload)
        except Exception as error:  # noqa: BLE001 - el enlace no debe tumbar el detector
            self.metrics.mark_error(f"{type(error).__name__}: {error}")
            return DeliveryOutcome(delivered=False, detail=str(error))
