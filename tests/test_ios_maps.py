"""El selector de mapas de iOS ofrece sólo lo que la app sabe dibujar."""
from __future__ import annotations

from pathlib import Path

NATIVE = Path("mobile_app/ios/Runner/Native")
SETTINGS = NATIVE / "Views/Settings/SettingsView.swift"
MONITOR = NATIVE / "Views/Monitor/MonitorView.swift"
DETAIL = NATIVE / "Views/Detail/EventDetailView.swift"
INFO_PLIST = Path("mobile_app/ios/Runner/Info.plist")


def test_the_picker_only_offers_apple_and_google() -> None:
    """OpenStreetMap se ofrecía sin que nada lo dibujara.

    El ajuste prometía «Apple Maps y OpenStreetMap funcionan dentro de la app»
    mientras el mapa era siempre MapKit.
    """

    settings = SETTINGS.read_text(encoding="utf-8")
    assert 'Text(MapProviderChoice.apple.label).tag(MapProviderChoice.apple.rawValue)' in settings
    assert 'Text(MapProviderChoice.google.label).tag(MapProviderChoice.google.rawValue)' in settings
    assert "OpenStreetMap" not in settings
    assert '.tag("osm")' not in settings


def test_no_screen_still_routes_to_openstreetmap() -> None:
    offenders = [
        path.name
        for path in NATIVE.rglob("*.swift")
        if "openstreetmap.org" in path.read_text(encoding="utf-8").lower()
    ]
    assert not offenders, offenders


def test_every_map_screen_can_draw_google() -> None:
    """Las tres pantallas con mapa comparten el mismo ajuste."""

    assert "GoogleMonitorMapView" in MONITOR.read_text(encoding="utf-8")
    assert "GoogleEpicenterMapView" in DETAIL.read_text(encoding="utf-8")
    assert "GoogleFamilyMapView" in SETTINGS.read_text(encoding="utf-8")


def test_the_build_still_carries_the_google_maps_key_and_scheme() -> None:
    """Sin la clave en Info.plist el SDK queda inactivo y el mapa sale gris."""

    plist = INFO_PLIST.read_text(encoding="utf-8")
    assert "<key>SeismikGoogleMapsAPIKey</key><string>$(SEISMIK_GOOGLE_MAPS_API_KEY)</string>" in plist
    assert "comgooglemaps" in plist
