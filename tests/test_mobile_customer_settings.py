from pathlib import Path


def test_customer_labels_keep_safety_and_legal_information() -> None:
    android = Path("mobile_app/lib/presentation/screens/settings_screen.dart").read_text(encoding="utf-8")
    ios = Path("mobile_app/ios/Runner/Native/Views/Settings/SettingsView.swift").read_text(encoding="utf-8")
    for source in (android, ios):
        assert "Diagnóstico de la beta" not in source
        assert "Beta experimental" not in source
        assert "Estado del dispositivo" in source
        assert "no sustituye a las autoridades" in source
    for source in (ios, Path("mobile_app/lib/services/app_links.dart").read_text(encoding="utf-8")):
        for route in ("terms-of-service", "terms-of-privacy", "delete-account/"):
            assert route in source
        assert "github.com/seismik-org/seismik" in source
    assert "Fuentes y aviso legal" in ios
    assert "https://sismo.sgc.gov.co/" in ios
    assert "https://www.usgs.gov/programs/earthquake-hazards" in ios
    assert "no representa ni está afiliada" in ios


def test_android_exposes_all_existing_oauth_providers_and_deletion() -> None:
    family = Path("mobile_app/lib/presentation/screens/family_safety_screen.dart").read_text(encoding="utf-8")
    for provider in ("apple", "github", "email"):
        assert f"family.signIn(provider: '{provider}')" in family
    assert "value: 'delete'" in family
    assert "AppLinks.deleteAccount" in family


def test_dynamic_colors_read_system_roles_not_app_theme_attributes() -> None:
    native = Path("mobile_app/android/app/src/main/kotlin/com/seismik/app/SystemDynamicColors.kt").read_text(encoding="utf-8")
    assert "Build.VERSION.SDK_INT < 34" in native
    assert 'getIdentifier(name, "color", "android")' in native
    assert "surface_container_highest" in native
    main = Path("mobile_app/lib/main.dart").read_text(encoding="utf-8")
    assert "child: SystemDynamicColorBuilder(" in main
