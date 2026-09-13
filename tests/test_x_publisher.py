from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

import pytest
from fakeredis.aioredis import FakeRedis

from api.config import AppSettings
from eew.simulation import drill_sequence
from integrations import x_publisher
from integrations.x_publisher import (
    AUDIT_STREAM,
    XPublisher,
    bulletin_text,
    eligible,
    is_simulated,
)


def official_event(magnitude: Any = 3.2, **report: Any) -> dict:
    """Mismos campos que `eew.models.OfficialReportUpdate.to_dict()`."""
    preferred = {
        "source_id": "sgc_colombia",
        "agency": "Servicio Geológico Colombiano (SGC)",
        "official_event_id": "sgc2026abc",
        "magnitude": magnitude,
        "magnitude_type": "ML",
        "place": "Los Santos, Colombia",
        "latitude": 6.75,
        "longitude": -73.1,
        "depth_km": 150.0,
        "review_status": "reviewed",
        "official_url": "https://www.sgc.gov.co/detallesismo/sgc2026abc/resumen",
        "origin_time": "2026-09-12T12:00:00Z",
        **report,
    }
    return {
        "type": "official_report_update",
        "status": "official_report_available",
        "event_id": "official-1",
        "candidate_event_id": "candidate-1",
        "preferred_report": preferred,
    }


def test_only_official_events_are_eligible() -> None:
    assert eligible(official_event(), 2.5)
    assert not eligible({"type": "earthquake_candidate", "event_id": "candidate", "magnitude": 6.0}, 2.5)
    assert not eligible(official_event(2.4), 2.5)


def test_malformed_official_events_are_not_eligible() -> None:
    assert not eligible(official_event("desconocida"), 2.5)
    assert not eligible({**official_event(), "preferred_report": "no es un objeto"}, 2.5)
    assert not eligible({**official_event(), "event_id": ""}, 2.5), "compartiría la marca de publicado"


def test_withdrawn_reports_are_not_eligible() -> None:
    assert not eligible(official_event(review_status="deleted"), 2.5)


def test_drills_are_never_eligible() -> None:
    """Un simulacro publicado anunciaría en la cuenta pública un sismo que no ocurrió."""
    _candidate, drill = drill_sequence("bogota")

    assert is_simulated(drill)
    assert not eligible(drill, 0.0)
    assert not is_simulated(official_event())


def test_the_post_text_names_the_agency_and_has_no_link() -> None:
    """Con URL X cobra $0.200 por post en vez de $0.015; el enlace va en la imagen."""
    text = bulletin_text(official_event())

    assert text.startswith("Boletín sísmico Seismik · M3.2")
    assert "Fuente: SGC" in text
    assert "12 de septiembre de 2026, 12:00 UTC (07:00 a. m. hora de Colombia)" in text
    assert "http" not in text and "sgc.gov.co" not in text
    assert len(text) <= 280


def test_preliminary_reports_say_so_in_the_post() -> None:
    assert bulletin_text(official_event(review_status="automatic")).startswith("Boletín preliminar Seismik")


def test_a_long_place_is_trimmed_to_fit_the_post() -> None:
    text = bulletin_text(official_event(place="Zona rural muy extensa " * 20))

    assert len(text) <= 280
    assert "…" in text
    assert text.endswith("Fuente: SGC")


# --- Consumo del stream ------------------------------------------------------


class FakeXResponse:
    def __init__(self, status_code: int, body: dict[str, Any] | None = None) -> None:
        self.status_code = status_code
        self.body = body if body is not None else {"data": {"id": "post-1"}}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise x_publisher.requests.HTTPError(f"HTTP {self.status_code}")

    def json(self) -> dict[str, Any]:
        return self.body


def rejected(*_args: object, **_kwargs: object) -> FakeXResponse:
    return FakeXResponse(503)


def unreachable(*_args: object, **_kwargs: object) -> FakeXResponse:
    raise x_publisher.requests.ConnectionError("sin red")


async def publisher(**overrides: Any) -> XPublisher:
    options: dict[str, Any] = {
        "x_publisher_enabled": True,
        "x_publisher_dry_run": False,
        "x_publisher_images": False,
        "pending_claim_idle_ms": 1_000,
        **overrides,
    }
    pub = XPublisher(FakeRedis(decode_responses=True), AppSettings(**options))
    await pub.ensure_group()
    return pub


async def deliver(pub: XPublisher, fields: dict[str, str]) -> str:
    """Encola un mensaje y lo procesa como lo haría `run`."""
    settings = pub.settings
    await pub.redis.xadd(settings.integration_stream, fields)
    rows = await pub.redis.xreadgroup(
        settings.x_publisher_group, settings.x_publisher_consumer_name, {settings.integration_stream: ">"}
    )
    message_id = ""
    for _stream, items in rows:
        for message_id, item in items:
            await pub._handle(message_id, item)
    return message_id


async def pending(pub: XPublisher) -> int:
    info = await pub.redis.xpending(pub.settings.integration_stream, pub.settings.x_publisher_group)
    return int(info["pending"])


async def audit_entries(pub: XPublisher) -> list[dict[str, str]]:
    return [fields for _id, fields in await pub.redis.xrange(AUDIT_STREAM)]


async def audit_actions(pub: XPublisher) -> list[str]:
    return [entry["action"] for entry in await audit_entries(pub)]


@pytest.mark.asyncio
async def test_the_bulletin_is_posted_with_its_card(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def post(url: str, **kwargs: Any) -> FakeXResponse:
        calls.append((url, kwargs))
        if url == x_publisher.X_MEDIA_UPLOAD_URL:
            return FakeXResponse(200, {"data": {"id": "1880028106020515840", "media_key": "3_1880028106020515840"}})
        return FakeXResponse(201)

    monkeypatch.setattr(x_publisher.requests, "post", post)
    monkeypatch.setattr(x_publisher, "render_bulletin_card", lambda event: b"PNG del boletin")
    pub = await publisher(x_publisher_images=True)

    await deliver(pub, {"payload": json.dumps(official_event())})

    (upload_url, upload), (post_url, tweet) = calls
    assert upload_url == x_publisher.X_MEDIA_UPLOAD_URL
    assert upload["files"]["media"][1] == b"PNG del boletin"
    assert upload["data"] == {"media_category": "tweet_image"}
    assert post_url == x_publisher.X_POST_URL
    assert tweet["json"]["media"] == {"media_ids": ["1880028106020515840"]}
    assert "http" not in tweet["json"]["text"]
    assert await audit_actions(pub) == ["published"]


@pytest.mark.asyncio
async def test_a_card_that_fails_to_render_still_posts_the_text(monkeypatch: pytest.MonkeyPatch) -> None:
    urls: list[str] = []

    def broken(_event: object) -> bytes:
        raise RuntimeError("fuente dañada")

    def post(url: str, **_kwargs: Any) -> FakeXResponse:
        urls.append(url)
        return FakeXResponse(201)

    monkeypatch.setattr(x_publisher, "render_bulletin_card", broken)
    monkeypatch.setattr(x_publisher.requests, "post", post)
    pub = await publisher(x_publisher_images=True)

    await deliver(pub, {"payload": json.dumps(official_event())})

    assert urls == [x_publisher.X_POST_URL]
    assert [entry.get("image") for entry in await audit_entries(pub)] == ["no"]


@pytest.mark.asyncio
async def test_a_rejected_image_upload_is_retried_like_a_rejected_post(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(x_publisher.requests, "post", rejected)
    monkeypatch.setattr(x_publisher, "render_bulletin_card", lambda event: b"PNG")
    pub = await publisher(x_publisher_images=True)

    await deliver(pub, {"payload": json.dumps(official_event())})

    assert await pending(pub) == 1
    assert not await pub.redis.exists("seismik:x:published:official-1")


@pytest.mark.asyncio
async def test_a_dry_run_renders_the_real_card_without_posting(monkeypatch: pytest.MonkeyPatch) -> None:
    def post(*_args: object, **_kwargs: object) -> FakeXResponse:
        raise AssertionError("en modo de prueba no se llama a X")

    monkeypatch.setattr(x_publisher.requests, "post", post)
    pub = await publisher(x_publisher_enabled=False, x_publisher_dry_run=True, x_publisher_images=True)

    await deliver(pub, {"payload": json.dumps(official_event())})

    [entry] = await audit_entries(pub)
    assert entry["action"] == "dry_run"
    assert int(entry["image_bytes"]) > 50_000


@pytest.mark.asyncio
async def test_a_drill_is_audited_and_never_posted(monkeypatch: pytest.MonkeyPatch) -> None:
    def post(*_args: object, **_kwargs: object) -> FakeXResponse:
        raise AssertionError("un simulacro no debe llegar a X")

    monkeypatch.setattr(x_publisher.requests, "post", post)
    pub = await publisher()
    _candidate, drill = drill_sequence("bogota")

    await deliver(pub, {"payload": json.dumps(drill)})

    assert await pending(pub) == 0
    assert await audit_actions(pub) == ["skipped_drill"]


@pytest.mark.asyncio
async def test_an_unreadable_message_is_discarded_without_stopping_the_service() -> None:
    pub = await publisher()

    await deliver(pub, {"sin_payload": "1"})
    await deliver(pub, {"payload": "{no es json"})

    assert await pending(pub) == 0, "reintentarlo no lo arregla"
    assert await audit_actions(pub) == ["skipped_malformed", "skipped_malformed"]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [rejected, unreachable])
async def test_a_failed_post_stays_pending_and_is_published_after_a_restart(
    monkeypatch: pytest.MonkeyPatch, failure: Callable[..., FakeXResponse]
) -> None:
    calls: list[int] = []

    def post(*args: object, **kwargs: object) -> FakeXResponse:
        calls.append(1)
        return failure(*args, **kwargs) if len(calls) == 1 else FakeXResponse(201)

    monkeypatch.setattr(x_publisher.requests, "post", post)
    pub = await publisher()

    await deliver(pub, {"payload": json.dumps(official_event())})

    assert await pending(pub) == 1, "sin confirmar, para reintentarlo"
    assert not await pub.redis.exists("seismik:x:published:official-1"), "no se dio por publicado"

    # Tras un reinicio `xreadgroup` con ">" ya no lo entrega: lo retoma la
    # recuperación de pendientes cuando supera `pending_claim_idle_ms`.
    restarted = XPublisher(pub.redis, pub.settings)
    await asyncio.sleep(1.1)
    await restarted._recover_pending()

    assert len(calls) == 2
    assert await pending(pub) == 0
    assert await audit_actions(pub) == ["published"]


@pytest.mark.asyncio
async def test_after_the_last_attempt_the_failure_is_audited_and_acknowledged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(x_publisher.requests, "post", rejected)
    pub = await publisher(integration_delivery_max_attempts=2)
    fields = {"payload": json.dumps(official_event())}

    message_id = await deliver(pub, fields)
    await pub._handle(message_id, fields)

    assert await pending(pub) == 0
    assert await audit_actions(pub) == ["failed"]
    assert not await pub.redis.exists(f"seismik:x:failures:{message_id}")


@pytest.mark.asyncio
async def test_a_redis_error_in_the_loop_does_not_stop_the_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pub = await publisher()
    reads = 0

    async def flaky_read(*_args: object, **_kwargs: object) -> list[Any]:
        nonlocal reads
        reads += 1
        if reads == 1:
            raise ConnectionError("Redis no responde")
        pub.stop_event.set()
        return []

    monkeypatch.setattr(pub.redis, "xreadgroup", flaky_read)

    await asyncio.wait_for(pub.run(), timeout=5)

    assert reads == 2
