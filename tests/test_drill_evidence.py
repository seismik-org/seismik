"""La evidencia de los simulacros debe seguir demostrando lo que afirma.

Los archivos de `data/drills/` se citan en el control de avance. Si la política
de alertamiento cambiara y dejara de coincidir con esa evidencia, el sprint
estaría documentando algo que ya no ocurre.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

DRILLS = Path("data/drills")

# Perfiles definidos en tools/run_drill.py y su resultado esperado.
EXPECTED_CRITICAL = {"drill-device-cerca", "drill-device-umbral-alto"}
EXPECTED_OFFICIAL = {"drill-device-cerca", "drill-device-silenciado"}


def load(name: str) -> dict:
    path = DRILLS / name
    if not path.is_file():
        pytest.skip(f"Evidencia no incluida: {name}")
    return json.loads(path.read_text(encoding="utf-8"))


def replay_drills() -> list[Path]:
    return sorted(DRILLS.glob("sa2-drill-co-*.json"))


def test_simulated_drill_reached_exactly_the_expected_devices() -> None:
    evidence = load("sa2-drill-simulation-2026-08-30.json")
    critical = [item for item in evidence["push_attempts"] if item["critical"]]
    official = [item for item in evidence["push_attempts"] if not item["critical"]]

    assert len(critical) == 1
    assert set(critical[0]["targets"]) == EXPECTED_CRITICAL
    assert len(official) == 1
    assert set(official[0]["targets"]) == EXPECTED_OFFICIAL


def test_a_repeated_drill_event_is_reported_as_duplicate() -> None:
    evidence = load("sa2-drill-simulation-2026-08-30.json")
    assert evidence["ingest"]["candidate_accepted"]["duplicate"] is False
    assert evidence["ingest"]["candidate_repeated"]["duplicate"] is True


def test_the_distant_device_never_appears_in_any_drill() -> None:
    """El umbral de cercanía es el filtro más fácil de romper sin notarlo."""

    for path in [*replay_drills(), DRILLS / "sa2-drill-simulation-2026-08-30.json"]:
        if not path.is_file():
            continue
        evidence = json.loads(path.read_text(encoding="utf-8"))
        for attempt in evidence["push_attempts"]:
            assert "drill-device-lejos" not in attempt["targets"], path.name


def test_no_drill_left_the_dry_run_mode() -> None:
    for path in DRILLS.glob("sa2-drill-*.json"):
        evidence = json.loads(path.read_text(encoding="utf-8"))
        for attempt in evidence["push_attempts"]:
            assert attempt["dry_run"] is True, (
                f"{path.name} salió de dry_run: pudo enviar notificaciones reales"
            )


@pytest.mark.parametrize("path", replay_drills() or [None])
def test_recorded_earthquakes_produce_one_critical_alert(path: Path | None) -> None:
    if path is None:
        pytest.skip("Sin ensayos de replay registrados")
    evidence = json.loads(path.read_text(encoding="utf-8"))
    assert evidence["source"]["kind"] == "replay"
    critical = [item for item in evidence["push_attempts"] if item["critical"]]
    assert len(critical) == 1, path.name
    assert set(critical[0]["targets"]) == EXPECTED_CRITICAL


def test_ambient_noise_did_not_raise_an_alert() -> None:
    """Disparos locales sin coincidencia multiestación no deben alertar."""

    evidence = load("sa2-drill-ambient-noise.json")
    assert evidence["outcome"] == "silence"
    assert evidence["candidate_event_id"] is None
    assert evidence["push_attempts"] == []


def test_every_drill_declares_its_limitations() -> None:
    for path in DRILLS.glob("sa2-drill-*.json"):
        evidence = json.loads(path.read_text(encoding="utf-8"))
        assert evidence.get("limitations"), path.name


def test_offline_ledger_matches_what_each_device_was_sent() -> None:
    evidence = load("sa2-drill-simulation-2026-08-30.json")
    ledger = evidence["alert_ledger_by_device"]

    # Quien recibió el push debe poder recuperarlo tras quedarse sin conexión.
    assert evidence["candidate_event_id"] in ledger["drill-device-cerca"]
    assert evidence["official_event_id"] in ledger["drill-device-cerca"]
    # Y quien quedó fuera del radio no lo encuentra en su bitácora.
    assert ledger["drill-device-lejos"] == []
