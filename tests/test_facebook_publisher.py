from datetime import datetime, timezone
from typing import Any

import pytest
from fakeredis.aioredis import FakeRedis
from test_x_publisher import FakeXResponse, official_event

from api.config import AppSettings
from eew.models import OfficialReport
from integrations import facebook_publisher
from integrations.facebook_publisher import FacebookPublisher
from integrations.x_publisher import XPublisher


def publisher(**options: Any) -> FacebookPublisher:
    settings = AppSettings(
        facebook_publisher_enabled=True,
        facebook_publisher_dry_run=False,
        facebook_page_id="61595218284668",
        facebook_page_access_token="test-only",
        **options,
    )
    return FacebookPublisher(FakeRedis(decode_responses=True), settings)


@pytest.mark.asyncio
async def test_facebook_publishes_card_with_page_token_only_in_header(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict]] = []

    def post(url: str, **kwargs: Any) -> FakeXResponse:
        calls.append((url, kwargs))
        return FakeXResponse(200, {"post_id": "61595218284668_123"})

    monkeypatch.setattr(facebook_publisher.requests, "post", post)
    pub = publisher()

    async def card(_event: dict) -> bytes:
        return b"PNG"

    monkeypatch.setattr(pub, "_render_card", card)
    await pub._publish(official_event(), "seismik:facebook:published:official-1")
    url, request = calls[0]
    assert url.endswith("/61595218284668/photos")
    assert "test-only" not in url
    assert request["headers"] == {"Authorization": "Bearer test-only"}
    assert request["files"]["source"] == ("boletin.png", b"PNG", "image/png")
    assert "Boletín sísmico Seismik" in request["data"]["message"]
    audit = await pub.redis.xrange("stream:seismik:facebook-audit")
    assert audit[0][1]["post_id"] == "61595218284668_123"
    assert "test-only" not in str(audit)
    assert not await pub.redis.exists("stream:seismik:x-audit")


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [200, 400, 503, None])
async def test_fallback_and_uncertain_delivery_do_not_blindly_retry(
    monkeypatch: pytest.MonkeyPatch, status: int | None,
) -> None:
    def post(url: str, **kwargs: Any) -> FakeXResponse:
        assert url.endswith("/feed")
        assert kwargs["files"] is None
        if status is None:
            raise facebook_publisher.requests.Timeout("sensitive response")
        return FakeXResponse(status, {})

    pub = publisher()

    async def card(_event: dict) -> None:
        return None

    monkeypatch.setattr(pub, "_render_card", card)
    monkeypatch.setattr(facebook_publisher.requests, "post", post)
    key = "seismik:facebook:published:official-1"
    await pub.redis.set(key, "1")
    if status == 400:
        with pytest.raises(RuntimeError, match="HTTP 400"):
            await pub._publish(official_event(), key)
        assert not await pub.redis.exists(key)
    else:
        await pub._publish(official_event(), key)
        assert await pub.redis.get(key) == "uncertain"
        audit = await pub.redis.xrange("stream:seismik:facebook-audit")
        assert audit[0][1]["action"] == "delivery_uncertain"
        assert "sensitive" not in str(audit)


@pytest.mark.asyncio
async def test_same_quake_posts_on_both_platforms_but_only_once_each(monkeypatch: pytest.MonkeyPatch) -> None:
    fb = publisher()
    x = XPublisher(fb.redis, fb.settings)
    posts: list[str] = []

    async def publish(_event: dict, key: str) -> None:
        posts.append(key)

    monkeypatch.setattr(fb, "_publish", publish)
    monkeypatch.setattr(x, "_publish", publish)
    event = official_event()
    report = OfficialReport(**event["preferred_report"], jurisdiction="CO", updated_at="2026-09-12T12:00:00Z")
    origin = datetime(2026, 9, 12, 12, tzinfo=timezone.utc)
    for pub in (x, fb, x, fb):
        await pub._post_catalog_event(event, report, origin)
    assert posts == ["seismik:x:published:official-1", "seismik:facebook:published:official-1"]
    assert fb._failure_key("a") != x._failure_key("a")


@pytest.mark.asyncio
async def test_disabled_facebook_does_not_poll_or_send(monkeypatch: pytest.MonkeyPatch) -> None:
    pub = FacebookPublisher(FakeRedis(), AppSettings())

    async def poll() -> None:
        pytest.fail("Facebook disabled must not query catalogs")

    monkeypatch.setattr(pub, "_run_catalogs", poll)
    await pub.run()


@pytest.mark.asyncio
async def test_missing_token_cannot_start_live_publisher() -> None:
    pub = FacebookPublisher(FakeRedis(), AppSettings(
        facebook_publisher_enabled=True, facebook_publisher_dry_run=False,
        facebook_page_id="61595218284668",
    ))
    with pytest.raises(ValueError, match="credencial"):
        await pub.run()
