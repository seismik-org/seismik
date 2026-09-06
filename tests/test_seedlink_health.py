"""La decisión de respaldo entre proveedores SeedLink debe ser reproducible."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from measure_seedlink_health import measure_tcp_connect, rank_providers  # noqa: E402

EVIDENCE = Path("data/seedlink/sa2-provider-health-2026-08-30.json")


def provider(
    provider_id: str,
    *,
    healthy: bool = True,
    delivery_ratio: float = 1.0,
    lag: float | None = 1.0,
) -> dict:
    return {
        "provider_id": provider_id,
        "healthy": healthy,
        "delivery_ratio": delivery_ratio,
        "median_packet_lag_seconds": lag,
    }


def test_a_healthy_provider_always_outranks_an_unreachable_one() -> None:
    order = rank_providers(
        [
            provider("caido", healthy=False, delivery_ratio=0.0, lag=None),
            provider("sano", lag=5.0),
        ]
    )
    assert order == ["sano", "caido"]


def test_delivery_matters_more_than_latency() -> None:
    """Un proveedor rápido que entrega la mitad no reemplaza a uno completo."""

    order = rank_providers(
        [
            provider("rapido_incompleto", delivery_ratio=0.5, lag=0.5),
            provider("completo", delivery_ratio=1.0, lag=4.0),
        ]
    )
    assert order == ["completo", "rapido_incompleto"]


def test_with_equal_delivery_the_lower_lag_wins() -> None:
    order = rank_providers(
        [
            provider("lento", lag=6.1),
            provider("rapido", lag=1.2),
        ]
    )
    assert order == ["rapido", "lento"]


def test_a_provider_without_measured_lag_goes_last_among_its_peers() -> None:
    order = rank_providers([provider("sin_dato", lag=None), provider("medido", lag=9.0)])
    assert order == ["medido", "sin_dato"]


def test_an_unreachable_endpoint_is_reported_without_raising() -> None:
    """Un proveedor caído no puede tumbar el barrido de los demás."""

    # El puerto 1 reservado no acepta conexiones en ningún entorno de CI.
    result = measure_tcp_connect("127.0.0.1:1", timeout=1.0)
    assert result["reachable"] is False
    assert "error" in result
    assert result["connect_seconds"] >= 0


@pytest.mark.skipif(not EVIDENCE.is_file(), reason="Evidencia de campo no incluida")
def test_recorded_field_evidence_keeps_its_shape() -> None:
    document = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    assert document["schema_version"] == 1
    assert document["providers"], "La evidencia debe listar proveedores"
    assert document["suggested_failover_order"]
    assert "limitation" in document, "La medición puntual debe declarar su alcance"
    for report in document["providers"]:
        assert "tcp" in report
        assert "stations" in report
