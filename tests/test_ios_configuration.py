"""Validación estática del proyecto iOS ejecutable fuera de macOS.

Xcode sólo existe en macOS, así que la compilación real vive en el job `ios` de
CI. Estas pruebas cubren lo que sí puede verificarse en cualquier máquina: que
los plists estén bien formados y que no se pierdan las claves de las que dependen
las alertas críticas y la apertura de epicentros.
"""
from __future__ import annotations

import plistlib
import sys
from pathlib import Path

import pytest
import yaml

IOS = Path("mobile_app/ios")
INFO_PLIST = IOS / "Runner/Info.plist"
ENTITLEMENTS = IOS / "Runner/Runner.entitlements"


@pytest.fixture(scope="module")
def info_plist() -> dict:
    return plistlib.loads(INFO_PLIST.read_bytes())


@pytest.fixture(scope="module")
def entitlements() -> dict:
    return plistlib.loads(ENTITLEMENTS.read_bytes())


def test_info_plist_is_well_formed_and_keeps_permission_strings(info_plist: dict) -> None:
    """Un plist mal formado rompe la compilación sólo al llegar a macOS."""

    assert info_plist["CFBundleDisplayName"] == "Seismik"
    # iOS rechaza en revisión una app que pide ubicación o sensores sin explicar
    # para qué los usa.
    assert info_plist["NSLocationWhenInUseUsageDescription"].strip()
    assert info_plist["NSMotionUsageDescription"].strip()


def test_push_and_background_modes_survive(info_plist: dict) -> None:
    assert "remote-notification" in info_plist["UIBackgroundModes"]


def test_map_schemes_are_declared(info_plist: dict) -> None:
    schemes = info_plist["LSApplicationQueriesSchemes"]
    assert "comgooglemaps" in schemes
    assert "maps" in schemes


def test_critical_alerts_entitlement_is_declared(entitlements: dict) -> None:
    """El entitlement va en Runner.entitlements, no en Info.plist."""

    assert entitlements["com.apple.developer.usernotifications.critical-alerts"] is True


def test_alarm_sound_ships_with_the_ios_bundle() -> None:
    assert (IOS / "Runner/alarm.aiff").is_file()


def test_local_configuration_is_optional_and_untracked() -> None:
    for name in ("Debug", "Release"):
        contents = (IOS / f"Flutter/{name}.xcconfig").read_text(encoding="utf-8")
        # `#include?` no falla si el archivo local no existe; `#include` sí.
        assert '#include? "Seismik.xcconfig"' in contents
    assert (IOS / "Flutter/Seismik.xcconfig.example").is_file()
    assert not (IOS / "Flutter/Seismik.xcconfig").is_file(), (
        "La configuración local no debe versionarse"
    )


def test_xcode_project_wires_the_entitlements_file() -> None:
    project = (IOS / "Runner.xcodeproj/project.pbxproj").read_text(encoding="utf-8")
    assert 'CODE_SIGN_ENTITLEMENTS = "Runner/$(SEISMIK_ENTITLEMENTS_FILE)";' in project
    assert (IOS / "Runner/Runner.basic.entitlements").is_file()
    assert "PRODUCT_BUNDLE_IDENTIFIER = com.seismik.app;" in project


def test_podfile_platform_matches_the_project_deployment_target() -> None:
    podfile = (IOS / "Podfile").read_text(encoding="utf-8")
    assert "platform :ios, '15.0'" in podfile
    assert "IPHONEOS_DEPLOYMENT_TARGET'] = '15.0'" in podfile


def test_ci_builds_ios_on_macos_since_it_cannot_run_elsewhere() -> None:
    workflow = yaml.safe_load(Path(".github/workflows/ci.yml").read_text(encoding="utf-8"))
    ios_job = workflow["jobs"]["ios"]
    assert ios_job["runs-on"].startswith("macos")
    steps = " ".join(str(step.get("run", "")) for step in ios_job["steps"])
    assert "pod install" in steps
    # Sin certificados en CI la firma es imposible; la compilación no.
    assert "--no-codesign" in steps


def test_ci_verifies_the_android_release_is_universal() -> None:
    workflow = yaml.safe_load(Path(".github/workflows/ci.yml").read_text(encoding="utf-8"))
    steps = " ".join(str(step.get("run", "")) for step in workflow["jobs"]["android"]["steps"])
    for abi in ("arm64-v8a", "armeabi-v7a", "x86_64"):
        assert abi in steps
    assert "seismikUnsignedReleaseCheck=true" in steps


def _ios_job_steps() -> list[dict]:
    workflow = yaml.safe_load(Path(".github/workflows/ci.yml").read_text(encoding="utf-8"))
    return list(workflow["jobs"]["ios"]["steps"])


def test_xcode_copies_the_firebase_configuration_into_the_bundle() -> None:
    """Sin este recurso la app arranca sin Firebase y no obtiene token APNs."""

    project = (IOS / "Runner.xcodeproj/project.pbxproj").read_text(encoding="utf-8")

    assert "GoogleService-Info.plist in Resources" in project


def test_the_real_firebase_configuration_is_never_committed() -> None:
    assert not (IOS / "Runner/GoogleService-Info.plist").is_file()
    assert "mobile_app/ios/Runner/GoogleService-Info.plist" in Path(".gitignore").read_text(
        encoding="utf-8"
    )


def test_ci_supplies_a_placeholder_firebase_plist_before_building() -> None:
    """El proyecto exige el archivo como recurso: sin él, Xcode falla antes de
    compilar una sola línea de Dart. El valor real llega desde un secreto sólo
    en el workflow de TestFlight."""

    steps = _ios_job_steps()
    names = [str(step.get("name", "")) for step in steps]
    placeholder = next(
        (index for index, name in enumerate(names) if "placeholder Firebase" in name),
        None,
    )
    build = next(
        (index for index, name in enumerate(names) if "without code signing" in name),
        None,
    )
    assert placeholder is not None, "El job iOS debe crear el plist de Firebase"
    assert build is not None
    assert placeholder < build, "El plist debe existir antes de compilar"

    script = str(steps[placeholder]["run"])
    assert "GoogleService-Info.plist" in script
    assert "plutil -lint" in script
    # El marcador debe ser evidentemente falso para que nadie lo confunda con
    # una configuración real de Firebase.
    assert "placeholder" in script


def test_testflight_workflow_uses_the_real_firebase_secret() -> None:
    workflow = Path(".github/workflows/ios-testflight.yml").read_text(encoding="utf-8")

    assert "IOS_GOOGLE_SERVICE_INFO_BASE64" in workflow
    assert "ios/Runner/GoogleService-Info.plist" in workflow
    assert "plutil -lint ios/Runner/GoogleService-Info.plist" in workflow


def test_ci_runs_the_native_swift_tests() -> None:
    """La app de iPhone es Swift nativo: `flutter test` no la ejercita."""

    names = [str(step.get("name", "")) for step in _ios_job_steps()]
    assert any("native Swift unit tests" in name for name in names), (
        "CI debe ejecutar las pruebas del código Swift, no sólo compilarlo"
    )


def test_the_native_test_target_has_real_tests() -> None:
    tests = IOS / "RunnerTests/SeismikNativeTests.swift"
    assert tests.is_file()
    contents = tests.read_text(encoding="utf-8")
    assert "OfflineReportQueueTests" in contents
    assert "SeismikDSPTests" in contents

    project = (IOS / "Runner.xcodeproj/project.pbxproj").read_text(encoding="utf-8")
    assert "SeismikNativeTests.swift in Sources" in project


def test_the_native_client_never_invents_seismic_data() -> None:
    """Mostrar sismos de ejemplo con el sello de una agencia oficial es peor
    que no mostrar nada."""

    client = (IOS / "Runner/Native/Services/SeismikAPIClient.swift").read_text(
        encoding="utf-8"
    )

    assert "sampleEvents" not in client
    assert "defaultStations" not in client


def test_the_native_app_reaches_parity_with_android() -> None:
    native = IOS / "Runner/Native"
    client = (native / "Services/SeismikAPIClient.swift").read_text(encoding="utf-8")

    assert (native / "Services/OfflineReportQueue.swift").is_file(), (
        "Sin cola offline, un reporte sin red se pierde"
    )
    assert (native / "Services/MotionDetector.swift").is_file()
    assert "v1/alerts/recent" in client, "Falta recuperar las alertas perdidas"
    assert "v1/crowd/shake" in client, "Falta la detección colaborativa"


def test_every_swift_file_closes_what_it_opens() -> None:
    """Un `}` de más deja el resto del archivo fuera de su tipo.

    Xcode señala la primera línea que ya no entiende, normalmente muy lejos del
    error real, y sólo lo hace tras minutos de build en macOS. Este chequeo lo
    detecta en cualquier sistema antes de llegar a CI.
    """

    sys.path.insert(0, str(Path("tools").resolve()))
    from check_swift_balance import check

    broken = check()

    assert not broken, "Archivos Swift desbalanceados: " + ", ".join(
        f"{path.name} ({problems})" for path, problems in broken.items()
    )


def test_views_only_use_members_the_models_declare() -> None:
    """Un miembro inexistente sólo lo revela Xcode, en macOS y de uno en uno."""

    sys.path.insert(0, str(Path("tools").resolve()))
    from check_swift_model_usage import scan

    findings = scan()

    assert not findings, "Accesos a miembros inexistentes:\n" + "\n".join(findings)


def test_the_test_target_can_resolve_the_pods_the_app_imports() -> None:
    """`@testable import Runner` arrastra los módulos que importa la app.

    GoogleMaps llega por CocoaPods, no por Swift Package Manager. Sin declarar
    el target de pruebas en el Podfile, Xcode falla con «Unable to resolve
    module dependency: 'GoogleMaps'» al compilar RunnerTests.
    """

    podfile = (IOS / "Podfile").read_text(encoding="utf-8")

    assert "target 'RunnerTests' do" in podfile
    assert "inherit! :search_paths" in podfile
    # Debe estar anidado dentro del target Runner para heredar sus pods.
    runner_block = podfile[podfile.index("target 'Runner' do") :]
    assert runner_block.index("target 'RunnerTests' do") < runner_block.index("\nend")
