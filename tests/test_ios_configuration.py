"""Validación estática del proyecto iOS ejecutable fuera de macOS.

Xcode sólo existe en macOS, así que la compilación real vive en el job `ios` de
CI. Estas pruebas cubren lo que sí puede verificarse en cualquier máquina: que
los plists estén bien formados y que no se pierdan las claves de las que dependen
las alertas críticas y la apertura de epicentros.
"""
from __future__ import annotations

import plistlib
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
