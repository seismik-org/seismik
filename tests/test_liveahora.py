"""Calendar privacy, authorization, input boundaries and durable edit conflicts."""
from __future__ import annotations

import base64
import copy
import io
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fakeredis.aioredis import FakeRedis
from fastapi import FastAPI
from PIL import Image

from api import liveahora
from api.config import AppSettings
from api.edge_origin import EdgeOriginGuard
from api.oauth import _finish_login


class Calendar:
    def __init__(self):
        self.data = None
        self.media = {}
        self._client = self

    def transaction(self):
        return self

    def get(self, transaction=None):
        return self

    def to_dict(self):
        return copy.deepcopy(self.data)

    def collection(self, name):
        return self

    def document(self, key):
        return Media(self.media, key)

    def delete(self, reference):
        reference.values.pop(reference.key, None)

    def set(self, reference, data):
        if isinstance(reference, Media):
            reference.values[reference.key] = copy.deepcopy(data)
        else:
            self.data = copy.deepcopy(data)


class Media:
    def __init__(self, values, key):
        self.values, self.key = values, key

    def get(self, transaction=None):
        return self

    def to_dict(self):
        return copy.deepcopy(self.values.get(self.key))


def thumbnail(color="red"):
    output = io.BytesIO()
    image = Image.new("RGB", (1600, 900), color)
    image.save(output, "PNG", pnginfo=None)
    return base64.b64encode(output.getvalue()).decode()


@pytest.mark.asyncio
async def test_thumbnail_lifecycle_privacy_and_conflicts(monkeypatch):
    app, client = await setup(monkeypatch)
    async with client:
        result = await client.post("/v1/liveahora/admin/events", json={
            "revision": 0, "event": event(status="draft"), "thumbnail": thumbnail()})
        assert result.status_code == 200
        key = result.json()["id"]
        saved = app.state.liveahora_store.data["events"][key]
        path = saved["image"]
        image = await client.get(path)
        assert image.status_code == 200
        assert image.headers["content-type"] == "image/webp"
        assert image.headers["cache-control"] == "no-store"
        with Image.open(io.BytesIO(image.content)) as decoded:
            assert decoded.size == (1280, 720)
            assert not decoded.getexif()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=liveahora.ORIGIN) as public:
            assert (await public.get(path)).status_code == 404
            saved["status"] = "scheduled"
            assert (await client.put(f"/v1/liveahora/admin/events/{key}", json={
                "revision": 1, "event": saved})).status_code == 200
            assert (await public.get(path)).status_code == 200
            old_media = copy.deepcopy(app.state.liveahora_store.media)
            assert (await client.put(f"/v1/liveahora/admin/events/{key}", json={
                "revision": 1, "event": saved, "thumbnail": thumbnail("blue")})).status_code == 409
            assert app.state.liveahora_store.media == old_media
            assert (await client.put(f"/v1/liveahora/admin/events/{key}", json={
                "revision": 2, "event": saved, "thumbnail": thumbnail("blue")})).status_code == 200
            assert (await public.get(path)).status_code == 404
        # Changing back to a local asset must not leave media behind after deletion.
        saved["image"] = "/assets/liveahora/logo.webp"
        assert (await client.put(f"/v1/liveahora/admin/events/{key}", json={
            "revision": 3, "event": saved})).status_code == 200
        assert (await client.delete(f"/v1/liveahora/admin/events/{key}?revision=4")).status_code == 200
        assert not app.state.liveahora_store.media


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["not base64!", base64.b64encode(b"<svg onload='evil'/>").decode()])
async def test_invalid_thumbnail_does_not_create_event(monkeypatch, value):
    app, client = await setup(monkeypatch)
    async with client:
        response = await client.post("/v1/liveahora/admin/events", json={
            "revision": 0, "event": event(), "thumbnail": value})
        assert response.status_code == 422
        assert app.state.liveahora_store.data is None


@pytest.mark.asyncio
async def test_thumbnail_cannot_reference_another_event_and_body_is_bounded(monkeypatch):
    _, client = await setup(monkeypatch)
    async with client:
        forged = f"/v1/liveahora/images/{'a' * 24}/{'b' * 64}.webp"
        assert (await client.post("/v1/liveahora/admin/events", json={
            "revision": 0, "event": event(image=forged)})).status_code == 422
        assert (await client.post("/v1/liveahora/admin/events", content=b"x" * (liveahora.MAX_BODY + 1))).status_code == 413


def event(**changes):
    now = datetime.now(timezone.utc)
    return {"title": "Encuentro de prueba", "description": "Deporte universitario",
            "starts_at": (now + timedelta(days=1)).isoformat(),
            "ends_at": (now + timedelta(days=1, hours=2)).isoformat(),
            "platform": "youtube", "url": "https://youtube.com/LiveAhoraES",
            "status": "scheduled", "rights_confirmed": True, **changes}


async def setup(monkeypatch, email="liveahora@seismik.org", **settings):
    monkeypatch.setattr(liveahora.firestore, "transactional", lambda fn: fn)
    app = FastAPI()
    app.state.settings = AppSettings(integrity_verification_enabled=True,
                                    webhook_hmac_secret="test-webhook", crowd_master_secret="test-crowd",
                                    integration_webhook_master_secret="test-integration",
                                    consumer_api_key="test-consumer", **settings)
    app.state.redis = FakeRedis(decode_responses=True)
    app.state.liveahora_store = Calendar()
    app.include_router(liveahora.router)
    app.add_middleware(EdgeOriginGuard, secret=app.state.settings.edge_origin_secret.get_secret_value())
    await app.state.redis.set("seismik:oauth:session:known", json.dumps({
        "uid": "owner-uid", "email": email, "name": "Owner"}), ex=3600)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=liveahora.ORIGIN,
                              headers={"Cookie": "seismik_session=known", "Origin": liveahora.ORIGIN,
                                       "X-LiveAhora-Admin": "1"})
    return app, client


@pytest.mark.asyncio
async def test_session_and_owner_are_required(monkeypatch):
    app, client = await setup(monkeypatch)
    async with client:
        assert (await client.get("/v1/liveahora/admin/events")).json()["email"] == "liveahora@seismik.org"
        await app.state.redis.delete("seismik:oauth:session:known")
        assert (await client.get("/v1/liveahora/admin/events")).status_code == 401
    _, client = await setup(monkeypatch, email="viewer@example.com")
    async with client:
        assert (await client.post("/v1/liveahora/admin/events", json={"revision": 0, "event": event()})).status_code == 403


@pytest.mark.asyncio
async def test_crud_conflicts_and_draft_privacy(monkeypatch):
    app, client = await setup(monkeypatch)
    async with client:
        result = await client.post("/v1/liveahora/admin/events", json={"revision": 0, "event": event(status="draft", rights_confirmed=False)})
        assert result.status_code == 200
        event_id = result.json()["id"]
        assert (await client.get("/v1/liveahora/events")).json()["events"] == []
        assert len((await client.get("/v1/liveahora/admin/events")).json()["events"]) == 1
        result = await client.put(f"/v1/liveahora/admin/events/{event_id}", json={"revision": 1, "event": event()})
        assert result.json()["revision"] == 2
        public = (await client.get("/v1/liveahora/events")).json()["events"]
        assert len(public) == 1 and "rights_confirmed" not in public[0]
        stale = await client.put(f"/v1/liveahora/admin/events/{event_id}", json={"revision": 1, "event": event(title="Stale change")})
        assert stale.status_code == 409
        assert app.state.liveahora_store.data["events"][event_id]["title"] == "Encuentro de prueba"
        assert (await client.delete(f"/v1/liveahora/admin/events/{event_id}?revision=1")).status_code == 409
        assert (await client.delete(f"/v1/liveahora/admin/events/{event_id}?revision=2")).status_code == 200
        assert (await client.get("/v1/liveahora/events")).json()["events"] == []
        assert (await client.put('/v1/liveahora/admin/events/' + 'a'*24, json={"revision": 3, "event": event()})).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("headers", [
    {"Origin": "https://attacker.example"}, {"X-LiveAhora-Admin": ""},
    {"Sec-Fetch-Site": "cross-site"},
])
async def test_cross_origin_writes_are_blocked(monkeypatch, headers):
    app, client = await setup(monkeypatch)
    async with client:
        response = await client.post('/v1/liveahora/admin/events', headers=headers, json={"revision": 0, "event": event()})
        assert response.status_code == 403
        assert app.state.liveahora_store.data is None


@pytest.mark.asyncio
async def test_production_requires_edge_secret_and_optional_uid(monkeypatch):
    _, client = await setup(monkeypatch, environment="production", edge_origin_secret="test-only")
    async with client:
        assert (await client.get('/v1/liveahora/admin/events')).status_code == 403
        response = await client.get('/v1/liveahora/admin/events', headers={"X-Seismik-Origin-Auth": "test-only"})
        assert response.status_code == 200
        assert response.headers['cache-control'] == 'no-store'
    _, client = await setup(monkeypatch, liveahora_admin_uid="another-identity")
    async with client:
        assert (await client.get('/v1/liveahora/admin/events')).status_code == 403


@pytest.mark.asyncio
async def test_public_calendar_sorts_and_excludes_expired_and_unpublished(monkeypatch):
    app, client = await setup(monkeypatch)
    now = datetime.now(timezone.utc)
    app.state.liveahora_store.data = {"revision": 1, "events": {
        "later": event(starts_at=(now+timedelta(days=3)).isoformat(), ends_at=(now+timedelta(days=3,hours=2)).isoformat()),
        "sooner": event(status="cancelled"),
        "expired": event(starts_at=(now-timedelta(hours=3)).isoformat(), ends_at=(now-timedelta(hours=1)).isoformat()),
        "draft": event(status="draft", rights_confirmed=False),
        "done": event(status="finished"),
    }}
    async with client:
        result = await client.get('/v1/liveahora/events', headers={"Cookie": ""})
        assert [row['id'] for row in result.json()['events']] == ['sooner', 'later']
        assert 'email' not in result.text and 'revision' not in result.text


@pytest.mark.parametrize("changes", [
    {"url": "javascript:alert(1)"}, {"url": "https://youtube.com.attacker.example/video"},
    {"url": "https://user:pass@youtube.com/video"}, {"url": "https://youtube.com:8080/video"},
    {"platform": "kick", "url": "https://youtube.com/LiveAhoraES"},
    {"rights_confirmed": False}, {"image": "https://tracker.example/image.png"},
    {"starts_at": "2030-01-01T12:00:00"}, {"ends_at": "2020-01-01T12:00:00Z"},
])
def test_event_rejects_unsafe_or_unpublishable_values(changes):
    with pytest.raises(ValueError):
        liveahora.Event.model_validate(event(**changes))


@pytest.mark.asyncio
async def test_login_uses_central_auth_and_fixed_return(monkeypatch):
    app, client = await setup(monkeypatch)

    @app.get('/finish')
    async def finish(request: liveahora.Request):
        return await _finish_login(request, {"uid": "owner", "email": "liveahora@seismik.org", "name": "Owner"}, None)

    async with client:
        login = await client.get('/v1/liveahora/login')
        assert login.headers['location'] == 'https://auth.seismik.org/id'
        assert 'Secure' in login.headers['set-cookie'] and 'HttpOnly' in login.headers['set-cookie']
        result = await client.get('/finish', headers={"Cookie": "seismik_after_login=liveahora"})
        assert result.headers['location'] == 'https://liveahora.seismik.org/admin/'
        assert 'Max-Age=0' in result.headers.get_list('set-cookie')[-1]
        unknown = await client.get('/finish', headers={"Cookie": "seismik_after_login=https://attacker.example"})
        assert unknown.headers['location'] == 'https://devs.seismik.org/'


@pytest.mark.asyncio
async def test_storage_failures_are_not_presented_as_an_empty_calendar(monkeypatch):
    app, client = await setup(monkeypatch)
    app.state.liveahora_store.get = lambda **kwargs: (_ for _ in ()).throw(RuntimeError('private storage error'))
    async with client:
        result = await client.get('/v1/liveahora/events')
        assert result.status_code == 503 and 'private storage error' not in result.text
