"""El cliente nativo de iPhone habla con la misma API que el de Android.

Estas pruebas comparan lo que el Swift envía con lo que el backend acepta. No
sustituyen a probar en un iPhone, pero atrapan la clase de fallo más cara: un
campo mal escrito que sólo se manifiesta como un 422 en el dispositivo, cuando
ya se gastó una subida a TestFlight.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from api.schemas import DeviceRegistration, ShakePing
from reporting.schemas import DamageReport, FeltReport

CLIENT = Path("mobile_app/ios/Runner/Native/Services/SeismikAPIClient.swift")
REPORTS = Path("mobile_app/ios/Runner/Native/Models/CitizenReports.swift")
APP_DELEGATE = Path("mobile_app/ios/Runner/AppDelegate.swift")


def swift_dictionary_keys(source: str, variable: str) -> set[str]:
    """Claves de un literal `[String: Any]` asignado a `variable`."""

    declaration = re.search(
        rf"(?:let|var)\s+{re.escape(variable)}:\s*\[String:\s*Any\]\s*=\s*\[",
        source,
    )
    if declaration is None:
        raise AssertionError(f"No se encontró el diccionario Swift {variable}")
    start = declaration.start()
    body = source[start : source.index("\n        ]", start)]
    keys = set(re.findall(r'"([a-z_]+)":', body))
    # El registro agrega la ubicación condicionalmente después del literal.
    tail = source[source.index("\n        ]", start) : source.index("request.httpBody", start)]
    keys.update(re.findall(rf'{re.escape(variable)}\["([a-z_]+)"\]', tail))
    return keys


def swift_coding_keys(source: str, model: str) -> set[str]:
    """Nombres JSON declarados en el `CodingKeys` de un modelo Swift."""

    start = source.index(f"public struct {model}")
    body = source[start:]
    keys_start = body.index("enum CodingKeys")
    keys_body = body[keys_start : body.index("\n    }", keys_start)]
    names = set()
    for line in keys_body.splitlines():
        match = re.search(r"case\s+(\w+)(?:\s*=\s*\"([^\"]+)\")?", line)
        if match:
            names.add(match.group(2) or match.group(1))
    return names


@pytest.fixture(scope="module")
def client_source() -> str:
    return CLIENT.read_text(encoding="utf-8")


def test_registration_only_sends_fields_the_backend_accepts(client_source: str) -> None:
    """`DeviceRegistration` prohíbe campos extra: uno de más es un 422."""

    sent = swift_dictionary_keys(client_source, "registrationPayload")
    accepted = set(DeviceRegistration.model_fields)

    assert sent <= accepted, f"El backend no acepta: {sorted(sent - accepted)}"


def test_registration_sends_what_an_ios_device_requires(client_source: str) -> None:
    sent = swift_dictionary_keys(client_source, "registrationPayload")

    # El validador del backend exige estos tres para `platform: ios`.
    assert {"device_id", "platform", "apns_token"} <= sent
    assert "app_attest_token" in sent
    # Y rechaza los de Android en un registro de iPhone.
    assert "fcm_token" not in sent
    assert "play_integrity_token" not in sent


def test_the_shake_ping_matches_the_crowd_schema(client_source: str) -> None:
    sent = swift_dictionary_keys(client_source, "payload")
    accepted = set(ShakePing.model_fields)

    assert sent <= accepted, f"El backend no acepta: {sorted(sent - accepted)}"
    assert {"device_id", "lat", "lon", "pga", "timestamp"} <= sent


@pytest.mark.parametrize(
    ("model", "schema"),
    [("FeltReportPayload", FeltReport), ("DamageReportPayload", DamageReport)],
)
def test_citizen_reports_match_the_backend_schema(model: str, schema: type) -> None:
    sent = swift_coding_keys(REPORTS.read_text(encoding="utf-8"), model)
    accepted = set(schema.model_fields)

    assert sent <= accepted, f"{model} envía campos que el backend rechaza: {sorted(sent - accepted)}"


def test_no_json_value_is_a_swift_substring(client_source: str) -> None:
    """`JSONSerialization` lanza una excepción de Objective-C ante un Substring.

    No es capturable desde Swift: la app se cierra en el primer registro. Un
    `prefix(...)` sin envolver en `String(...)` produce exactamente eso.
    """

    offenders = [
        line.strip()
        for line in client_source.splitlines()
        if re.search(r'"\w+":\s*[^,]*\.prefix\(', line) and "String(" not in line
    ]

    assert not offenders, "Valores JSON de tipo Substring: " + "; ".join(offenders)


def test_the_app_asks_for_notification_permission() -> None:
    """Sin autorización, iOS descarta el contenido de la alerta.

    El token de APNs llega igual, así que el registro parece correcto y el fallo
    sólo se nota cuando un sismo real no avisa a nadie.
    """

    delegate = APP_DELEGATE.read_text(encoding="utf-8")

    assert "requestAuthorization" in delegate
    assert "registerForRemoteNotifications" in delegate


def test_ios_registration_uses_real_firebase_app_check() -> None:
    client = CLIENT.read_text(encoding="utf-8")
    delegate = APP_DELEGATE.read_text(encoding="utf-8")

    assert "AppCheck.appCheck().token" in client
    assert "DeviceCheckProvider" in delegate
    assert "sideload-unverified" not in client


def test_ios_privacy_manifest_is_bundled() -> None:
    manifest = Path("mobile_app/ios/Runner/PrivacyInfo.xcprivacy")
    project = Path("mobile_app/ios/Runner.xcodeproj/project.pbxproj").read_text(
        encoding="utf-8"
    )

    assert manifest.exists()
    assert "NSPrivacyTracking" in manifest.read_text(encoding="utf-8")
    assert "PrivacyInfo.xcprivacy in Resources" in project


def test_recovered_alerts_keep_their_timestamp() -> None:
    """`/v1/alerts/recent` fecha cada aviso con `emitted_at`, no `detected_at`."""

    model = Path("mobile_app/ios/Runner/Native/Models/SeismicEvent.swift").read_text(
        encoding="utf-8"
    )

    assert 'case emittedAt = "emitted_at"' in model
    assert ".emittedAt" in model


def swift_enum_raw_values(source: str, name: str) -> set[str]:
    """Valores JSON de un `enum ... : String` de Swift.

    Un `case electrical` sin `= "..."` usa su propio nombre como valor.
    """

    start = source.index(f"public enum {name}: String")
    body = source[start : source.index("\n    public var id", start)]
    values = set()
    for line in body.splitlines():
        match = re.search(r"case\s+(\w+)(?:\s*=\s*\"([^\"]+)\")?", line)
        if match:
            values.add(match.group(2) or match.group(1))
    return values


def test_the_hazard_catalogue_matches_the_backend_enum() -> None:
    """Un identificador inventado se traduce en un 422 con el reporte escrito."""

    from reporting.schemas import ObservedHazard

    swift = swift_enum_raw_values(REPORTS.read_text(encoding="utf-8"), "ObservedHazard")
    backend = {item.value for item in ObservedHazard}

    assert swift == backend, (
        f"Sólo en iOS: {sorted(swift - backend)}; sólo en el backend: {sorted(backend - swift)}"
    )


def test_the_severity_scale_matches_the_backend_enum() -> None:
    from reporting.schemas import DamageSeverity

    swift = swift_enum_raw_values(REPORTS.read_text(encoding="utf-8"), "DamageSeverity")
    backend = {item.value for item in DamageSeverity}

    assert swift == backend


def test_iphone_offers_the_same_hazards_as_android() -> None:
    """Un catálogo más corto haría incomparables los reportes de un mismo sismo."""

    android = Path("mobile_app/lib/presentation/screens/damage_report_screen.dart").read_text(
        encoding="utf-8"
    )
    # Sólo el mapa de peligros: el archivo declara otras tablas de etiquetas.
    start = android.index("_hazardLabels")
    catalogue = android[start : android.index("};", start)]
    android_hazards = set(re.findall(r"'([a-z_]+)':\s*'", catalogue))
    swift = swift_enum_raw_values(REPORTS.read_text(encoding="utf-8"), "ObservedHazard")

    assert android_hazards == swift, (
        f"Sólo en Android: {sorted(android_hazards - swift)}; "
        f"sólo en iPhone: {sorted(swift - android_hazards)}"
    )
