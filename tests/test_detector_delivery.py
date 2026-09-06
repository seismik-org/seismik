"""El enlace detector → API no debe perder candidatos si la API está caída."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import requests

from api.security import verify_signature
from eew.alerts import AlertDispatcher
from eew.config import AlertSettings
from eew.delivery import DeliveryOutcome, DeliverySpool, DurableEventDelivery
from eew.models import EarthquakeCandidate, StationTrigger


def build_candidate(event_id: str = "candidate-1") -> EarthquakeCandidate:
    trigger = StationTrigger(
        provider_id="test",
        country_code="CO",
        zone_id="andes",
        station_id="CM.A",
        stream_id="CM.A.00.HHZ",
        trigger_time="2026-01-01T00:00:00Z",
        received_at="2026-01-01T00:00:01Z",
        sta_lta_ratio=4.2,
    )
    return EarthquakeCandidate(
        event_id=event_id,
        type="earthquake_candidate",
        status="unlocated_unreviewed",
        zone_id="andes",
        country_code="CO",
        country_codes=("CO",),
        detected_at="2026-01-01T00:00:02Z",
        coincidence_window_seconds=15,
        required_stations=1,
        station_count=1,
        stations=(trigger,),
    )


class FakeResponse:
    def __init__(self, status_code: int = 202, body: dict | None = None):
        self.status_code = status_code
        self._body = body or {"accepted": True, "duplicate": False}

    def json(self) -> dict:
        return self._body


def test_spool_survives_a_restart_and_keeps_arrival_order(tmp_path: Path) -> None:
    spool = DeliverySpool(tmp_path)
    spool.append({"event_id": "a"}, event_type="earthquake_candidate", event_id="a")
    spool.append({"event_id": "b"}, event_type="earthquake_candidate", event_id="b")

    reopened = DeliverySpool(tmp_path)
    pending = reopened.pending()
    assert len(pending) == 2
    records = [reopened.read(path) for path in pending]
    assert [record["event_id"] for record in records if record] == ["a", "b"]


def test_spool_discards_the_oldest_entry_when_it_reaches_its_limit(tmp_path: Path) -> None:
    spool = DeliverySpool(tmp_path, max_entries=2)
    for name in ("a", "b", "c"):
        spool.append({"event_id": name}, event_type="earthquake_candidate", event_id=name)
    records = [spool.read(path) for path in spool.pending()]
    assert [record["event_id"] for record in records if record] == ["b", "c"]


def test_unreadable_spool_entry_is_dropped_instead_of_blocking_the_queue(tmp_path: Path) -> None:
    spool = DeliverySpool(tmp_path)
    broken = tmp_path / "000000000000001-0001.json"
    broken.write_text("{ truncated", encoding="utf-8")
    assert spool.read(broken) is None
    assert not broken.exists()


def test_event_is_spooled_while_the_api_is_down_and_delivered_on_recovery(
    tmp_path: Path,
) -> None:
    online = {"value": False}
    attempts: list[str] = []

    def sender(event_type: str, payload: dict) -> DeliveryOutcome:
        attempts.append(str(payload["event_id"]))
        if not online["value"]:
            raise requests.ConnectionError("API no disponible")
        return DeliveryOutcome(delivered=True)

    delivery = DurableEventDelivery(sender, DeliverySpool(tmp_path))
    assert not delivery.submit(
        {"event_id": "candidate-1"}, event_type="earthquake_candidate", event_id="candidate-1"
    )
    assert delivery.pending_count() == 1
    assert delivery.drain() == 0

    online["value"] = True
    assert delivery.drain() == 1
    assert delivery.pending_count() == 0
    assert delivery.metrics.delivered == 1
    assert delivery.metrics.spooled == 1
    assert attempts.count("candidate-1") == 3


def test_a_rejected_contract_is_not_retried_forever(tmp_path: Path) -> None:
    def sender(event_type: str, payload: dict) -> DeliveryOutcome:
        return DeliveryOutcome(delivered=False, retryable=False, detail="HTTP 422")

    delivery = DurableEventDelivery(sender, DeliverySpool(tmp_path))
    assert not delivery.submit({"event_id": "x"}, event_type="earthquake_candidate", event_id="x")
    assert delivery.pending_count() == 0


def test_expired_events_leave_the_spool_without_being_delivered(tmp_path: Path) -> None:
    def sender(event_type: str, payload: dict) -> DeliveryOutcome:
        raise AssertionError("un evento vencido no debe reenviarse")

    spool = DeliverySpool(tmp_path)
    spool.append({"event_id": "old"}, event_type="earthquake_candidate", event_id="old")
    delivery = DurableEventDelivery(sender, spool, max_age_seconds=-1)
    assert delivery.drain() == 0
    assert delivery.pending_count() == 0
    assert delivery.metrics.expired == 1


def test_dispatcher_signs_and_spools_when_the_api_refuses(tmp_path: Path, monkeypatch) -> None:
    captured: list[dict] = []

    def fake_post(url, data, timeout, headers):
        captured.append({"url": url, "data": data, "headers": headers})
        return FakeResponse(status_code=503)

    monkeypatch.setattr("eew.alerts.requests.post", fake_post)
    dispatcher = AlertDispatcher(
        AlertSettings(
            webhook_base_url="https://api.example.test",
            webhook_hmac_secret="shared-secret",
            spool_directory=str(tmp_path),
        )
    )
    dispatcher.trigger_alert(build_candidate())

    assert captured[0]["url"] == "https://api.example.test/v1/events/candidate"
    verify_signature(
        secret="shared-secret",
        timestamp=captured[0]["headers"]["X-Seismik-Timestamp"],
        signature=captured[0]["headers"]["X-Seismik-Signature"],
        body=captured[0]["data"],
        max_skew_seconds=30,
    )
    health = dispatcher.health()
    assert health["pending"] == 1
    assert health["spooled"] == 1
    assert health["last_error"] == "HTTP 503"


def test_dispatcher_counts_the_duplicate_reported_by_the_bus(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "eew.alerts.requests.post",
        lambda url, data, timeout, headers: FakeResponse(
            status_code=202, body={"accepted": True, "duplicate": True}
        ),
    )
    dispatcher = AlertDispatcher(
        AlertSettings(
            webhook_base_url="https://api.example.test",
            webhook_hmac_secret="shared-secret",
            spool_directory=str(tmp_path),
        )
    )
    dispatcher.trigger_alert(build_candidate())
    health = dispatcher.health()
    assert health["delivered"] == 1
    assert health["duplicates"] == 1
    assert health["pending"] == 0


def test_official_updates_use_their_own_route(tmp_path: Path, monkeypatch) -> None:
    urls: list[str] = []
    monkeypatch.setattr(
        "eew.alerts.requests.post",
        lambda url, data, timeout, headers: urls.append(url) or FakeResponse(),
    )
    dispatcher = AlertDispatcher(
        AlertSettings(
            webhook_base_url="https://api.example.test",
            webhook_hmac_secret="shared-secret",
            spool_directory=str(tmp_path),
        )
    )
    assert dispatcher._url_for("official_report_update") == (
        "https://api.example.test/v1/events/official-update"
    )
    dispatcher.trigger_alert(build_candidate())
    assert urls == ["https://api.example.test/v1/events/candidate"]


def test_stdout_contract_is_preserved_without_a_configured_api(capsys) -> None:
    dispatcher = AlertDispatcher(AlertSettings())
    dispatcher.trigger_alert(build_candidate("candidate-stdout"))
    printed = json.loads(capsys.readouterr().out.strip())
    assert printed["event_id"] == "candidate-stdout"


def test_unsigned_delivery_is_refused(monkeypatch) -> None:
    def fail(*_args, **_kwargs):
        raise AssertionError("no debe salir tráfico sin firma")

    monkeypatch.setattr("eew.alerts.requests.post", fail)
    dispatcher = AlertDispatcher(AlertSettings(webhook_base_url="https://api.example.test"))
    dispatcher.trigger_alert(build_candidate())


@pytest.mark.parametrize(
    ("status_code", "retryable"),
    [(500, True), (503, True), (429, True), (408, True), (422, False), (401, False)],
)
def test_status_codes_are_classified_for_retry(
    tmp_path: Path, monkeypatch, status_code: int, retryable: bool
) -> None:
    monkeypatch.setattr(
        "eew.alerts.requests.post",
        lambda url, data, timeout, headers: FakeResponse(status_code=status_code),
    )
    dispatcher = AlertDispatcher(
        AlertSettings(
            webhook_base_url="https://api.example.test",
            webhook_hmac_secret="shared-secret",
            spool_directory=str(tmp_path),
        )
    )
    dispatcher.trigger_alert(build_candidate())
    assert dispatcher.health()["pending"] == (1 if retryable else 0)
