from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fakeredis.aioredis import FakeRedis
from test_family_api import account, app_for, client_for, family_with_member


async def context(client, headers):
    circle = (await client.get('/v1/family/circle', headers=headers)).json()
    return circle['circle_id'], next(m['member_id'] for m in circle['members'] if m['is_you'])


def message(circle, sender, **changes):
    return {'message_id': str(uuid4()), 'circle_id': circle, 'sender_id': sender,
            'text': 'Nos vemos en el parque', 'created_at': datetime.now(timezone.utc).isoformat(), **changes}


@pytest.mark.asyncio
async def test_text_is_private_idempotent_and_never_a_safety_checkin():
    redis = FakeRedis(decode_responses=True)
    async with client_for(app_for(redis)) as client:
        owner, member = await family_with_member(client, redis)
        circle, sender = await context(client, owner)
        _, recipient = await context(client, member)
        payload = message(circle, sender)
        first = await client.post('/v1/family/messages', headers=owner, json=payload)
        second = await client.post('/v1/family/messages', headers=owner, json=payload)
        assert first.status_code == second.status_code == 200
        assert not first.json()['duplicate'] and second.json()['duplicate']
        assert first.json()['accepted_at'] == second.json()['accepted_at']
        result = await client.get('/v1/family/messages', headers=member, params={'sender_id': recipient})
        assert result.headers['cache-control'] == 'no-store'
        data = result.json()
        assert len(data['messages']) == 1 and data['messages'][0]['text'] == payload['text']
        assert not data['messages'][0]['is_you']
        assert 'google-owner' not in json.dumps(data)
        assert data['retention_hours'] == 24
        assert (await client.get('/v1/family/circle', headers=owner)).json()['members'][0]['status'] is None
        assert not await redis.exists('seismik:family:notifications')
        conflict = await client.post('/v1/family/messages', headers=owner, json={**payload, 'text': 'Distinto'})
        assert conflict.status_code == 409


@pytest.mark.asyncio
async def test_no_account_or_wrong_circle_or_sender_cannot_access_messages():
    redis = FakeRedis(decode_responses=True)
    async with client_for(app_for(redis)) as client:
        owner, member = await family_with_member(client, redis)
        circle, sender = await context(client, owner)
        outsider = await account(redis, 'outsider')
        assert (await client.post('/v1/family/messages', json=message(circle, sender))).status_code == 401
        assert (await client.get('/v1/family/messages', headers=outsider, params={'sender_id': sender})).status_code == 404
        assert (await client.get('/v1/family/messages', headers=member, params={'sender_id': sender})).status_code == 403
        assert (await client.post('/v1/family/messages', headers=owner, json=message('other-circle-id', sender))).status_code == 403
        assert (await client.post('/v1/family/messages', headers=member, json=message(circle, sender))).status_code == 403
        await redis.srem(f'seismik:family:members:{circle}', 'google-owner')
        assert (await client.post('/v1/family/messages', headers=owner, json=message(circle, sender))).status_code == 403


@pytest.mark.asyncio
async def test_expired_blank_long_and_timezone_free_messages_are_rejected():
    redis = FakeRedis(decode_responses=True)
    async with client_for(app_for(redis)) as client:
        owner, _ = await family_with_member(client, redis)
        circle, sender = await context(client, owner)
        changes = [{'text': '   '}, {'text': 'a'*281}, {'created_at': '2026-01-01T00:00:00'},
                   {'created_at': (datetime.now(timezone.utc)-timedelta(hours=25)).isoformat()},
                   {'created_at': (datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()},
                   {'location': {'latitude': 4.6, 'longitude': -74.0}}]
        for change in changes:
            result = await client.post('/v1/family/messages', headers=owner, json=message(circle, sender, **change))
            assert result.status_code == 422


@pytest.mark.asyncio
async def test_message_rate_limit_retention_and_bounded_reads():
    redis = FakeRedis(decode_responses=True)
    async with client_for(app_for(redis)) as client:
        owner, _ = await family_with_member(client, redis)
        circle, sender = await context(client, owner)
        for _ in range(12):
            assert (await client.post('/v1/family/messages', headers=owner, json=message(circle, sender))).status_code == 200
        limited = await client.post('/v1/family/messages', headers=owner, json=message(circle, sender))
        assert limited.status_code == 429 and limited.headers['retry-after'] == '60'
        result = await client.get('/v1/family/messages', headers=owner, params={'sender_id': sender, 'limit': 2})
        assert len(result.json()['messages']) == 2
        assert (await client.get('/v1/family/messages', headers=owner, params={'sender_id': sender, 'limit': 500})).status_code == 422
        keys = await redis.zrange(f'seismik:family:messages:{circle}', 0, -1)
        assert len(keys) == 12
        assert 86_390 <= await redis.ttl(keys[0]) <= 86_400
        await redis.delete(*keys)
        assert (await client.get('/v1/family/messages', headers=owner, params={'sender_id': sender})).json()['messages'] == []


@pytest.mark.asyncio
async def test_family_storage_is_bounded_without_disabling_safety_reports():
    redis = FakeRedis(decode_responses=True)
    async with client_for(app_for(redis)) as client:
        owner, _ = await family_with_member(client, redis)
        circle, sender = await context(client, owner)
        await redis.zadd(f'seismik:family:messages:{circle}', {f'item-{i}': datetime.now(timezone.utc).timestamp() for i in range(500)})
        result = await client.post('/v1/family/messages', headers=owner, json=message(circle, sender))
        assert result.status_code == 429
        assert await redis.zcard(f'seismik:family:messages:{circle}') == 500
        safe = await client.put('/v1/family/status', headers=owner, json={'status': 'need_help'})
        assert safe.status_code == 200
