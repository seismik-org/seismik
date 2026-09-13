from integrations.x_publisher import bulletin_text, eligible


def official_event(magnitude: float = 3.2) -> dict:
    return {"type": "official_report_available", "event_id": "official-1", "preferred_report": {"magnitude": magnitude, "place": "Los Santos, Colombia", "source": "SGC", "official_url": "https://example.org/event", "origin_time": "2026-09-12T12:00:00Z"}}


def test_only_official_events_are_eligible() -> None:
    assert eligible(official_event(), 2.5)
    assert not eligible({"type": "earthquake_candidate", "event_id": "candidate", "magnitude": 6.0}, 2.5)
    assert not eligible(official_event(2.4), 2.5)


def test_bulletin_is_short_and_source_attributed() -> None:
    text = bulletin_text(official_event())
    assert "M3.2" in text and "Fuente: SGC" in text and len(text) <= 280
