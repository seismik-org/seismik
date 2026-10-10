"""admin.seismik.org: sin datos privados de clientes, teléfonos de prueba y simulacros dirigidos."""
from __future__ import annotations

import json
import time
from datetime import datetime

import httpx
import pytest
from fakeredis.aioredis import FakeRedis
from fastapi import FastAPI
from pydantic import SecretStr

from api.admin import router as admin_router
from api.admin_beta import DrillIn, drill_action
from api.admin_beta import router as beta_router
from api.admin_privacy import PrivateView, pseudonym
from api.admin_security import MFA_PREFIX, SESSION_PREFIX, account, digest
from api.admin_security import router as security_router
from api.beta_phones import DRILL_KEY_PREFIX, PHONES_KEY, phone_ref
from api.config import AppSettings
from api.dependencies import get_app_settings, get_redis
from api.schemas import DeviceTarget
from dispatcher.consumer import StreamConsumer
from dispatcher.push import PushResult, notification_content
from reporting.ingest import router as reports_router

COOKIE_HEADERS = {
    "Cookie": "__Host-Seismik-Admin=admin-token", "Origin": "https://admin.seismik.org",
    "X-Seismik-Admin": "1", "X-Seismik-Admin-Approval": "approval",
}
SECRET = "una-clave-del-panel"
PHONE = "ios-device-0001-abcd"
OTHER_PHONE = "android-device-0002-wxyz"


def view(stream: str, admins: str = "admin@example.com") -> PrivateView:
    return PrivateView(stream, SECRET, admins)


# --- Privacidad ---------------------------------------------------------------------------


def test_family_notices_hide_names_messages_and_real_ids() -> None:
    record = {
        "type": "family_status", "event_id": "family-abc", "circle_id": "casa-de-los-perez",
        "member_id": "google-ana", "display_name": "Ana Pérez", "status": "safe",
        "message": "Estoy bien, en casa de mi mamá Luisa", "related_event_id": "official-1",
        "reported_at": "2026-10-09T12:00:00+00:00",
    }

    shown = view("family")(record)

    assert shown["display_name"] == "•••" and shown["message"] == "•••"
    assert shown["circle_id"] == pseudonym("casa-de-los-perez", SECRET) != "casa-de-los-perez"
    assert shown["member_id"].startswith("id:") and "ana" not in json.dumps(shown).lower()
    # Lo operativo sí se ve.
    assert shown["status"] == "safe" and shown["related_event_id"] == "official-1" and shown["event_id"] == "family-abc"
    # El mismo círculo sale igual dos veces (sirve para depurar) y cambia con otra clave.
    assert view("family")(record)["circle_id"] == shown["circle_id"]
    assert PrivateView("family", "otra-clave")(record)["circle_id"] != shown["circle_id"]


def test_push_test_records_keep_public_text_but_family_pushes_lose_the_name() -> None:
    drill = {"title": "SIMULACRO: Sismo fuerte en tu zona", "body": "M 5.2. Simulacro — Sabana de Bogotá",
             "data": {"type": "official_report_update", "event_id": "drill-1"}}
    family = {"title": "Ana Pérez está bien", "body": "Reportó que está a salvo",
              "data": {"type": "family_status", "display_name": "Ana Pérez", "event_id": "family-1"}}

    assert view("push_audit")(drill) == drill
    shown = view("push_audit")(family)
    assert shown["title"] == "•••" and shown["body"] == "•••" and shown["data"]["display_name"] == "•••"
    assert "Ana" not in json.dumps(shown)


def test_reports_lose_free_text_and_exact_location() -> None:
    shown = view("felt")({
        "report_id": "web-1", "latitude": 4.65432, "longitude": -74.05678, "country_code": "CO",
        "comment": "Vivo en la calle 12 #3-45, llamen al 300 123 4567", "intensity_mmi": 5,
        "device_id": "device-secret-0001",
    })

    assert shown["latitude"] == 4.7 and shown["longitude"] == -74.1  # ~11 km, no la casa
    assert shown["comment"] == "•••" and "300" not in json.dumps(shown)
    assert shown["device_id"] == pseudonym("device-secret-0001", SECRET)
    assert shown["country_code"] == "CO" and shown["intensity_mmi"] == 5 and shown["report_id"] == "web-1"


def test_emails_and_phone_labels_are_hidden_but_admin_actions_stay_attributable() -> None:
    deletion = view("deletions")({"request_id": "delreq_1", "email": "persona@correo.com", "details": "Borren todo"})
    assert deletion == {"request_id": "delreq_1", "email": "•••", "details": "•••"}

    audit = view("developer_audit")({"action": "report_review", "by": "admin@example.com",
                                     "note": "contacto dev@empresa.com", "uid": "dev-uid-77"})
    assert audit["by"] == "admin@example.com"  # tu propia acción sigue en la auditoría
    assert audit["note"] == "•••" and audit["uid"] == pseudonym("dev-uid-77", SECRET)
    # Un correo suelto dentro de un texto que no es clave privada también se oculta.
    assert view("integrations")({"summary": "falló para dev@empresa.com"})["summary"] == "falló para •••"
    assert view("integrations")({"summary": "revisó admin@example.com"})["summary"] == "revisó admin@example.com"


def test_public_earthquake_data_is_left_alone() -> None:
    official = {"event_id": "usgs:1", "preferred_report": {"place": "24 km al OSO de Sipí, Chocó", "latitude": 4.912345,
                "longitude": -76.2, "magnitude": 5.1, "agency": "USGS", "title": "Sismo M 5.1"}}
    assert view("official")(official) == official
    assert view("alerts")({"latitude": 4.912345, "place": "Bogotá"}) == {"latitude": 4.912345, "place": "Bogotá"}


# --- API ----------------------------------------------------------------------------------


async def api_client(admins: str = "admin@example.com"):
    settings = AppSettings(admin_emails=admins).model_copy(update={"admin_mfa_encryption_key": SecretStr(SECRET)})
    redis = FakeRedis(decode_responses=True)
    await redis.set(SESSION_PREFIX + digest("admin-token"), json.dumps({
        "uid": "admin-token", "email": "admin@example.com", "authenticated_at": str(int(time.time())),
        "last_seen": time.time(), "mfa_version": "v1"}))
    await redis.set(MFA_PREFIX + account({"uid": "admin-token"}), json.dumps({"version": "v1"}))
    app = FastAPI()
    for router in (admin_router, beta_router, security_router, reports_router):
        app.include_router(router)
    app.state.settings, app.state.redis = settings, redis
    app.dependency_overrides[get_app_settings] = lambda: settings
    app.dependency_overrides[get_redis] = lambda: redis
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://local")
    return client, redis, settings


async def approve(redis: FakeRedis, action: str) -> None:
    await redis.set("seismik:admin:approval:" + digest("approval"),
                    json.dumps({"session": digest("admin-token"), "action": action}), ex=120)


async def register_phone(redis: FakeRedis, device_id: str, platform: str = "ios", token: str = "t" * 64) -> None:
    await redis.hset(f"seismik:device:{device_id}", mapping={
        "device_id": device_id, "platform": platform, "token": token, "critical_alerts_authorized": "1"})


@pytest.mark.asyncio
async def test_the_records_endpoint_never_returns_family_names_or_customer_data() -> None:
    client, redis, settings = await api_client()
    await redis.xadd(settings.family_notification_stream, {"payload": json.dumps({
        "type": "family_status", "event_id": "family-1", "circle_id": "casa-perez", "member_id": "google-ana",
        "display_name": "Ana Pérez", "status": "need_help", "message": "Atrapada en el piso 3 de Calle 10",
        "related_event_id": "official-1", "reported_at": "2026-10-09T12:00:00+00:00"})})
    await redis.xadd(settings.account_deletion_request_stream, {"payload": json.dumps({
        "request_id": "delreq_1", "email": "cliente@correo.com", "details": "Mi dirección es Calle 1"})})
    async with client:
        family = await client.get("/v1/admin/records/family", headers=COOKIE_HEADERS)
        deletions = await client.get("/v1/admin/records/deletions", headers=COOKIE_HEADERS)

    text = family.text + deletions.text
    for private in ("Ana", "Pérez", "casa-perez", "google-ana", "Atrapada", "Calle", "cliente@correo.com"):
        assert private not in text, private
    assert family.json()["records"][0]["data"]["status"] == "need_help"
    assert deletions.json()["records"][0]["data"]["request_id"] == "delreq_1"


@pytest.mark.asyncio
async def test_the_report_review_list_keeps_only_a_coarse_location_and_no_comments() -> None:
    client, redis, settings = await api_client()
    await redis.xadd(settings.felt_reports_stream, {"payload": json.dumps({
        "report_id": "app-1", "device_id": "device-secret-0001", "latitude": 4.65432, "longitude": -74.05678,
        "country_code": "CO", "felt": True, "intensity_mmi": 4, "comment": "Soy Pedro, vivo en la carrera 7",
        "observed_at": "2026-10-09T12:00:00+00:00"})})
    async with client:
        response = await client.get("/v1/reports/admin/reports", headers=COOKIE_HEADERS)

    report = response.json()["reports"][0]["report"]
    assert response.status_code == 200
    assert (report["latitude"], report["longitude"]) == (4.7, -74.1)
    assert report["comment"] == "•••" and "Pedro" not in response.text and "carrera" not in response.text


@pytest.mark.asyncio
async def test_enrolling_a_phone_needs_mfa_and_a_registered_identifier() -> None:
    client, redis, _ = await api_client()
    await register_phone(redis, PHONE)
    async with client:
        body = {"device_id": PHONE, "label": "iPhone de Óscar"}
        assert (await client.post("/v1/admin/beta-phones", json=body, headers=COOKIE_HEADERS)).status_code == 428
        unknown = await client.post("/v1/admin/beta-phones", json={"device_id": "nunca-registrado-1", "label": "x"},
                                    headers=COOKIE_HEADERS)
        assert unknown.status_code == 404
        await approve(redis, f"beta:add:{phone_ref('otro-teléfono')}")
        assert (await client.post("/v1/admin/beta-phones", json=body, headers=COOKIE_HEADERS)).status_code == 428
        await approve(redis, f"beta:add:{phone_ref(PHONE)}")
        created = await client.post("/v1/admin/beta-phones", json=body, headers=COOKIE_HEADERS)
        assert created.status_code == 201
        again = await client.post("/v1/admin/beta-phones", json=body, headers=COOKIE_HEADERS)
        assert again.status_code == 409
        listed = (await client.get("/v1/admin/beta-phones", headers=COOKIE_HEADERS)).json()

    [phone] = listed["phones"]
    assert phone["label"] == "iPhone de Óscar" and phone["suffix"] == PHONE[-4:] and phone["push_ready"] is True
    assert phone["platform"] == "ios" and phone["critical_alerts"] is True
    assert PHONE not in json.dumps(listed), "el identificador completo no vuelve a salir"
    assert {item["id"] for item in listed["scenarios"]} == {"bogota", "pacifico", "atacama"}
    bogota = next(item for item in listed["scenarios"] if item["id"] == "bogota")
    assert {"latitude", "longitude", "magnitude", "depth_km", "country_code", "place"} <= set(bogota)


@pytest.mark.asyncio
async def test_only_configured_admins_reach_the_beta_and_drill_routes() -> None:
    client, _, _ = await api_client(admins="otra@example.com")
    async with client:
        assert (await client.get("/v1/admin/beta-phones", headers=COOKIE_HEADERS)).status_code == 403
        assert (await client.get("/v1/admin/drills", headers=COOKIE_HEADERS)).status_code == 403
        assert (await client.post("/v1/admin/drills", headers=COOKIE_HEADERS,
                                  json=drill_body(["a" * 16]))).status_code == 403
    client, _, _ = await api_client()
    async with client:
        assert (await client.get("/v1/admin/beta-phones")).status_code == 401


async def enroll(redis: FakeRedis, device_id: str, label: str = "Prueba") -> str:
    await register_phone(redis, device_id, "android" if "android" in device_id else "ios")
    ref = phone_ref(device_id)
    await redis.hset(PHONES_KEY, ref, json.dumps({"device_id": device_id, "label": label, "added_by": "admin@example.com"}))
    return ref


def drill_body(refs: list[str], **changes: object) -> dict:
    """Un simulacro con todos sus datos, como lo envía el panel."""

    return {"critical": True, "latitude": 5.0721, "longitude": -75.5138, "magnitude": 6.8, "depth_km": 12.5,
            "place": "Eje Cafetero", "origin_minutes_ago": 2, "country_code": "CO", "refs": refs, **changes}


def action_for(body: dict) -> str:
    return drill_action(DrillIn(**body))


@pytest.mark.asyncio
async def test_a_drill_carries_the_chosen_epicentre_and_is_bound_to_the_approval() -> None:
    client, redis, settings = await api_client()
    ref, other = await enroll(redis, PHONE), await enroll(redis, OTHER_PHONE)
    body = drill_body([ref])
    async with client:
        assert (await client.post("/v1/admin/drills", json=body, headers=COOKIE_HEADERS)).status_code == 428
        # Una aprobación para otros teléfonos, otra magnitud, otro lugar o otro epicentro no sirve.
        for changed in (drill_body([ref, other]), drill_body([ref], magnitude=7.9),
                        drill_body([ref], place="Otro sitio"), drill_body([ref], latitude=4.65),
                        drill_body([ref], critical=False), drill_body([ref], origin_minutes_ago=30)):
            await approve(redis, action_for(changed))
            assert (await client.post("/v1/admin/drills", json=body, headers=COOKIE_HEADERS)).status_code == 428
        await approve(redis, action_for(body))
        sent = await client.post("/v1/admin/drills", json=body, headers=COOKIE_HEADERS)
        assert sent.status_code == 202
        # Quien no está inscrito no recibe nada, aunque se conozca su código.
        ghost_body = drill_body(["f" * 16])
        await approve(redis, action_for(ghost_body))
        assert (await client.post("/v1/admin/drills", json=ghost_body, headers=COOKIE_HEADERS)).status_code == 409
        history = (await client.get("/v1/admin/drills", headers=COOKIE_HEADERS)).json()["drills"]

    [(_, fields)] = await redis.xrange(settings.admin_drill_stream)
    event = json.loads(fields["payload"])
    report = event["preferred_report"]
    assert event["type"] == "admin_drill" and event["event_id"].startswith("drill-")
    assert event["device_ids"] == [PHONE] and event["critical"] is True and event["requested_by"] == "admin@example.com"
    assert report["source_id"] == "simulation" and report["place"] == "Simulacro — Eje Cafetero"
    assert (report["latitude"], report["longitude"], report["magnitude"], report["depth_km"]) == (5.0721, -75.5138, 6.8, 12.5)
    assert report["jurisdiction"] == "CO"
    origin = datetime.fromisoformat(report["origin_time"])
    assert 100 < (datetime.fromisoformat(event["requested_at"]) - origin).total_seconds() < 140  # «hace 2 min»
    assert history[0]["id"] == event["event_id"] and history[0]["status"] == "queued" and history[0]["targets"] == "1"
    assert history[0]["magnitude"] == "6.8" and history[0]["place"] == "Simulacro — Eje Cafetero"
    assert PHONE not in json.dumps(history) and PHONE not in sent.text
    audit = [fields for _, fields in await redis.xrange(settings.developer_audit_stream)]
    assert audit[-1]["action"] == "drill.requested" and audit[-1]["by"] == "admin@example.com"


@pytest.mark.asyncio
async def test_a_drill_rejects_impossible_or_ambiguous_values_and_cannot_pass_for_a_real_quake() -> None:
    client, redis, _ = await api_client()
    ref = await enroll(redis, PHONE)
    async with client:
        for bad in ({"magnitude": 9.6}, {"magnitude": 0.5}, {"magnitude": 6.85}, {"latitude": 91}, {"longitude": -181},
                    {"latitude": 4.123456}, {"depth_km": 701}, {"depth_km": -1}, {"origin_minutes_ago": 121},
                    {"country_code": "col"}, {"place": "   "}, {"place": "x" * 61}, {"place": "Mal\x00lugar"},
                    {"scenario": "bogota"}):
            response = await client.post("/v1/admin/drills", json=drill_body([ref], **bad), headers=COOKIE_HEADERS)
            assert response.status_code == 422, bad
    assert DrillIn(**drill_body([ref], place="Sipí")).place == "Simulacro — Sipí"
    assert DrillIn(**drill_body([ref], place="simulacro en Cali")).place == "simulacro en Cali"  # no se duplica


@pytest.mark.asyncio
async def test_a_drill_is_rate_limited_and_needs_phones_that_can_receive_it() -> None:
    client, redis, _ = await api_client()
    ref = await enroll(redis, PHONE)
    async with client:
        await redis.hset(f"seismik:device:{PHONE}", "token", "")
        body = drill_body([ref], critical=False)
        assert (await client.post("/v1/admin/drills", json=body, headers=COOKIE_HEADERS)).status_code == 409
        await redis.hset(f"seismik:device:{PHONE}", "token", "t" * 64)
        statuses = []
        for _ in range(8):
            await approve(redis, action_for(body))
            statuses.append((await client.post("/v1/admin/drills", json=body, headers=COOKIE_HEADERS)).status_code)
    assert statuses[:6] == [202] * 6 and statuses[6:] == [429, 429]


@pytest.mark.asyncio
async def test_removing_a_phone_needs_mfa_and_ends_its_drills() -> None:
    client, redis, _ = await api_client()
    ref = await enroll(redis, PHONE)
    async with client:
        assert (await client.delete(f"/v1/admin/beta-phones/{ref}", headers=COOKIE_HEADERS)).status_code == 428
        await approve(redis, f"beta:remove:{ref}")
        assert (await client.delete(f"/v1/admin/beta-phones/{ref}", headers=COOKIE_HEADERS)).json() == {"phones": []}
        assert (await client.delete(f"/v1/admin/beta-phones/{ref}", headers=COOKIE_HEADERS)).status_code == 404
        assert (await client.delete("/v1/admin/beta-phones/no-valido", headers=COOKIE_HEADERS)).status_code == 422


# --- Dispatcher ---------------------------------------------------------------------------


class Devices:
    def __init__(self, *known: str) -> None:
        self.known = set(known)

    async def resolve(self, device_id: str) -> DeviceTarget | None:
        if device_id not in self.known:
            return None
        return DeviceTarget(device_id=device_id, platform="android", token="t" * 64)

    async def unregister(self, _device_id: str) -> bool:
        return True


class Push:
    def __init__(self) -> None:
        self.calls: list[tuple[dict, list[str], bool]] = []

    async def send(self, event, targets, *, critical):
        ids = [target.device_id for target in targets]
        self.calls.append((event, ids, critical))
        return PushResult(attempted=len(ids), succeeded=len(ids))


def drill_event(drill_id: str = "drill-abc", devices: tuple[str, ...] = (PHONE,), critical: bool = True) -> dict:
    return {
        "type": "admin_drill", "event_id": drill_id, "device_ids": list(devices), "critical": critical,
        "requested_by": "admin@example.com",
        "preferred_report": {"official_event_id": drill_id, "source_id": "simulation", "agency": "Simulacro Seismik",
                             "place": "Simulacro — Sabana de Bogotá", "latitude": 4.65, "longitude": -74.05,
                             "magnitude": 5.2, "depth_km": 25.0, "origin_time": "2026-10-09T12:00:00+00:00",
                             "jurisdiction": "CO", "attribution": "Simulacro de Seismik", "official_url": None},
    }


@pytest.mark.asyncio
async def test_the_dispatcher_sends_a_drill_only_to_phones_still_enrolled_and_only_once() -> None:
    redis = FakeRedis(decode_responses=True)
    settings = AppSettings()
    push = Push()
    consumer = StreamConsumer(redis, settings, Devices(PHONE, OTHER_PHONE), push)  # type: ignore[arg-type]
    assert settings.admin_drill_stream in consumer.streams
    await redis.hset(DRILL_KEY_PREFIX + "drill-abc", mapping={"status": "queued"})
    await redis.hset(PHONES_KEY, phone_ref(PHONE), json.dumps({"device_id": PHONE}))  # el otro ya no está inscrito

    event = drill_event(devices=(PHONE, OTHER_PHONE))
    await consumer._handle_admin_drill(event)
    await consumer._handle_admin_drill(event)  # una reentrega del stream no repite el simulacro

    assert len(push.calls) == 1
    sent, targets, critical = push.calls[0]
    assert targets == [PHONE] and critical is True and sent["type"] == "official_report_update"
    result = await redis.hgetall(DRILL_KEY_PREFIX + "drill-abc")
    assert result["status"] == "sent" and result["attempted"] == "1" and result["succeeded"] == "1"
    # Nada de lo que hace un sismo real: ni integraciones, ni bitácora, ni familias.
    assert await redis.xlen(settings.integration_stream) == 0
    assert await redis.xlen(settings.alert_ledger_stream) == 0
    assert await redis.xlen(settings.family_notification_stream) == 0


@pytest.mark.asyncio
async def test_the_dispatcher_rejects_a_drill_without_a_drill_identifier() -> None:
    redis = FakeRedis(decode_responses=True)
    push = Push()
    consumer = StreamConsumer(redis, AppSettings(), Devices(PHONE), push)  # type: ignore[arg-type]
    await redis.hset(PHONES_KEY, phone_ref(PHONE), json.dumps({"device_id": PHONE}))

    with pytest.raises(ValueError):
        await consumer._handle_admin_drill(drill_event("official-123"))
    assert push.calls == []


@pytest.mark.asyncio
async def test_a_drill_routed_through_the_stream_handler_does_not_reach_the_alert_policy() -> None:
    redis = FakeRedis(decode_responses=True)
    settings = AppSettings()
    push = Push()
    consumer = StreamConsumer(redis, settings, Devices(PHONE), push)  # type: ignore[arg-type]
    await redis.hset(PHONES_KEY, phone_ref(PHONE), json.dumps({"device_id": PHONE}))
    await consumer.ensure_groups()
    await redis.xadd(settings.admin_drill_stream, {"payload": json.dumps(drill_event())})

    [(stream, entries)] = await redis.xreadgroup(
        settings.dispatcher_group, settings.consumer_name, {settings.admin_drill_stream: ">"}, count=5)
    for message_id, fields in entries:
        await consumer._handle(stream, message_id, fields)

    assert [call[1] for call in push.calls] == [[PHONE]]
    assert (await redis.xpending(settings.admin_drill_stream, settings.dispatcher_group))["pending"] == 0


def test_a_drill_notification_says_simulacro() -> None:
    event = {**drill_event(), "type": "official_report_update"}

    critical_title, body, data = notification_content(event, critical=True)
    notice_title, _, _ = notification_content(event, critical=False)

    assert critical_title.startswith("SIMULACRO: ") and notice_title.startswith("SIMULACRO: ")
    assert "Simulacro" in body and data["event_id"] == "drill-abc" and data["critical"] is True
    real = {**event, "event_id": "official-1"}
    assert not notification_content(real, critical=True)[0].startswith("SIMULACRO")


def test_the_approval_fingerprint_is_the_one_the_panel_computes() -> None:
    """El panel (web/admin.js) calcula el mismo texto; tests/admin_panel.test.mjs fija el mismo valor."""

    body = {"critical": True, "latitude": 5.0721, "longitude": -75.5138, "magnitude": 6.8, "depth_km": 12.5,
            "place": "Simulacro — Eje Cafetero", "origin_minutes_ago": 2, "country_code": "CO",
            "refs": ["d5659ff255ec655c"]}
    assert drill_action(DrillIn(**body)) == "drill:979dad1ae1e74393"
