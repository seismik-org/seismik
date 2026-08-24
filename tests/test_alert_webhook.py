from __future__ import annotations

from eew.alerts import AlertDispatcher
from eew.config import AlertSettings
from eew.models import EarthquakeCandidate, StationTrigger
from api.security import verify_signature


class FakeResponse:
    status_code = 202

    def raise_for_status(self) -> None:
        pass


def test_phase1_dispatcher_signs_exact_body_and_selects_candidate_route(monkeypatch) -> None:
    captured = {}

    def fake_post(url, data, timeout, headers):
        captured.update(url=url, data=data, timeout=timeout, headers=headers)
        return FakeResponse()

    monkeypatch.setattr("eew.alerts.requests.post", fake_post)
    trigger = StationTrigger(
        provider_id="test", country_code="CO", zone_id="andes", station_id="CM.A",
        stream_id="CM.A.00.HHZ", trigger_time="2026-01-01T00:00:00Z",
        received_at="2026-01-01T00:00:01Z", sta_lta_ratio=4.2,
    )
    event = EarthquakeCandidate(
        event_id="5c0750ca-8d5e-4f87-995e-03b4a2f9d947",
        type="earthquake_candidate", status="unlocated_unreviewed", zone_id="andes",
        country_code="CO", country_codes=("CO",), detected_at="2026-01-01T00:00:02Z",
        coincidence_window_seconds=15, required_stations=1, station_count=1,
        stations=(trigger,),
    )
    dispatcher = AlertDispatcher(AlertSettings(
        webhook_base_url="https://api.example.test", webhook_hmac_secret="shared-secret",
    ))
    dispatcher.trigger_alert(event)
    assert captured["url"] == "https://api.example.test/v1/events/candidate"
    verify_signature(
        secret="shared-secret",
        timestamp=captured["headers"]["X-Seismik-Timestamp"],
        signature=captured["headers"]["X-Seismik-Signature"],
        body=captured["data"],
        max_skew_seconds=30,
    )
