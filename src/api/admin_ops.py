"""admin.seismik.org: estado, configuración, alertas, flota, auditoría, plataforma, seguridad y solicitudes.

Todo lo que sale de aquí es agregado (nunca una persona concreta) o pasa por el filtro de
privacidad de `api.admin_privacy`. Las lecturas de «solo ver» responden bloques listos para
pintar: `{"type": "kpis" | "table" | "note", ...}`. Las acciones que cambian algo piden un código
MFA nuevo ligado a esa acción y quedan en la auditoría.
"""
from __future__ import annotations

import json
import os
import re
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, cast

import httpx
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from redis.asyncio import Redis

from api.admin import MAX_SCANNED_KEYS, _decode, _stream_time, redact, streams
from api.admin_notify import notify
from api.admin_privacy import view_for
from api.admin_security import (
    COOKIE,
    SESSION_PREFIX,
    digest,
    readonly,
    require_action,
    require_admin,
)
from api.config import AppSettings
from api.dependencies import get_app_settings, get_redis
from api.felt_area import describe, haversine_km, intensity_at, roman
from api.runtime_controls import INFO_PREFIX, state
from api.schemas import DeviceTarget, Platform
from dispatcher.policy import ALWAYS_ALARM_MMI, EARLY_ALARM_MMI, OFFICIAL_NOTICE_MMI, AlertPolicy
from reporting.web import official_events

router = APIRouter(prefix="/v1/admin", tags=["admin-ops"])

STARTED_AT = datetime.now(timezone.utc).isoformat()
SMALL_GROUP = 5  # un grupo de menos de 5 se muestra como «<5»: no se señala a nadie
DELETION_KEY = "seismik:admin:deletion-status"
TEMPLATES_KEY = "seismik:admin:drill-templates"
DELETION_DEADLINE_DAYS = 30
SENSITIVE_ACTIONS = frozenset({
    "operation.paused", "operation.resumed", "alert.skipped_paused", "beta_phone.enrolled", "beta_phone.removed",
    "drill.requested", "report_review", "admin.mfa_verified", "admin.mfa_recovery", "admin.primary_login",
    "session.revoked", "deletion.status", "template.saved", "template.deleted",
})
ACTION_LABELS = {
    "operation.paused": "Pausó una función", "operation.resumed": "Reanudó una función",
    "alert.skipped_paused": "Alerta omitida por pausa", "beta_phone.enrolled": "Inscribió un teléfono de prueba",
    "beta_phone.removed": "Quitó un teléfono de prueba", "drill.requested": "Pidió un simulacro",
    "report_review": "Revisó un reporte", "admin.mfa_verified": "Verificó MFA", "admin.mfa_recovery": "Entró con código de recuperación",
    "admin.primary_login": "Inició sesión", "session.revoked": "Cerró una sesión de administración",
    "deletion.status": "Cambió una solicitud de borrado", "template.saved": "Guardó una plantilla de simulacro",
    "template.deleted": "Borró una plantilla de simulacro", "key_created": "Creó una clave de API", "key_revoked": "Revocó una clave de API",
}
DELETION_STATUSES = ("pending", "verifying", "in_progress", "completed", "rejected")


# --- bloques para pintar -------------------------------------------------------------------------


def kpis(*items: tuple[Any, ...]) -> dict[str, Any]:
    """Cada tarjeta es (etiqueta, valor[, tono[, ayuda]]); tono: ok, warn, bad."""

    def card(item: tuple[Any, ...]) -> dict[str, Any]:
        padded = (*item, None, None)
        return {"label": padded[0], "value": str(padded[1]), "tone": padded[2], "hint": padded[3]}

    return {"type": "kpis", "items": [card(item) for item in items]}


def table(title: str, columns: list[str], rows: list[list[Any]], empty: str = "Sin datos.") -> dict[str, Any]:
    return {"type": "table", "title": title, "columns": columns, "rows": rows, "empty": empty}


def note(text: str, tone: str | None = None) -> dict[str, Any]:
    return {"type": "note", "text": text, "tone": tone}


def small(count: int) -> str:
    return f"<{SMALL_GROUP}" if 0 < count < SMALL_GROUP else f"{count:,}".replace(",", ".")


def ago_text(moment: datetime | None, now: datetime) -> str:
    if moment is None:
        return "—"
    seconds = max(0, int((now - moment).total_seconds()))
    if seconds < 90:
        return f"hace {seconds} s"
    if seconds < 5400:
        return f"hace {round(seconds / 60)} min"
    if seconds < 172_800:
        return f"hace {round(seconds / 3600)} h"
    return f"hace {round(seconds / 86_400)} d"


def parse_time(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value)
    try:
        if re.fullmatch(r"\d{9,11}(\.\d+)?", text):
            return datetime.fromtimestamp(float(text), timezone.utc)
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (ValueError, OverflowError, OSError):
        return None


def clock(moment: datetime | None) -> str:
    return moment.astimezone(timezone(timedelta(hours=-5))).strftime("%d/%m %H:%M") if moment else "—"


async def _entries(redis: Redis, stream: str, count: int) -> list[tuple[str, dict[str, Any]]]:
    raw = cast(list[tuple[str, dict[str, str]]], await redis.xrevrange(stream, count=count))
    return [(stream_id, _decode(fields)) for stream_id, fields in raw]


async def _recent_count(redis: Redis, stream: str, since: datetime) -> int:
    raw = cast(list[Any], await redis.xrange(stream, min=f"{int(since.timestamp() * 1000)}-0", max="+", count=10_000))
    return len(raw)


# --- estado y configuración efectiva ----------------------------------------------------------------


async def _public_availability() -> list[list[Any]] | None:
    """Disponibilidad pública de 30 días, de status.seismik.org (dato público)."""

    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            data = (await client.get("https://status.seismik.org/api/history")).json()
    except Exception:
        return None
    if not isinstance(data, dict) or not data.get("available"):
        return None
    totals: dict[str, list[int]] = {"api": [0, 0], "web": [0, 0], "developers": [0, 0]}
    if isinstance(data.get("days"), list):
        for day in data["days"]:
            for name, counts in (day.get("services") or {}).items():
                if name in totals:
                    totals[name][0] += int(counts.get("healthy", 0))
                    totals[name][1] += int(counts.get("healthy", 0)) + int(counts.get("failed", 0))
    elif isinstance(data.get("services"), dict):
        for name, windows in data["services"].items():
            window = (windows or {}).get("last_30d") or {}
            if name in totals and window.get("uptime") is not None:
                totals[name] = [int(float(window["uptime"]) * 100), 10_000]
    labels = {"api": "API pública", "web": "Sitio web", "developers": "Portal de desarrolladores"}
    return [[labels[name], f"{100 * ok / total:.2f} %" if total else "sin datos", f"{total:,}".replace(",", ".")]
            for name, (ok, total) in totals.items()]


def _flag_text(value: Any) -> str:
    return "sí" if value is True else "no" if value is False else str(value)


@router.get("/system")
async def system(
    response: Response, admin: str = Depends(require_admin),
    settings: AppSettings = Depends(get_app_settings), redis: Redis = Depends(get_redis),
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    now = datetime.now(timezone.utc)
    started = time.perf_counter()
    await redis.ping()
    redis_ms = (time.perf_counter() - started) * 1000

    infos: list[dict[str, Any]] = []
    async for key in redis.scan_iter(match=f"{INFO_PREFIX}*", count=100):
        raw, ttl = await redis.get(key), await redis.ttl(key)
        try:
            info = json.loads(raw or "")
        except ValueError:
            continue
        info["age_seconds"] = max(0, 90 - int(ttl)) if ttl and ttl > 0 else 90
        infos.append(info)
    infos.sort(key=lambda item: str(item.get("role")))
    controls = {item["id"]: item for item in await state(redis)}
    by_role = {str(info.get("role")): info for info in infos}

    def publisher(feature: str, flags_key: str, dry_key: str) -> tuple[str, str]:
        flags = (by_role.get("integrations") or {}).get("flags")
        control = controls.get(feature, {})
        if flags is None:
            return "Sin conexión reciente", "warn"
        if control.get("paused"):
            return "Pausada desde el panel", "ok"
        if not flags.get(flags_key):
            return "Apagada", "ok"
        if flags.get(dry_key):
            return "Simulación (no publica)", "ok"
        return ("Publicando de verdad", "bad") if control.get("configured") else ("Encendida pero sin credenciales", "warn")

    x_text, x_tone = publisher("x", "x_publisher_enabled", "x_publisher_dry_run")
    fb_text, fb_tone = publisher("facebook", "facebook_publisher_enabled", "facebook_publisher_dry_run")
    alerts_flags = (by_role.get("alerts") or {}).get("flags") or {}
    push_text = (
        "Sin conexión reciente" if not alerts_flags else
        "Apagado" if not alerts_flags.get("push_enabled") else str(alerts_flags.get("push_mode"))
    )
    revision = os.environ.get("K_REVISION", "")
    blocks: list[dict[str, Any]] = [
        kpis(
            ("Publicación en X", x_text, x_tone, "Según el servicio que la ejecuta, no según lo que se espera"),
            ("Publicación en Facebook", fb_text, fb_tone),
            ("Push a teléfonos", push_text, "ok" if push_text == "production" else "warn", "dry_run, testers o production"),
            ("Redis", f"{redis_ms:.0f} ms", "ok" if redis_ms < 50 else "warn"),
        ),
    ]

    service_rows: list[list[Any]] = [["API", os.environ.get("K_SERVICE", "—") or "—", revision or "—", "este servicio", clock(parse_time(STARTED_AT))]]
    labels = {"alerts": "Dispatcher (alertas)", "integrations": "Dispatcher (X, Facebook, catálogo)"}
    for info in infos:
        service_rows.append([
            labels.get(str(info.get("role")), str(info.get("role"))), str(info.get("service") or "—"),
            str(info.get("revision") or "—"), f"hace {info['age_seconds']} s", clock(parse_time(info.get("started_at"))),
        ])
    blocks.append(table("Qué corre ahora", ["Servicio", "Nombre", "Revisión", "Último latido", "Arrancó"], service_rows))
    for role, label in labels.items():
        if role not in by_role:
            blocks.append(note(f"{label}: sin latido en los últimos 90 s. Puede estar desplegándose o caído.", "warn"))

    config_rows: list[list[Any]] = [
        ["API", "environment", settings.environment],
        ["API", "verificación de integridad (App Check)", _flag_text(settings.integrity_verification_enabled)],
        ["API", "inicio de sesión con correo", _flag_text(settings.email_login_enabled)],
        ["API", "cuentas de solo lectura", str(len([x for x in settings.admin_readonly_emails.split(",") if x.strip()]))],
        ["API", "aviso de acciones sensibles", "configurado" if settings.admin_alert_webhook_url.get_secret_value() else "sin configurar"],
    ]
    for role in ("alerts", "integrations"):
        for flag, value in sorted(((by_role.get(role) or {}).get("flags") or {}).items()):
            config_rows.append([labels[role], flag, _flag_text(value)])
    for feature in controls.values():
        config_rows.append(["Controles", feature["label"], "pausado" if feature["paused"] else "activo" if feature["enabled"] else "no configurado para envíos"])
    blocks.append(table("Configuración efectiva (solo lectura)", ["Componente", "Ajuste", "Valor"], config_rows))

    freshness: list[list[Any]] = []
    for name in ("official", "candidates", "alerts", "dead_letter", "integration_failures"):
        stream, title = streams(settings)[name]
        last = cast(list[tuple[str, dict[str, str]]], await redis.xrevrange(stream, count=1))
        last_at = _stream_time(last[0][0]) if last else None
        freshness.append([title, clock(last_at), ago_text(last_at, now), str(await _recent_count(redis, stream, now - timedelta(days=1))) if last else "0"])
    blocks.append(table("Actividad de los registros", ["Registro", "Último", "Hace", "Últimas 24 h"], freshness))

    availability = await _public_availability()
    blocks.append(table("Disponibilidad pública (30 días)", ["Servicio", "Comprobaciones correctas", "Comprobaciones"], availability or [], "No se pudo consultar status.seismik.org."))
    blocks.append(note(
        "Estaciones sísmicas: todavía no hay un latido del detector en Redis, así que el panel no puede decir cuándo llegó el "
        "último dato de cada una. Falta que el detector lo publique; no se tocó para no redesplegarlo.", "warn"))
    return {"generated_at": now.isoformat(), "blocks": blocks}


# --- alertas y alcance ----------------------------------------------------------------------------


@router.get("/alerts")
async def alerts(
    response: Response, admin: str = Depends(require_admin),
    settings: AppSettings = Depends(get_app_settings), redis: Redis = Depends(get_redis),
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    now = datetime.now(timezone.utc)
    raw_ledger = cast(list[tuple[str, dict[str, str]]], await redis.xrevrange(settings.alert_ledger_stream, count=200))
    sent_rows: list[list[Any]] = []
    alerted: set[str] = set()
    last_24h = {"alarm": 0, "notice": 0, "reached": 0}
    for stream_id, fields in raw_ledger:
        payload = _decode({"payload": fields["payload"]}) if fields.get("payload") else {}
        moment = parse_time(fields.get("emitted_at")) or _stream_time(stream_id)
        critical = str(fields.get("critical")).lower() == "true"
        delivered = int(fields.get("delivered") or 0)
        alerted.add(str(fields.get("event_id", "")))
        if now - moment <= timedelta(days=1):
            last_24h["alarm" if critical else "notice"] += 1
            last_24h["reached"] += delivered
        if len(sent_rows) < 25:
            magnitude = payload.get("magnitude")
            sent_rows.append([clock(moment), "Alarma" if critical else "Aviso",
                              f"{float(magnitude):.1f}" if isinstance(magnitude, (int, float)) else "—",
                              str(payload.get("place") or payload.get("zone_id") or "—"), small(delivered),
                              str(fields.get("event_id", ""))[:28]])
    official_rows: list[list[Any]] = []
    seen: set[str] = set()
    for _, event in await _entries(redis, settings.official_stream, 300):
        report = event.get("preferred_report") or {}
        event_id = str(event.get("event_id", ""))
        if not event_id or event_id in seen or not isinstance(report, dict):
            continue
        seen.add(event_id)
        if len(official_rows) < 20:
            magnitude = report.get("magnitude")
            depth = report.get("depth_km")
            official_rows.append([clock(parse_time(report.get("origin_time"))),
                                  f"{float(magnitude):.1f}" if isinstance(magnitude, (int, float)) else "—",
                                  str(report.get("place") or "—"),
                                  f"{float(depth):.0f} km" if isinstance(depth, (int, float)) else "—",
                                  str(report.get("agency") or "—"), "Sí" if event_id in alerted else "No"])
    candidate_rows = []
    for _, event in await _entries(redis, settings.candidate_stream, 20):
        magnitude = event.get("magnitude_estimate")
        candidate_rows.append([clock(parse_time(event.get("detected_at"))), str(event.get("zone_id") or "—"),
                               str(event.get("station_count") or len(event.get("stations") or []) or "—"),
                               f"{float(magnitude):.1f}" if isinstance(magnitude, (int, float)) else "sin magnitud",
                               "Sí" if str(event.get("event_id", "")) in alerted else "No"])
    return {"generated_at": now.isoformat(), "blocks": [
        kpis(("Alarmas (24 h)", last_24h["alarm"]), ("Avisos (24 h)", last_24h["notice"]),
             ("Dispositivos alcanzados (24 h)", small(last_24h["reached"]), None, "Suma de envíos; un teléfono puede contar varias veces")),
        table("Alertas enviadas", ["Hora (Colombia)", "Tipo", "M", "Lugar", "Dispositivos", "Evento"], sent_rows, "Aún no hay alertas enviadas."),
        table("Sismos oficiales recientes", ["Hora (Colombia)", "M", "Lugar", "Profundidad", "Agencia", "¿Alertó?"], official_rows),
        table("Detecciones propias recientes", ["Hora (Colombia)", "Zona", "Estaciones", "Magnitud", "¿Alertó?"], candidate_rows),
    ]}


@router.get("/alerts/explain")
async def explain(
    response: Response,
    latitude: float = Query(ge=-90, le=90), longitude: float = Query(ge=-180, le=180),
    epicenter_latitude: float = Query(ge=-90, le=90), epicenter_longitude: float = Query(ge=-180, le=180),
    magnitude: float = Query(ge=1, le=9.5), depth_km: float = Query(default=10, ge=0, le=700),
    minutes_ago: int = Query(default=1, ge=0, le=1440), radius_km: float = Query(default=250, ge=10, le=2000),
    receive_official: bool = True, minimum_magnitude: float = Query(default=4.0, ge=0, le=10),
    admin: str = Depends(require_admin), settings: AppSettings = Depends(get_app_settings),
    redis: Redis = Depends(get_redis),
) -> dict[str, Any]:
    """«¿Por qué sonó o no sonó en este punto?»: la política real, con un teléfono imaginario."""

    response.headers["Cache-Control"] = "no-store"
    target = DeviceTarget(
        device_id="explain-device", platform=Platform.ANDROID, token="x" * 32, latitude=latitude, longitude=longitude,
        alert_radius_km=radius_km, receive_official_updates=receive_official, minimum_notification_magnitude=minimum_magnitude,
    )
    policy = AlertPolicy(redis, settings)
    origin = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    distance = haversine_km(epicenter_latitude, epicenter_longitude, latitude, longitude)
    expected = intensity_at(magnitude, depth_km, distance)
    official = policy.classify_official(
        target, magnitude=magnitude, latitude=epicenter_latitude, longitude=epicenter_longitude,
        depth_km=depth_km, origin_time=origin.isoformat(),
    )
    early = bool(policy.filter_critical([target], latitude=epicenter_latitude, longitude=epicenter_longitude, magnitude=magnitude))
    decision = {"alarm": "Alarma", "notice": "Aviso"}.get(str(official), "Nada")
    reasons: list[list[Any]] = [
        ["Distancia al epicentro", f"{distance:.0f} km", "Haversine entre el punto y el epicentro"],
        ["Intensidad esperada", f"{roman(expected)} ({expected:.1f}) · {describe(expected)}", "Allen 2012 (corteza) / Zhao 2006 (profundo)"],
        [f"Alarma desde MMI {ALWAYS_ALARM_MMI:g}", "sí" if expected >= ALWAYS_ALARM_MMI else "no",
         f"Si el reporte tiene más de {settings.official_alarm_max_age_minutes:g} min baja a aviso (este tiene {minutes_ago})"],
        [f"Aviso desde MMI {OFFICIAL_NOTICE_MMI:g}", "sí" if expected >= OFFICIAL_NOTICE_MMI else "no",
         "Sólo si el teléfono recibe reportes oficiales" + ("" if receive_official else " (aquí los apagó)")],
        [f"Alerta temprana del detector desde MMI {EARLY_ALARM_MMI:g}", "llegaría" if early else "no llegaría",
         "Usa el radio elegido por la persona y su magnitud mínima"],
    ]
    return {"blocks": [
        kpis(("Distancia", f"{distance:.0f} km"), ("Intensidad esperada", f"{roman(expected)} · {describe(expected)}"),
             ("Reporte oficial", decision, "bad" if decision == "Alarma" else "warn" if decision == "Aviso" else "ok"),
             ("Alerta temprana", "Llegaría" if early else "No llegaría", "bad" if early else "ok")),
        table("Cómo se decidió", ["Paso", "Resultado", "Detalle"], reasons),
        note("Es la política real del dispatcher aplicada a un teléfono imaginario en el punto que elegiste. No lee datos de ningún cliente."),
    ]}


# --- flota agregada ---------------------------------------------------------------------------------


@router.get("/fleet")
async def fleet(
    response: Response, admin: str = Depends(require_admin),
    settings: AppSettings = Depends(get_app_settings), redis: Redis = Depends(get_redis),
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    now = datetime.now(timezone.utc)
    keys: list[str] = []
    complete = True
    async for key in redis.scan_iter(match="seismik:device:*", count=1000):
        text = str(key)
        if text.startswith(("seismik:device:account:", "seismik:device-session:")):
            continue
        if len(keys) >= MAX_SCANNED_KEYS:
            complete = False
            break
        keys.append(text)
    total = Counter[str]()
    platform = Counter[str]()
    country = Counter[str]()
    activity = Counter[str]()
    radius = Counter[str]()
    minimum = Counter[str]()
    for offset in range(0, len(keys), 500):
        pipe = redis.pipeline(transaction=False)
        for key in keys[offset:offset + 500]:
            pipe.hgetall(key)
        for record in await pipe.execute(raise_on_error=False):
            if not isinstance(record, dict) or not record:
                continue
            total["devices"] += 1
            platform[str(record.get("platform") or "?")] += 1
            has_token = bool(record.get("token"))
            total["token"] += has_token
            total["critical"] += record.get("critical_alerts_authorized") == "1"
            total["critical_ready"] += has_token and record.get("critical_alerts_authorized") == "1"
            total["early"] += record.get("receive_early_alerts", "1") == "1"
            total["official"] += record.get("receive_official_updates", "1") == "1"
            total["verified"] += record.get("integrity_verified") == "1"
            country[str(record.get("country_code") or "sin país")] += 1
            moment = parse_time(record.get("updated_at"))
            age = (now - moment) if moment else None
            activity["día" if age and age <= timedelta(days=1) else "semana" if age and age <= timedelta(days=7)
                     else "mes" if age and age <= timedelta(days=30) else "antiguo"] += 1
            km = float(record.get("alert_radius_km") or 250)
            radius["hasta 100 km" if km <= 100 else "101–250 km" if km <= 250 else "251–500 km" if km <= 500 else "más de 500 km"] += 1
            magnitude = float(record.get("minimum_notification_magnitude") or 4)
            minimum["menos de 3" if magnitude < 3 else "3 a 3,9" if magnitude < 4 else "4 a 4,9" if magnitude < 5 else "5 o más"] += 1

    def share(part: int) -> str:
        return f"{100 * part / total['devices']:.0f} %" if total["devices"] else "—"

    def grouped(counter: Counter[str], order: list[str] | None = None) -> list[list[Any]]:
        names = order or [name for name, _ in counter.most_common()]
        rows = [[name, small(counter[name]), share(counter[name])] for name in names if counter[name] >= SMALL_GROUP]
        hidden = sum(counter[name] for name in names if 0 < counter[name] < SMALL_GROUP)
        # Un porcentaje de un grupo pequeño delata la cifra que se oculta: sin porcentaje.
        return rows + ([["Otros (grupos de menos de 5)", small(hidden) if hidden < SMALL_GROUP else str(hidden), "—" if hidden < SMALL_GROUP else share(hidden)]] if hidden else [])

    invalid = []
    for back in range(7):
        day = now - timedelta(days=back)
        invalid.append([day.strftime("%d/%m"), str(int(await redis.get(f"seismik:metrics:invalid-tokens:{day:%Y%m%d}") or 0))])
    blocks: list[dict[str, Any]] = [
        kpis(("Dispositivos", small(total["devices"])), ("Con token de notificaciones", share(total["token"]), None, "Sin token no reciben alertas"),
             ("Alertas críticas listas", share(total["critical_ready"]), None, "Con token y permiso crítico concedido"),
             ("Activos esta semana", share(activity["día"] + activity["semana"]), None, "Última actualización del registro")),
        table("Plataforma", ["Plataforma", "Dispositivos", "%"], grouped(platform)),
        table("Preferencias", ["Ajuste", "Dispositivos", "%"], [
            ["Permiso de alertas críticas", small(total["critical"]), share(total["critical"])],
            ["Alertas tempranas activadas", small(total["early"]), share(total["early"])],
            ["Reportes oficiales activados", small(total["official"]), share(total["official"])],
            ["Verificados (App Check)", small(total["verified"]), share(total["verified"])],
        ]),
        table("País", ["País", "Dispositivos", "%"], grouped(country)),
        table("Radio elegido", ["Radio", "Dispositivos", "%"], grouped(radius, ["hasta 100 km", "101–250 km", "251–500 km", "más de 500 km"])),
        table("Magnitud mínima elegida", ["Magnitud", "Dispositivos", "%"], grouped(minimum, ["menos de 3", "3 a 3,9", "4 a 4,9", "5 o más"])),
        table("Última actualización del registro", ["Hace", "Dispositivos", "%"], grouped(activity, ["día", "semana", "mes", "antiguo"])),
        table("Tokens rechazados por APNs/FCM (por día)", ["Día", "Tokens purgados"], invalid),
        note("Todo es agregado: ningún dispositivo ni persona se muestra, y los grupos de menos de 5 salen como «<5». "
             "La versión de la app todavía no se guarda en el registro del dispositivo, por eso no aparece.", None),
    ]
    if not complete:
        blocks.append(note("Recuento parcial: hay demasiados dispositivos para contarlos todos.", "warn"))
    return {"generated_at": now.isoformat(), "blocks": blocks}


# --- auditoría ---------------------------------------------------------------------------------------


@router.get("/audit")
async def audit_log(
    response: Response, limit: int = Query(default=200, ge=1, le=500), sensitive: bool = False,
    admin: str = Depends(require_admin), settings: AppSettings = Depends(get_app_settings), redis: Redis = Depends(get_redis),
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    private = view_for("developer_audit", settings)
    raw = cast(list[tuple[str, dict[str, str]]], await redis.xrevrange(settings.developer_audit_stream, count=limit * 3 if sensitive else limit))
    rows: list[list[Any]] = []
    for stream_id, fields in raw:
        data = private(redact(_decode(fields)))
        action = str(data.get("action") or "—")
        is_sensitive = action in SENSITIVE_ACTIONS
        if sensitive and not is_sensitive:
            continue
        moment = parse_time(data.get("at")) or _stream_time(stream_id)
        detail = " · ".join(f"{key}={value}" for key, value in data.items() if key not in {"action", "by", "at"} and value not in (None, "", "•••"))
        rows.append([clock(moment), ACTION_LABELS.get(action, action), str(data.get("by") or "—"), detail[:160], "Sensible" if is_sensitive else ""])
        if len(rows) >= limit:
            break
    return {"blocks": [
        kpis(("Entradas mostradas", len(rows)), ("Sensibles", sum(1 for row in rows if row[4]))),
        table("Quién hizo qué", ["Hora (Colombia)", "Acción", "Quién", "Detalle", ""], rows, "Sin entradas."),
        note("Tus acciones sensibles pueden avisar a un canal: define SEISMIK_ADMIN_ALERT_WEBHOOK_URL (Slack, Discord u otro) en la API."
             if not settings.admin_alert_webhook_url.get_secret_value() else "Las acciones sensibles se avisan al canal configurado."),
    ]}


# --- plataforma de desarrolladores -------------------------------------------------------------------


@router.get("/usage")
async def usage(
    response: Response, admin: str = Depends(require_admin),
    settings: AppSettings = Depends(get_app_settings), redis: Redis = Depends(get_redis),
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    now = datetime.now(timezone.utc)
    plans = Counter[str]()
    async for key in redis.scan_iter(match="seismik:developer-profile:*", count=500):
        plans[str(await redis.hget(key, "selected_plan_id") or "free")] += 1
    key_status = Counter[str]()
    used_today = 0
    async for key in redis.scan_iter(match="seismik:developer-key:*", count=500):
        record = cast(dict[str, str], await redis.hgetall(key))
        if not record:
            continue
        key_status[record.get("status", "active")] += 1
        moment = parse_time(record.get("last_used_at"))
        used_today += bool(moment and now - moment <= timedelta(days=1))
    requests_today = 0
    busiest = 0
    async for key in redis.scan_iter(match=f"seismik:developer-usage:day:*:{now:%Y%m%d}", count=500):
        count = int(await redis.get(key) or 0)
        requests_today += count
        busiest = max(busiest, count)
    failures = await _recent_count(redis, settings.integration_dead_letter_stream, now - timedelta(days=1))
    delivered = 0
    for _, fields in cast(list[tuple[str, dict[str, str]]], await redis.xrevrange(settings.integration_audit_stream, count=2000)):
        if fields.get("action") == "webhook.delivered":
            moment = parse_time(fields.get("at"))
            delivered += bool(moment and now - moment <= timedelta(days=1))
    plan_rows = [[name, small(count)] for name, count in plans.most_common()]
    return {"generated_at": now.isoformat(), "blocks": [
        kpis(("Cuentas de desarrollador", small(sum(plans.values()))), ("Claves activas", small(key_status["active"])),
             ("Consultas hoy (UTC)", requests_today), ("Claves usadas en 24 h", small(used_today)),
             ("Webhooks entregados (24 h)", delivered),
             ("Webhooks fallidos (24 h)", failures, "bad" if failures else "ok")),
        table("Planes", ["Plan", "Cuentas"], plan_rows, "Aún no hay cuentas."),
        table("Claves", ["Estado", "Claves"], [[name, small(count)] for name, count in key_status.most_common()], "Aún no hay claves."),
        note(f"La clave más usada hoy hizo {busiest:,} consultas.".replace(",", ".") + " No se muestran nombres, correos ni claves."),
    ]}


# --- seguridad del panel -----------------------------------------------------------------------------


@router.get("/sessions")
async def sessions(
    request: Request, response: Response, admin: str = Depends(require_admin),
    settings: AppSettings = Depends(get_app_settings), redis: Redis = Depends(get_redis),
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    now = time.time()
    current = SESSION_PREFIX + digest(request.cookies.get(COOKIE, ""))
    rows: list[dict[str, Any]] = []
    async for key in redis.scan_iter(match=f"{SESSION_PREFIX}*", count=200):
        raw = await redis.get(key)
        try:
            user = json.loads(raw or "")
        except ValueError:
            continue
        rows.append({
            "ref": str(key).removeprefix(SESSION_PREFIX)[:16], "email": str(user.get("email", "")),
            "authenticated_at": datetime.fromtimestamp(float(user.get("authenticated_at", 0)), timezone.utc).isoformat(),
            "last_seen": datetime.fromtimestamp(float(user.get("last_seen", 0)), timezone.utc).isoformat(),
            "mfa": bool(user.get("mfa_version")), "current": str(key) == current,
        })
    rows.sort(key=lambda item: item["last_seen"], reverse=True)
    mfa_attempts = 0
    async for key in redis.scan_iter(match=f"seismik:admin:rate:mfa-hour:*:{int(now // 3600)}", count=200):
        mfa_attempts += int(await redis.get(key) or 0)
    readonly = [item.strip() for item in settings.admin_readonly_emails.split(",") if item.strip()]
    return {"sessions": rows, "mfa_attempts_hour": mfa_attempts, "readonly_accounts": len(readonly),
            "admin_accounts": len([item for item in settings.admin_emails.split(",") if item.strip()])}


@router.delete("/sessions/{ref}")
async def revoke_session(
    request: Request, response: Response, ref: str = Path(pattern=r"^[0-9a-f]{16}$"),
    admin: str = Depends(require_admin), settings: AppSettings = Depends(get_app_settings), redis: Redis = Depends(get_redis),
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    matches = [key async for key in redis.scan_iter(match=f"{SESSION_PREFIX}{ref}*", count=200)]
    if len(matches) != 1:
        raise HTTPException(404, "Sesión no encontrada")
    await require_action(request, redis, f"session:revoke:{ref}")
    await redis.delete(matches[0])
    await redis.xadd(settings.developer_audit_stream, {"action": "session.revoked", "ref": ref, "by": admin, "at": datetime.now(timezone.utc).isoformat()},
                     maxlen=settings.stream_maxlen, approximate=True)
    notify(settings, f"{admin} cerró una sesión de administración")
    return {"revoked": True}


# --- solicitudes de borrado ---------------------------------------------------------------------------


class DeletionChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["pending", "verifying", "in_progress", "completed", "rejected"]


@router.get("/deletions")
async def deletions(
    response: Response, admin: str = Depends(require_admin),
    settings: AppSettings = Depends(get_app_settings), redis: Redis = Depends(get_redis),
) -> dict[str, Any]:
    """Cola con estado y plazo. Nunca muestra el correo ni lo que escribió la persona."""

    response.headers["Cache-Control"] = "no-store"
    now = datetime.now(timezone.utc)
    stored = cast(dict[str, str], await redis.hgetall(DELETION_KEY))
    requests = []
    for _, data in await _entries(redis, settings.account_deletion_request_stream, 500):
        request_id = str(data.get("request_id", ""))
        received = parse_time(data.get("received_at"))
        if not request_id or received is None:
            continue
        record = json.loads(stored[request_id]) if request_id in stored else {}
        status = record.get("status", "pending")
        due = received + timedelta(days=DELETION_DEADLINE_DAYS)
        requests.append({
            "request_id": request_id, "received_at": received.isoformat(), "due_at": due.isoformat(), "status": status,
            "overdue": status not in {"completed", "rejected"} and now > due, "scope": str(data.get("scope") or "—"),
            "source": str(data.get("source") or "—"), "updated_by": record.get("by"), "updated_at": record.get("at"),
        })
    open_requests = [item for item in requests if item["status"] not in {"completed", "rejected"}]
    return {"requests": requests, "statuses": list(DELETION_STATUSES), "open": len(open_requests),
            "overdue": sum(1 for item in requests if item["overdue"]), "deadline_days": DELETION_DEADLINE_DAYS}


@router.put("/deletions/{request_id}")
async def change_deletion(
    change: DeletionChange, request: Request, response: Response,
    request_id: str = Path(pattern=r"^delreq_[0-9a-f]{16}$"),
    admin: str = Depends(require_admin), settings: AppSettings = Depends(get_app_settings), redis: Redis = Depends(get_redis),
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    known = {str(data.get("request_id")) for _, data in await _entries(redis, settings.account_deletion_request_stream, 2000)}
    if request_id not in known:
        raise HTTPException(404, "Solicitud no encontrada")
    await require_action(request, redis, f"deletion:{request_id}:{change.status}")
    now = datetime.now(timezone.utc).isoformat()
    pipe = redis.pipeline(transaction=True)
    pipe.hset(DELETION_KEY, request_id, json.dumps({"status": change.status, "by": admin, "at": now}))
    pipe.xadd(settings.developer_audit_stream, {"action": "deletion.status", "request_id": request_id, "status": change.status, "by": admin, "at": now},
              maxlen=settings.stream_maxlen, approximate=True)
    await pipe.execute()
    notify(settings, f"{admin} marcó {request_id} como {change.status}")
    return await deletions(response, admin, settings, redis)


# --- plantillas de simulacro -------------------------------------------------------------------------


class TemplateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    place: str = Field(min_length=1, max_length=60)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    magnitude: float = Field(ge=1.0, le=9.5)
    depth_km: float = Field(ge=0, le=700)
    origin_minutes_ago: int = Field(default=0, ge=0, le=120)
    country_code: str = Field(default="CO", pattern=r"^[A-Z]{2}$")
    critical: StrictBool = True


TEMPLATE_NAME = r"^[A-Za-z0-9ÁÉÍÓÚÜÑáéíóúüñ _.-]{1,30}$"


def _no_readonly(request: Request, settings: AppSettings) -> None:
    """Guardar una plantilla no pide MFA, pero una cuenta de solo lectura tampoco puede."""

    user = getattr(request.state, "admin_user", None) or {}
    if readonly(settings, str(user.get("email", ""))):
        raise HTTPException(403, "Tu cuenta es de solo lectura: puede ver el panel, no cambiarlo")


async def list_templates(redis: Redis) -> list[dict[str, Any]]:
    stored = cast(dict[str, str], await redis.hgetall(TEMPLATES_KEY))
    return [{"name": name, **json.loads(raw)} for name, raw in sorted(stored.items())]


@router.get("/drill-templates")
async def drill_templates(response: Response, admin: str = Depends(require_admin), redis: Redis = Depends(get_redis)) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    return {"templates": await list_templates(redis)}


@router.put("/drill-templates/{name}")
async def save_template(
    template: TemplateIn, request: Request, response: Response, name: str = Path(pattern=TEMPLATE_NAME),
    admin: str = Depends(require_admin), settings: AppSettings = Depends(get_app_settings), redis: Redis = Depends(get_redis),
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    _no_readonly(request, settings)
    if await redis.hlen(TEMPLATES_KEY) >= 30 and not await redis.hexists(TEMPLATES_KEY, name):
        raise HTTPException(409, "Hasta 30 plantillas")
    await redis.hset(TEMPLATES_KEY, name, json.dumps(template.model_dump(), ensure_ascii=False))
    await redis.xadd(settings.developer_audit_stream, {"action": "template.saved", "name": name, "by": admin, "at": datetime.now(timezone.utc).isoformat()},
                     maxlen=settings.stream_maxlen, approximate=True)
    return {"templates": await list_templates(redis)}


@router.delete("/drill-templates/{name}")
async def delete_template(
    request: Request, response: Response, name: str = Path(pattern=TEMPLATE_NAME),
    admin: str = Depends(require_admin), settings: AppSettings = Depends(get_app_settings), redis: Redis = Depends(get_redis),
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "no-store"
    _no_readonly(request, settings)
    await redis.hdel(TEMPLATES_KEY, name)
    await redis.xadd(settings.developer_audit_stream, {"action": "template.deleted", "name": name, "by": admin, "at": datetime.now(timezone.utc).isoformat()},
                     maxlen=settings.stream_maxlen, approximate=True)
    return {"templates": await list_templates(redis)}


# --- mapa agregado de reportes ciudadanos ---------------------------------------------------------------


@router.get("/reports-heat")
async def reports_heat(
    response: Response, event_id: str | None = Query(default=None, max_length=128),
    admin: str = Depends(require_admin), settings: AppSettings = Depends(get_app_settings), redis: Redis = Depends(get_redis),
) -> dict[str, Any]:
    """Reportes «¿Lo sentiste?» agrupados en celdas de 0,5° (~55 km), con la intensidad esperada al lado."""

    response.headers["Cache-Control"] = "no-store"
    events = await official_events(redis, settings)
    listing = sorted(events.values(), key=lambda item: str(item.get("origin_time") or ""), reverse=True)[:60]
    options = [{"event_id": item["event_id"], "label": f"M {float(item['magnitude']):.1f} · {item.get('place') or '—'} · {clock(parse_time(item.get('origin_time')))}"
                if isinstance(item.get("magnitude"), (int, float)) else str(item["event_id"])} for item in listing]
    chosen = events.get(event_id or "") if event_id else (listing[0] if listing else None)
    if chosen is None:
        return {"events": options, "event": None, "cells": [], "total": 0}
    cells: dict[tuple[float, float], list[float]] = {}
    total = 0
    for _, report in await _entries(redis, settings.felt_reports_stream, 2000):
        if str(report.get("earthquake_event_id") or "") != chosen["event_id"]:
            continue
        latitude, longitude = report.get("latitude"), report.get("longitude")
        if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
            continue
        total += 1
        key = (int(latitude // 0.5) * 0.5 + 0.25, int(longitude // 0.5) * 0.5 + 0.25)
        intensity = report.get("intensity_mmi")
        cells.setdefault(key, []).append(float(intensity) if isinstance(intensity, (int, float)) and report.get("felt", True) else 0.0)
    magnitude, depth = chosen.get("magnitude"), chosen.get("depth_km")
    rows = []
    for (latitude, longitude), values in sorted(cells.items(), key=lambda item: -len(item[1])):
        reported = [value for value in values if value > 0]
        expected = (
            intensity_at(float(magnitude), float(depth) if isinstance(depth, (int, float)) else None,
                         haversine_km(float(chosen["latitude"]), float(chosen["longitude"]), latitude, longitude))
            if isinstance(magnitude, (int, float)) and chosen.get("latitude") is not None else None
        )
        rows.append({"latitude": latitude, "longitude": longitude, "count": len(values), "felt": len(reported),
                     "avg_mmi": round(sum(reported) / len(reported), 1) if reported else None,
                     "expected_mmi": round(expected, 1) if expected is not None else None})
    return {"events": options, "total": total, "cells": rows, "event": {
        "event_id": chosen["event_id"], "latitude": chosen.get("latitude"), "longitude": chosen.get("longitude"),
        "magnitude": magnitude, "depth_km": depth, "place": chosen.get("place"),
    }}
