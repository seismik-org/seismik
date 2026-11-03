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


async def third_member(client, redis, owner):
    headers = await account(redis, 'third-relative')
    invitation = await client.post('/v1/family/circle/invitations', headers=owner, json={'display_name': 'Luis'})
    joined = await client.post('/v1/family/join', headers=headers,
                              json={'invite_code': invitation.json()['invite_code'], 'display_name': 'Luis'})
    assert joined.status_code == 200
    return headers


def message(circle, sender, **changes):
    return {'message_id': str(uuid4()), 'circle_id': circle, 'sender_id': sender,
            'text': 'Nos vemos en el parque', 'created_at': datetime.now(timezone.utc).isoformat(), **changes}


@pytest.mark.asyncio
async def test_direct_messages_are_two_party_only_and_never_enter_group_history():
    redis = FakeRedis(decode_responses=True)
    async with client_for(app_for(redis)) as client:
        owner, member = await family_with_member(client, redis)
        third = await third_member(client, redis, owner)
        circle, sender = await context(client, owner)
        _, recipient = await context(client, member)
        _, other = await context(client, third)
        payload = message(circle, sender, recipient_id=recipient)
        assert (await client.post('/v1/family/messages', headers=owner, json=payload)).status_code == 200
        assert (await client.post('/v1/family/messages', headers=owner, json=payload)).json()['duplicate']
        for headers, identity in ((owner, sender), (member, recipient), (third, other)):
            result = await client.get('/v1/family/messages', headers=headers, params={'sender_id': identity})
            assert result.json()['messages'] == []
        for headers, identity, peer in ((owner, sender, recipient), (member, recipient, sender)):
            result = await client.get('/v1/family/messages', headers=headers,
                                      params={'sender_id': identity, 'recipient_id': peer})
            assert result.headers['cache-control'] == 'no-store'
            assert len(result.json()['messages']) == 1
            assert result.json()['messages'][0]['text'] == payload['text']
        forged = await client.get('/v1/family/messages', headers=third,
                                  params={'sender_id': sender, 'recipient_id': recipient})
        assert forged.status_code == 403
        own_chat = await client.get('/v1/family/messages', headers=third,
                                    params={'sender_id': other, 'recipient_id': recipient})
        assert own_chat.json()['messages'] == []
        assert await redis.zcard(f'seismik:family:messages:{circle}') == 0
        assert not await redis.exists('seismik:family:notifications')


@pytest.mark.asyncio
async def test_message_identifier_cannot_be_reused_for_another_conversation():
    redis = FakeRedis(decode_responses=True)
    async with client_for(app_for(redis)) as client:
        owner, member = await family_with_member(client, redis)
        circle, sender = await context(client, owner)
        _, recipient = await context(client, member)
        payload = message(circle, sender, recipient_id=recipient)
        assert (await client.post('/v1/family/messages', headers=owner, json=payload)).status_code == 200
        assert (await client.post('/v1/family/messages', headers=owner,
                                   json={**payload, 'recipient_id': None})).status_code == 409
        assert (await client.post('/v1/family/messages', headers=owner,
                                   json=message(circle, sender, recipient_id=sender))).status_code == 422
        assert (await client.post('/v1/family/messages', headers=owner,
                                   json=message(circle, sender, recipient_id='0'*16))).status_code == 404


@pytest.mark.asyncio
async def test_private_quota_is_shared_with_group_and_recipient_membership_is_required():
    from api.family import family_members_key
    redis = FakeRedis(decode_responses=True)
    async with client_for(app_for(redis)) as client:
        owner, member = await family_with_member(client, redis)
        circle, sender = await context(client, owner)
        _, recipient = await context(client, member)
        await redis.zadd(f'seismik:family:messages:{circle}',
                         {f'group-{i}': datetime.now(timezone.utc).timestamp() for i in range(249)})
        await redis.zadd(f'seismik:family:private-message-budget:{circle}',
                         {f'item-{i}': datetime.now(timezone.utc).timestamp() for i in range(251)})
        assert (await client.post('/v1/family/messages', headers=owner,
                                   json=message(circle, sender))).status_code == 429
        assert (await client.post('/v1/family/messages', headers=owner,
                                   json=message(circle, sender, recipient_id=recipient))).status_code == 429
        await redis.srem(family_members_key(circle), 'google-ana')
        assert (await client.post('/v1/family/messages', headers=owner,
                                   json=message(circle, sender, recipient_id=recipient))).status_code == 404
        assert (await client.get('/v1/family/messages', headers=owner,
                                  params={'sender_id': sender, 'recipient_id': recipient})).status_code == 404


@pytest.mark.asyncio
async def test_recipient_leaving_during_send_cannot_receive_a_new_message(monkeypatch):
    from api import family
    redis = FakeRedis(decode_responses=True)
    async with client_for(app_for(redis)) as client:
        owner, member = await family_with_member(client, redis)
        circle, sender = await context(client, owner)
        _, recipient = await context(client, member)
        original = family._message_recipient

        async def leaving(store, current_circle, current_sender, target):
            uid = await original(store, current_circle, current_sender, target)
            await store.srem(family.family_members_key(current_circle), uid)
            return uid

        monkeypatch.setattr(family, '_message_recipient', leaving)
        result = await client.post('/v1/family/messages', headers=owner,
                                   json=message(circle, sender, recipient_id=recipient))
        assert result.status_code == 403
        assert await redis.zcard(family._message_index(circle, sender, recipient)) == 0


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
async def test_message_rate_limit_retention_and_bounded_reads(monkeypatch):
    from api import family
    moment = datetime.now(timezone.utc)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return moment if tz else moment.replace(tzinfo=None)

    monkeypatch.setattr(family, 'datetime', FrozenDateTime)
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
