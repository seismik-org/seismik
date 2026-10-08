from __future__ import annotations

import asyncio
import base64
import json
import time

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from test_report_admin import ADMIN, login_request, setup

from api.admin_security import (
    COOKIE,
    LOGIN_COOKIE,
    MFA_PREFIX,
    SESSION_PREFIX,
    account,
    digest,
    finish_admin_login,
    otp,
)
from api.config import AppSettings
from api.dependencies import get_app_settings
from api.runtime_controls import announce

SECRET = base64.b32encode(b"12345678901234567890").decode()


async def fixture():
    client, redis = await setup()
    settings = AppSettings(admin_emails="admin@example.com", admin_mfa_encryption_key=Fernet.generate_key().decode())
    client._transport.app.state.settings = settings
    client._transport.app.dependency_overrides[get_app_settings] = lambda: settings
    user = {"uid": "admin-token", "email": "admin@example.com", "authenticated_at": time.time(), "last_seen":time.time()}
    await redis.set(SESSION_PREFIX + digest("admin-token"), json.dumps(user), ex=300)
    await redis.delete(MFA_PREFIX + account(user))
    return client, redis, settings, user


def code(offset=0):
    return otp(SECRET, int(time.time() // 30) + offset)


async def enrolled():
    client, redis, settings, user = await fixture()
    encrypted = Fernet(settings.admin_mfa_encryption_key.get_secret_value().encode()).encrypt(SECRET.encode()).decode()
    await redis.set(MFA_PREFIX + account(user), json.dumps({"secret":encrypted, "version":"v1", "last_counter":-1, "recovery":[digest("abcd"*8)]}))
    return client, redis, settings, user


@pytest.mark.parametrize(("timestamp", "expected"), [(59,"94287082"),(1111111109,"07081804"),(1111111111,"14050471"),(1234567890,"89005924"),(2000000000,"69279037"),(20000000000,"65353130")])
def test_totp_matches_rfc6238_vectors(timestamp, expected):
    assert otp(SECRET, timestamp // 30, digits=8) == expected


@pytest.mark.asyncio
async def test_shared_cookie_and_pre_mfa_session_cannot_access_any_admin_data():
    client, redis, _, _ = await fixture()
    await redis.set("seismik:oauth:session:old-token", json.dumps({"email":"admin@example.com", "uid":"admin-token", "authenticated_at":time.time()}))
    async with client:
        for path in ("/v1/admin/me", "/v1/admin/overview", "/v1/admin/controls", "/v1/admin/records/felt", "/v1/reports/admin/reports"):
            assert (await client.get(path, headers={"Cookie":"seismik_session=old-token"})).status_code == 401
            assert (await client.get(path, headers=ADMIN)).status_code == 428
        assert (await client.get("/v1/admin/auth/status", headers=ADMIN)).json() == {"email":"admin@example.com", "enrolled":False, "verified":False}


@pytest.mark.asyncio
async def test_enrollment_encryption_confirmation_cookie_rotation_recovery_and_no_reenrollment():
    client, redis, _, user = await fixture()
    async with client:
        candidate = await client.post("/v1/admin/auth/enroll", headers=ADMIN)
        assert candidate.status_code == 200
        secret = candidate.json()["secret"]
        pending = await redis.get("seismik:admin:pending:" + digest("admin-token"))
        assert secret not in pending
        assert await redis.ttl("seismik:admin:pending:" + digest("admin-token")) <= 300
        assert not await redis.exists(MFA_PREFIX + account(user))
        response = await client.post("/v1/admin/auth/verify", headers=ADMIN, json={"code":otp(secret,int(time.time()//30))})
        assert response.status_code == 200
        cookie = response.headers["set-cookie"]
        assert COOKIE in cookie and "HttpOnly" in cookie and "Secure" in cookie and "SameSite=strict" in cookie
        assert "Domain=" not in cookie
        token = response.cookies.get(COOKIE)
        assert token != "admin-token"
        assert not await redis.exists(SESSION_PREFIX + digest("admin-token"))
        recovery = response.json()["recovery_codes"]
        assert len(recovery) == 10
        record = await redis.get(MFA_PREFIX + account(user))
        assert secret not in record and all(item not in record for item in recovery)
        headers = {**ADMIN, "Cookie":f"{COOKIE}={token}"}
        assert (await client.get("/v1/admin/me", headers=headers)).status_code == 200
        assert (await client.post("/v1/admin/auth/enroll", headers=headers)).status_code == 409
        audit = str(await redis.xrange(AppSettings().developer_audit_stream))
        assert secret not in audit and all(item not in audit for item in recovery)


@pytest.mark.asyncio
async def test_totp_replay_rejected_even_concurrently_across_sessions():
    client, redis, _, user = await enrolled()
    await redis.set(SESSION_PREFIX + digest("other-session"), json.dumps(user), ex=300)
    async with client:
        a, b = await asyncio.gather(
            client.post("/v1/admin/auth/verify", headers=ADMIN, json={"code":code()}),
            client.post("/v1/admin/auth/verify", headers={**ADMIN,"Cookie":f"{COOKIE}=other-session"},json={"code":code()}),
        )
        assert sorted([a.status_code,b.status_code]) == [200,401]


@pytest.mark.asyncio
async def test_step_up_is_bound_to_action_session_single_use_and_cannot_use_recovery():
    client, redis, _, user = await enrolled()
    user["mfa_version"] = "v1"
    await redis.set(SESSION_PREFIX + digest("admin-token"),json.dumps(user))
    await announce(redis,{"alerts":True,"x":True})
    async with client:
        url = "/v1/admin/controls/alerts"
        assert (await client.put(url,headers={k:v for k,v in ADMIN.items() if k!="X-Seismik-Admin-Approval"},json={"enabled":False})).status_code == 428
        assert (await client.post("/v1/admin/auth/verify",headers=ADMIN,json={"code":"abcd"*8,"action":"control:alerts:false"})).status_code == 401
        verified = await client.post("/v1/admin/auth/verify",headers=ADMIN,json={"code":code(),"action":"control:alerts:false"})
        assert verified.status_code == 200
        token = verified.json()["approval"]
        headers = {**ADMIN,"X-Seismik-Admin-Approval":token}
        assert (await client.put(url,headers=headers,json={"enabled":False})).status_code == 200
        assert (await client.put(url,headers=headers,json={"enabled":False})).status_code == 428
        await redis.set("seismik:admin:approval:"+digest(token),json.dumps({"session":digest("admin-token"),"action":"control:x:false"}),ex=120)
        assert (await client.put(url,headers=headers,json={"enabled":False})).status_code == 428
        await redis.set("seismik:admin:approval:"+digest(token),json.dumps({"session":digest("another-token"),"action":"control:alerts:false"}),ex=120)
        assert (await client.put(url,headers=headers,json={"enabled":False})).status_code == 428


@pytest.mark.asyncio
async def test_recovery_code_is_one_time_login_only_and_rate_limit_survives_new_sessions():
    client, redis, _, user = await enrolled()
    async with client:
        response = await client.post("/v1/admin/auth/verify",headers=ADMIN,json={"code":"abcd"*8})
        assert response.status_code == 200
        assert response.json()["recovery_codes"] == []
        await redis.set(SESSION_PREFIX+digest("admin-token"),json.dumps(user),ex=300)
        assert (await client.post("/v1/admin/auth/verify",headers=ADMIN,json={"code":"abcd"*8})).status_code == 401
        for _ in range(3):
            assert (await client.post("/v1/admin/auth/verify",headers=ADMIN,json={"code":"invalid"})).status_code == 401
        assert (await client.post("/v1/admin/auth/verify",headers=ADMIN,json={"code":code()})).status_code == 429


@pytest.mark.asyncio
async def test_csrf_idle_expiry_mfa_version_change_and_logout_invalidate_admin_session():
    client, redis, _, user = await enrolled()
    user["mfa_version"] = "v1"
    async with client:
        await redis.set(SESSION_PREFIX+digest("admin-token"),json.dumps(user))
        for origin in ("https://ifeltit.seismik.org","https://evil.example",None):
            headers={k:v for k,v in ADMIN.items() if k!="Origin"}
            if origin:
                headers["Origin"]=origin
            assert (await client.post("/v1/admin/auth/verify",headers=headers,json={"code":code()})).status_code == 403
        user["last_seen"] = time.time()-901
        await redis.set(SESSION_PREFIX+digest("admin-token"),json.dumps(user))
        assert (await client.get("/v1/admin/me",headers=ADMIN)).status_code == 401
        user["last_seen"] = time.time()
        user["mfa_version"]="old-version"
        await redis.set(SESSION_PREFIX+digest("admin-token"),json.dumps(user))
        assert (await client.get("/v1/admin/me",headers=ADMIN)).status_code == 428
        assert (await client.post("/v1/admin/auth/logout",headers=ADMIN)).status_code == 200
        assert not await redis.exists(SESSION_PREFIX+digest("admin-token"))


@pytest.mark.asyncio
async def test_admin_handoff_requires_original_browser_and_is_single_use():
    client, redis, settings, user = await fixture()
    state="a"*43
    await redis.set("seismik:admin:login:"+digest(state),"1",ex=600)
    request=login_request("seismik_after_login=admin:"+state)
    request.app.state.redis=redis
    request.app.state.settings=settings
    response=await finish_admin_login(request,user)
    assert "seismik_session=" not in str(response.headers)
    code=response.headers["location"].split("admin_code=")[1]
    assert await redis.ttl("seismik:admin:handoff:"+digest(code)) <= 60
    async with client:
        bad=await client.post("/v1/admin/auth/exchange",headers=ADMIN,json={"code":code})
        assert bad.status_code==401
        assert (await client.post("/v1/admin/auth/exchange",headers={**ADMIN,"Cookie":f"{LOGIN_COOKIE}={state}"},json={"code":code})).status_code==401
        await redis.set("seismik:admin:login:"+digest(state),"1",ex=600)
        response=await finish_admin_login(request,user)
        code=response.headers["location"].split("admin_code=")[1]
        good=await client.post("/v1/admin/auth/exchange",headers={**ADMIN,"Cookie":f"{LOGIN_COOKIE}={state}"},json={"code":code})
        assert good.status_code==200
        assert "Domain=" not in good.headers["set-cookie"]
        with pytest.raises(HTTPException):
            await finish_admin_login(request,user)


@pytest.mark.asyncio
async def test_another_provider_with_same_email_cannot_enroll_again_or_access_admin():
    from api.admin_security import BINDING_PREFIX
    client, redis, _, user = await enrolled()
    await redis.set(BINDING_PREFIX + digest(user["email"]), account(user))
    user["uid"] = "different-provider-subject"
    await redis.set(SESSION_PREFIX + digest("other-provider"), json.dumps(user), ex=300)
    headers = {**ADMIN, "Cookie": f"{COOKIE}=other-provider"}
    async with client:
        for path in ("/v1/admin/auth/status", "/v1/admin/me"):
            assert (await client.get(path, headers=headers)).status_code == 403
        assert (await client.post("/v1/admin/auth/enroll", headers=headers)).status_code == 403


def test_redaction_handles_embedded_json_bearer_and_malformed_payloads():
    from api.admin import _decode, redact
    data = redact({"nested_json":'{"access_token":"private-value"}', "message":"Bearer private-value https://x/?token=private-value", "malformed":'{"secret":"private-value"'})
    assert "private-value" not in json.dumps(data)
    assert "private-value" not in json.dumps(_decode({"payload":'{"token":"private-value"'}))
