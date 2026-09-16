"""El mapa de iOS es Apple Maps, y el ajuste sólo decide con qué app se abre."""
from __future__ import annotations

from pathlib import Path

NATIVE = Path("mobile_app/ios/Runner/Native")
SETTINGS = NATIVE / "Views/Settings/SettingsView.swift"
MONITOR = NATIVE / "Views/Monitor/MonitorView.swift"
DETAIL = NATIVE / "Views/Detail/EventDetailView.swift"


def test_the_app_never_draws_a_google_map() -> None:
    """El SDK de Google se probó en el build 51 y se quitó.

    No llegaba a cargar mosaicos, y como el proveedor se guarda en el teléfono,
    la app volvía a intentarlo en cada arranque y se quedaba trabada. El mapa
    de dentro es Apple Maps en las tres pantallas: monitor, detalle y familia.
    """

    offenders = [
        f"{path.name}:{number}"
        for path in NATIVE.rglob("*.swift")
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if "GMSMapView" in line
    ]
    assert not offenders, offenders


def test_the_picker_only_chooses_where_epicenters_open() -> None:
    settings = SETTINGS.read_text(encoding="utf-8")
    assert "Abrir epicentros con" in settings
    assert "El mapa de la app es siempre Apple Maps" in settings
    assert 'Text(MapProviderChoice.apple.label).tag(MapProviderChoice.apple.rawValue)' in settings
    assert 'Text(MapProviderChoice.google.label).tag(MapProviderChoice.google.rawValue)' in settings


def test_no_screen_still_routes_to_openstreetmap() -> None:
    offenders = [
        path.name
        for path in NATIVE.rglob("*.swift")
        if "openstreetmap.org" in path.read_text(encoding="utf-8").lower()
    ]
    assert not offenders, offenders


def test_opening_an_epicenter_outside_still_offers_google() -> None:
    """Abrir el epicentro en la app de Google no necesita el SDK y sí funciona."""

    detail = DETAIL.read_text(encoding="utf-8")
    assert "comgooglemaps://" in detail
    assert "Abrir epicentro en Google Maps" in detail


def test_the_monitor_map_is_apple_only() -> None:
    monitor = MONITOR.read_text(encoding="utf-8")
    assert "NativeMapView(" in monitor
    assert "MapProviderChoice" not in monitor
