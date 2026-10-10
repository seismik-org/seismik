"""admin.seismik.org: estado, alertas, flota, auditoría, plataforma, sesiones, borrados, plantillas y reportes."""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import pytest
from fakeredis.aioredis import FakeRedis
from fastapi import FastAPI

from api import admin_notify
from api.admin import router as admin_router
from api.admin_beta import router as beta_router
from api.admin_ops import DELETION_KEY
from api.admin_ops import router as ops_router
from api.admin_security import COOKIE, MFA_PREFIX, SESSION_PREFIX, account, digest, valid_action
from api.admin_security import router as security_router
from api.config import AppSettings
from api.dependencies import get_app_settings, get_redis
from api.runtime_controls import announce, service_info
from dispatcher.consumer import StreamConsumer
from reporting.ingest import router as reports_router

HEADERS = {"Cookie": f"{COOKIE}=admin-token", "Origin": "https://admin.seismik.org",
           "X-Seismik-Admin": "1", "X-Seismik-Admin-Approval": "approval"}
NOW = datetime.now(timezone.utc)


async def client_for(**settings_changes: Any):
    settings = AppSettings(admin_emails="admin@example.com", **settings_changes)
    redis = FakeRedis(decode_responses=True)
    await redis.set(SESSION_PREFIX + digest("admin-token"), json.dumps({
        "uid": "admin-token", "email": "admin@example.com", "authenticated_at": time.time(),
        "last_seen": time.time(), "mfa_version": "v1"}))
    await redis.set(MFA_PREFIX + account({"uid": "admin-token"}), json.dumps({"version": "v1"}))
    app = FastAPI()
    for router in (admin_router, beta_router, ops_router, security_router, reports_router):
        app.include_router(router)
    app.state.settings, app.state.redis = settings, redis
    app.dependency_overrides[get_app_settings] = lambda: settings
    app.dependency_overrides[get_redis] = lambda: redis
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://local"), redis, settings


async def approve(redis: FakeRedis, action: str) -> None:
    await redis.set("seismik:admin:approval:" + digest("approval"),
                    json.dumps({"session": digest("admin-token"), "action": action}), ex=120)


def block(response: httpx.Response, kind: str, title: str | None = None) -> dict[str, Any]:
    return next(item for item in response.json()["blocks"]
                if item["type"] == kind and (title is None or item.get("title") == title))


def kpi(response: httpx.Response, label: str) -> str:
    return next(item["value"] for item in block(response, "kpis")["items"] if item["label"] == label)


# --- estado ---------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_system_says_whether_x_really_publishes_from_what_the_service_reports() -> None:
    client, redis, _ = await client_for()
    async with client:
        none = await client.get("/v1/admin/system", headers=HEADERS)
        assert kpi(none, "Publicación en X") == "Sin conexión reciente"

        async def report(**flags: bool) -> str:
            caps = {"x": flags["configured"], "facebook": False}
            await announce(redis, caps, service_info("integrations", {
                "x_publisher_enabled": flags["enabled"], "x_publisher_dry_run": flags["dry_run"],
                "facebook_publisher_enabled": False, "facebook_publisher_dry_run": True}))
            return kpi(await client.get("/v1/admin/system", headers=HEADERS), "Publicación en X")

        assert await report(enabled=False, dry_run=True, configured=False) == "Apagada"
        assert await report(enabled=True, dry_run=True, configured=False) == "Simulación (no publica)"
        assert await report(enabled=True, dry_run=False, configured=True) == "Publicando de verdad"
        await redis.hset("seismik:operations:paused", "x", "1")
        assert await report(enabled=True, dry_run=False, configured=True) == "Pausada desde el panel"
        full = await client.get("/v1/admin/system", headers=HEADERS)
    config = block(full, "table", "Configuración efectiva (solo lectura)")["rows"]
    assert ["Dispatcher (X, Facebook, catálogo)", "x_publisher_enabled", "sí"] in config
    assert any("latido del detector" in item["text"] for item in full.json()["blocks"] if item["type"] == "note")


@pytest.mark.asyncio
async def test_system_lists_running_services_and_stream_activity() -> None:
    client, redis, settings = await client_for()
    await announce(redis, {"alerts": True}, service_info("alerts", {"push_enabled": True, "push_mode": "production"}))
    await redis.xadd(settings.official_stream, {"payload": json.dumps({"event_id": "e1"})})
    async with client:
        response = await client.get("/v1/admin/system", headers=HEADERS)
    assert kpi(response, "Push a teléfonos") == "production"
    services = block(response, "table", "Qué corre ahora")["rows"]
    assert services[0][0] == "API" and any(row[0] == "Dispatcher (alertas)" for row in services)
    activity = {row[0]: row for row in block(response, "table", "Actividad de los registros")["rows"]}
    assert activity["Sismos oficiales"][3] == "1"


# --- alertas ---------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_alerts_view_links_official_quakes_to_what_was_sent() -> None:
    client, redis, settings = await client_for()
    report = {"origin_time": (NOW - timedelta(minutes=10)).isoformat(), "latitude": 4.9, "longitude": -76.2,
              "magnitude": 7.4, "depth_km": 108, "place": "San José del Palmar", "agency": "USGS"}
    await redis.xadd(settings.official_stream, {"payload": json.dumps({"event_id": "usgs:1", "preferred_report": report})})
    await redis.xadd(settings.official_stream, {"payload": json.dumps({"event_id": "usgs:2", "preferred_report": {**report, "magnitude": 4.1}})})
    await redis.xadd(settings.alert_ledger_stream, {
        "event_id": "usgs:1", "type": "official_report_update", "critical": "true", "emitted_at": NOW.isoformat(),
        "delivered": "1234", "payload": json.dumps({"place": "San José del Palmar", "magnitude": 7.4})})
    async with client:
        response = await client.get("/v1/admin/alerts", headers=HEADERS)
    assert kpi(response, "Alarmas (24 h)") == "1" and kpi(response, "Dispositivos alcanzados (24 h)") == "1.234"
    official = {row[1]: row for row in block(response, "table", "Sismos oficiales recientes")["rows"]}
    assert official["7.4"][5] == "Sí" and official["4.1"][5] == "No"
    sent = block(response, "table", "Alertas enviadas")["rows"]
    assert sent[0][1] == "Alarma" and sent[0][4] == "1.234"


@pytest.mark.asyncio
async def test_explain_uses_the_real_policy_for_pereira_after_the_2026_quake() -> None:
    client, _, _ = await client_for()
    base = {"epicenter_latitude": 4.9, "epicenter_longitude": -76.2, "magnitude": 7.4, "depth_km": 108}
    async with client:
        pereira = await client.get("/v1/admin/alerts/explain", params={**base, "latitude": 4.81, "longitude": -75.69}, headers=HEADERS)
        old = await client.get("/v1/admin/alerts/explain", params={**base, "latitude": 4.81, "longitude": -75.69, "minutes_ago": 90}, headers=HEADERS)
        quiet = await client.get("/v1/admin/alerts/explain", params={**base, "latitude": 4.81, "longitude": -75.69, "receive_official": "false"}, headers=HEADERS)
        far = await client.get("/v1/admin/alerts/explain", params={**base, "latitude": 10.96, "longitude": -74.8}, headers=HEADERS)
    assert pereira.status_code == 200
    assert kpi(pereira, "Reporte oficial") == "Alarma"
    assert kpi(old, "Reporte oficial") == "Aviso", "pasados 30 min la alarma baja a aviso"
    assert kpi(quiet, "Reporte oficial") == "Alarma", "una sacudida fuerte suena aunque apague los reportes oficiales"
    assert kpi(far, "Reporte oficial") == "Nada"
    assert "7" in kpi(pereira, "Intensidad esperada") or "VII" in kpi(pereira, "Intensidad esperada")


# --- flota ----------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_fleet_is_aggregated_and_small_groups_are_hidden() -> None:
    client, redis, _ = await client_for()
    for index in range(12):
        await redis.hset(f"seismik:device:phone-secret-{index:04d}", mapping={
            "platform": "android" if index < 7 else "ios", "token": "t" * 40 if index != 3 else "",
            "country_code": "CO" if index < 11 else "EC", "critical_alerts_authorized": "1" if index % 2 == 0 else "0",
            "receive_early_alerts": "1", "receive_official_updates": "1", "integrity_verified": "1",
            "alert_radius_km": "250", "minimum_notification_magnitude": "4.0", "updated_at": NOW.isoformat()})
    await redis.set("seismik:device:account:phone-secret-0001", "uid-private")
    await redis.set("seismik:metrics:invalid-tokens:" + NOW.strftime("%Y%m%d"), "3")
    async with client:
        response = await client.get("/v1/admin/fleet", headers=HEADERS)
    assert response.status_code == 200 and kpi(response, "Dispositivos") == "12"
    platforms = {row[0]: row[1] for row in block(response, "table", "Plataforma")["rows"]}
    assert platforms == {"android": "7", "ios": "5"}
    countries = {row[0]: row[1] for row in block(response, "table", "País")["rows"]}
    assert countries["CO"] == "11" and "EC" not in countries and "Otros (grupos de menos de 5)" in countries
    hidden = next(row for row in block(response, "table", "País")["rows"] if row[0].startswith("Otros"))
    assert hidden[1] == "<5" and hidden[2] == "—", "el porcentaje de un grupo pequeño revelaría la cifra oculta"
    assert block(response, "table", "Tokens rechazados por APNs/FCM (por día)")["rows"][0][1] == "3"
    assert "phone-secret" not in response.text and "uid-private" not in response.text


# --- auditoría -------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_audit_log_is_readable_marks_sensitive_actions_and_hides_customer_data() -> None:
    client, redis, settings = await client_for()
    await redis.xadd(settings.developer_audit_stream, {"action": "key_created", "by": "dev@cliente.com", "at": str(int(time.time()))})
    await redis.xadd(settings.developer_audit_stream, {"action": "operation.paused", "feature": "x", "by": "admin@example.com",
                                                       "at": NOW.isoformat()})
    async with client:
        everything = await client.get("/v1/admin/audit", headers=HEADERS)
        only_sensitive = await client.get("/v1/admin/audit", params={"sensitive": "true"}, headers=HEADERS)
    rows = block(everything, "table")["rows"]
    assert [row[1] for row in rows] == ["Pausó una función", "Creó una clave de API"]
    assert rows[0][2] == "admin@example.com" and rows[0][4] == "Sensible"
    assert rows[1][2] == "•••", "el correo de un cliente no se muestra"
    assert [row[1] for row in block(only_sensitive, "table")["rows"]] == ["Pausó una función"]


# --- plataforma de desarrolladores ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_developer_platform_numbers_are_aggregated_without_names_or_keys() -> None:
    client, redis, settings = await client_for()
    for index in range(6):
        await redis.hset(f"seismik:developer-profile:uid-{index}", mapping={"selected_plan_id": "free" if index < 4 else "pro"})
    await redis.hset("seismik:developer-key:abc", mapping={"status": "active", "last_used_at": NOW.isoformat(), "name": "Mi clave secreta"})
    await redis.hset("seismik:developer-key:def", mapping={"status": "revoked", "name": "Otra"})
    await redis.set(f"seismik:developer-usage:day:abc:{NOW:%Y%m%d}", "120")
    await redis.xadd(settings.integration_dead_letter_stream, {"source_id": "1-0", "payload": "{}", "attempts": "5"})
    async with client:
        response = await client.get("/v1/admin/usage", headers=HEADERS)
    assert kpi(response, "Consultas hoy (UTC)") == "120" and kpi(response, "Webhooks fallidos (24 h)") == "1"
    assert {row[0]: row[1] for row in block(response, "table", "Planes")["rows"]} == {"free": "<5", "pro": "<5"}
    assert "Mi clave secreta" not in response.text and "abc" not in response.text.replace("abcd", "")


# --- sesiones --------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sessions_are_listed_and_another_one_can_be_revoked_with_mfa() -> None:
    client, redis, _ = await client_for()
    await redis.set(SESSION_PREFIX + digest("other-token"), json.dumps({
        "uid": "u2", "email": "otro@example.com", "authenticated_at": time.time() - 60, "last_seen": time.time() - 30, "mfa_version": "v1"}))
    other_ref = digest("other-token")[:16]
    async with client:
        listed = (await client.get("/v1/admin/sessions", headers=HEADERS)).json()
        assert {item["ref"]: item["current"] for item in listed["sessions"]} == {digest("admin-token")[:16]: True, other_ref: False}
        assert (await client.delete(f"/v1/admin/sessions/{other_ref}", headers=HEADERS)).status_code == 428
        await approve(redis, f"session:revoke:{other_ref}")
        assert (await client.delete(f"/v1/admin/sessions/{other_ref}", headers=HEADERS)).json() == {"revoked": True}
        assert (await client.delete("/v1/admin/sessions/" + "0" * 16, headers=HEADERS)).status_code == 404
    assert not await redis.exists(SESSION_PREFIX + digest("other-token"))


# --- solicitudes de borrado --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deletion_requests_show_status_and_deadline_but_never_the_requester() -> None:
    client, redis, settings = await client_for()
    old = (NOW - timedelta(days=40)).isoformat()
    await redis.xadd(settings.account_deletion_request_stream, {"payload": json.dumps({
        "request_id": "delreq_" + "a" * 16, "received_at": old, "email": "persona@correo.com", "scope": "account",
        "details": "Mi nombre es Ana Pérez", "source": "web"})})
    await redis.xadd(settings.account_deletion_request_stream, {"payload": json.dumps({
        "request_id": "delreq_" + "b" * 16, "received_at": NOW.isoformat(), "email": "otra@correo.com", "scope": "account", "source": "web"})})
    request_id = "delreq_" + "a" * 16
    async with client:
        listed = await client.get("/v1/admin/deletions", headers=HEADERS)
        assert "persona@correo.com" not in listed.text and "Ana" not in listed.text
        body = listed.json()
        assert body["open"] == 2 and body["overdue"] == 1
        assert next(item for item in body["requests"] if item["request_id"] == request_id)["overdue"] is True
        url = f"/v1/admin/deletions/{request_id}"
        assert (await client.put(url, json={"status": "completed"}, headers=HEADERS)).status_code == 428
        await approve(redis, f"deletion:{request_id}:completed")
        done = await client.put(url, json={"status": "completed"}, headers=HEADERS)
        assert done.status_code == 200 and done.json()["overdue"] == 0 and done.json()["open"] == 1
        assert (await client.put("/v1/admin/deletions/delreq_" + "c" * 16, json={"status": "completed"}, headers=HEADERS)).status_code == 404
        assert (await client.put(url, json={"status": "borrado"}, headers=HEADERS)).status_code == 422
    assert json.loads(await redis.hget(DELETION_KEY, request_id))["by"] == "admin@example.com"


# --- plantillas y solo lectura ------------------------------------------------------------------------


TEMPLATE = {"place": "Eje Cafetero", "latitude": 5.0721, "longitude": -75.5138, "magnitude": 6.8, "depth_km": 12.5,
            "origin_minutes_ago": 2, "country_code": "CO", "critical": True}


@pytest.mark.asyncio
async def test_drill_templates_can_be_saved_listed_and_deleted() -> None:
    client, _, _ = await client_for()
    async with client:
        saved = await client.put("/v1/admin/drill-templates/Eje%20Cafetero", json=TEMPLATE, headers=HEADERS)
        assert saved.status_code == 200 and saved.json()["templates"][0]["name"] == "Eje Cafetero"
        assert (await client.put("/v1/admin/drill-templates/Eje%20Cafetero%20M6.8", json=TEMPLATE, headers=HEADERS)).status_code == 200
        listing = await client.get("/v1/admin/beta-phones", headers=HEADERS)
        assert listing.json()["templates"][0]["magnitude"] == 6.8
        assert (await client.put("/v1/admin/drill-templates/x", json={**TEMPLATE, "magnitude": 12}, headers=HEADERS)).status_code == 422
        assert (await client.put("/v1/admin/drill-templates/mal*nombre", json=TEMPLATE, headers=HEADERS)).status_code == 422
        await client.delete("/v1/admin/drill-templates/Eje%20Cafetero%20M6.8", headers=HEADERS)
        assert (await client.delete("/v1/admin/drill-templates/Eje%20Cafetero", headers=HEADERS)).json() == {"templates": []}


@pytest.mark.asyncio
async def test_a_read_only_account_can_look_but_not_change_anything() -> None:
    client, redis, _ = await client_for(admin_readonly_emails="Admin@Example.com")
    await redis.hset("seismik:device:phone-0001-abcd", mapping={"platform": "ios", "token": "t" * 40})
    ref = "0aec05721a399773"
    async with client:
        assert (await client.get("/v1/admin/me", headers=HEADERS)).json() == {"email": "admin@example.com", "readonly": True}
        assert (await client.get("/v1/admin/fleet", headers=HEADERS)).status_code == 200
        await approve(redis, f"beta:remove:{ref}")
        await redis.hset("seismik:admin:beta-phones", ref, json.dumps({"device_id": "phone-0001-abcd"}))
        denied = await client.delete(f"/v1/admin/beta-phones/{ref}", headers=HEADERS)
        assert denied.status_code == 403 and "solo lectura" in denied.json()["detail"]
        assert (await client.put("/v1/admin/drill-templates/x", json=TEMPLATE, headers=HEADERS)).status_code == 403
        approval_attempt = await client.post("/v1/admin/auth/verify", json={"code": "123456", "action": f"beta:remove:{ref}"}, headers=HEADERS)
        assert approval_attempt.status_code == 403
    assert await redis.hexists("seismik:admin:beta-phones", ref), "no se quitó nada"


# --- reportes ----------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_report_map_groups_felt_reports_into_coarse_cells_with_expected_intensity() -> None:
    client, redis, settings = await client_for()
    await redis.xadd(settings.official_stream, {"payload": json.dumps({"event_id": "usgs:1", "preferred_report": {
        "origin_time": NOW.isoformat(), "latitude": 4.9, "longitude": -76.2, "magnitude": 7.4, "depth_km": 108, "place": "Palmar"}})})
    for latitude, longitude, mmi in ((4.81, -75.69, 7), (4.83, -75.71, 6), (6.25, -75.58, 5), (10.96, -74.8, 2)):
        await redis.xadd(settings.felt_reports_stream, {"payload": json.dumps({
            "earthquake_event_id": "usgs:1", "latitude": latitude, "longitude": longitude, "intensity_mmi": mmi, "felt": True,
            "device_id": "device-secret-0001", "comment": "Soy Pedro"})})
    await redis.xadd(settings.felt_reports_stream, {"payload": json.dumps({
        "earthquake_event_id": "usgs:OTRO", "latitude": 1.0, "longitude": 1.0, "intensity_mmi": 3, "felt": True})})
    async with client:
        response = await client.get("/v1/admin/reports-heat", params={"event_id": "usgs:1"}, headers=HEADERS)
    body = response.json()
    assert body["total"] == 4 and body["event"]["magnitude"] == 7.4
    cells = {(cell["latitude"], cell["longitude"]): cell for cell in body["cells"]}
    pereira = cells[(4.75, -75.75)]
    assert pereira["count"] == 2 and pereira["avg_mmi"] == 6.5 and pereira["expected_mmi"] > 5
    assert all(0.0 == (cell["latitude"] - 0.25) % 0.5 for cell in body["cells"]), "celdas de 0,5°, no puntos exactos"
    assert "Pedro" not in response.text and "device-secret" not in response.text


# --- acciones del MFA, avisos y dispatcher ------------------------------------------------------------


def test_the_new_panel_actions_are_accepted_by_the_mfa_verify_endpoint() -> None:
    for action in ("deletion:delreq_" + "a" * 16 + ":completed", "session:revoke:" + "a" * 16):
        assert valid_action(action), action
    for action in ("deletion:delreq_" + "a" * 16 + ":borrado", "deletion:otro:completed", "session:revoke:corto"):
        assert not valid_action(action), action


@pytest.mark.asyncio
async def test_sensitive_action_notices_are_optional_and_never_carry_customer_data(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[tuple[str, str]] = []

    async def fake_post(url: str, text: str) -> None:
        sent.append((url, text))

    monkeypatch.setattr(admin_notify, "_post", fake_post)
    client, redis, _ = await client_for(admin_alert_webhook_url="https://hooks.example.com/seismik")
    await redis.hset("seismik:device:phone-0001-abcd", mapping={"platform": "ios", "token": "t" * 40})
    async with client:
        await approve(redis, "beta:add:" + __import__("api.beta_phones", fromlist=["x"]).phone_ref("phone-0001-abcd"))
        response = await client.post("/v1/admin/beta-phones", json={"device_id": "phone-0001-abcd", "label": "iPhone de Ana"}, headers=HEADERS)
        assert response.status_code == 201
        await __import__("asyncio").sleep(0.05)
    assert sent and sent[0][0] == "https://hooks.example.com/seismik"
    assert "admin@example.com" in sent[0][1] and "phone-0001-abcd" not in sent[0][1] and "Ana" not in sent[0][1]

    sent.clear()
    quiet, quiet_redis, _ = await client_for()  # sin URL: no se envía nada
    await quiet_redis.hset("seismik:device:phone-0001-abcd", mapping={"platform": "ios", "token": "t" * 40})
    async with quiet:
        await approve(quiet_redis, "beta:add:" + __import__("api.beta_phones", fromlist=["x"]).phone_ref("phone-0001-abcd"))
        await quiet.post("/v1/admin/beta-phones", json={"device_id": "phone-0001-abcd", "label": "x"}, headers=HEADERS)
        await __import__("asyncio").sleep(0.05)
    assert sent == []


class Devices:
    def __init__(self) -> None:
        self.removed: list[str] = []

    async def unregister(self, device_id: str) -> bool:
        self.removed.append(device_id)
        return True


@pytest.mark.asyncio
async def test_the_dispatcher_counts_rejected_tokens_per_day() -> None:
    redis = FakeRedis(decode_responses=True)
    devices = Devices()
    consumer = StreamConsumer(redis, AppSettings(), devices, object())  # type: ignore[arg-type]

    await consumer._remove_invalid(("a-device-0001", "b-device-0002"))
    await consumer._remove_invalid(())

    assert devices.removed == ["a-device-0001", "b-device-0002"]
    assert await redis.get(f"seismik:metrics:invalid-tokens:{NOW:%Y%m%d}") == "2"
