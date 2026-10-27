from __future__ import annotations

import asyncio
import hashlib
import json

import httpx
import pytest
from fakeredis.aioredis import FakeRedis
from fastapi import Depends, FastAPI

from api import developer_keys, history
from api.billing import summary
from api.config import AppSettings
from api.dependencies import ApiPrincipal, require_events_read
from api.developer_plans import assign_plan, quota_usage


async def make_app(monkeypatch, **settings):
    app = FastAPI()
    app.state.redis = FakeRedis(decode_responses=True)
    app.state.settings = AppSettings(**settings)
    app.include_router(developer_keys.router)
    for uid in ('one', 'two'):
        await app.state.redis.set(f'seismik:oauth:session:session-{uid}',json.dumps({'uid':uid,'email':uid+'@example.com','name':uid}))
    app.state.calls = []

    async def query(**kwargs):
        app.state.calls.append(kwargs)
        return {'events':[{'event_id':'example','magnitude':4.1,'latitude':None}], 'sources':[], 'errors':[]}

    monkeypatch.setattr(history,'official_history',query)

    @app.get('/data')
    async def data(principal: ApiPrincipal = Depends(require_events_read)):
        return {'subject':principal.subject}

    return app


@pytest.mark.asyncio
async def test_explorer_requires_a_valid_portal_session_not_an_api_key(monkeypatch):
    app = await make_app(monkeypatch,consumer_api_key='internal-secret')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://devs.seismik.org') as client:
        for headers in ({},{'X-Seismik-API-Key':'internal-secret'},{'Authorization':'Bearer other'}):
            assert (await client.get('/v1/developer/explore/history',headers=headers)).status_code == 401
        client.cookies.set('seismik_session','expired')
        assert (await client.get('/v1/developer/explore/history')).status_code == 401
    assert app.state.calls == []
    assert (await summary(app.state.redis,'one'))['requests'] == 0


@pytest.mark.asyncio
async def test_explorer_uses_session_owner_charges_once_and_leaves_keys_uncreated(monkeypatch):
    app = await make_app(monkeypatch)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://devs.seismik.org',cookies={'seismik_session':'session-one'}) as client:
        response = await client.get('/v1/developer/explore/history?uid=two&plan=ultra&days=30&limit=500&minimum_magnitude=4&sources=sgc_colombia')
    assert response.status_code == 200
    assert response.headers['Cache-Control'] == 'no-store'
    assert response.headers['Vary'] == 'Cookie'
    assert len(app.state.calls) == 1
    call = app.state.calls[0]
    assert (call['days'],call['limit'],call['minimum_magnitude'],call['_authorized'].subject) == (30,500,4,'one')
    assert (await summary(app.state.redis,'one'))['events_read'] == 1
    assert (await summary(app.state.redis,'two'))['requests'] == 0
    assert await app.state.redis.keys('seismik:developer-key:*') == []
    assert 'sk_live_' not in response.text


@pytest.mark.asyncio
async def test_keys_and_portal_share_the_same_minute_quota(monkeypatch):
    app = await make_app(monkeypatch)
    await assign_plan(app.state.redis,'one','pro',actor='test',reason='test',requests_per_minute=1)
    key = 'sk_live_test'
    digest = hashlib.sha256(key.encode()).hexdigest()
    await app.state.redis.hset('seismik:developer-key:'+digest,mapping={'uid':'one','key_id':'key','scopes':'events:read','status':'active'})
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://devs.seismik.org',cookies={'seismik_session':'session-one'}) as client:
        assert (await client.get('/data',headers={'X-Seismik-API-Key':key})).status_code == 200
        response = await client.get('/v1/developer/explore/history')
        assert response.status_code == 429
        assert response.headers['Retry-After'] == '60'
    assert (await summary(app.state.redis,'one'))['requests'] == 1
    assert app.state.calls == []


@pytest.mark.asyncio
async def test_portal_month_cap_is_atomic_and_plan_changes_do_not_reset_it(monkeypatch):
    app = await make_app(monkeypatch)
    await assign_plan(app.state.redis,'one','ultra',actor='test',reason='test',requests_per_month=3)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://devs.seismik.org',cookies={'seismik_session':'session-one'}) as client:
        replies = await asyncio.gather(*(client.get('/v1/developer/explore/history') for _ in range(12)))
        assert sum(r.status_code == 200 for r in replies) == 3
        assert sum(r.status_code == 429 for r in replies) == 9
        await assign_plan(app.state.redis,'one','enterprise',actor='test',reason='test',requests_per_month=3)
        assert (await client.get('/v1/developer/explore/history')).status_code == 429
    assert (await quota_usage(app.state.redis,'one'))['month']['used'] == 3
    assert len(app.state.calls) == 3


@pytest.mark.asyncio
async def test_cross_site_requests_and_invalid_filters_do_not_spend_quota(monkeypatch):
    app = await make_app(monkeypatch)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://devs.seismik.org',cookies={'seismik_session':'session-one'}) as client:
        for headers in ({'Sec-Fetch-Site':'cross-site'},{'Sec-Fetch-Site':'same-site'},{'Origin':'https://evil.example'}):
            assert (await client.get('/v1/developer/explore/history',headers=headers)).status_code == 403
        for query in ('days=999','limit=9999','minimum_magnitude=-1'):
            assert (await client.get('/v1/developer/explore/history?'+query)).status_code == 422
    assert (await summary(app.state.redis,'one'))['requests'] == 0


@pytest.mark.asyncio
async def test_deleted_session_cannot_keep_reading(monkeypatch):
    app = await make_app(monkeypatch)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='https://devs.seismik.org',cookies={'seismik_session':'session-one'}) as client:
        assert (await client.get('/v1/developer/explore/history')).status_code == 200
        await app.state.redis.delete('seismik:oauth:session:session-one')
        assert (await client.get('/v1/developer/explore/history')).status_code == 401
    assert (await summary(app.state.redis,'one'))['requests'] == 1
