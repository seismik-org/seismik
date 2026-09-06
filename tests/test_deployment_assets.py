from pathlib import Path


def test_api_image_contains_official_source_catalog() -> None:
    dockerfile = Path("Dockerfile.api").read_text(encoding="utf-8")

    assert "COPY official_sources.json ./official_sources.json" in dockerfile


def test_android_declares_visibility_for_maps_and_official_sources() -> None:
    """Android 11+ oculta las apps instaladas salvo las declaradas en <queries>."""

    manifest = Path("mobile_app/android/app/src/main/AndroidManifest.xml").read_text(
        encoding="utf-8"
    )

    assert "<queries>" in manifest
    assert 'android:scheme="geo"' in manifest
    assert 'android:scheme="https"' in manifest


def test_ios_declares_the_map_schemes_it_needs_to_query() -> None:
    """Sin LSApplicationQueriesSchemes, iOS cae siempre al respaldo web."""

    info_plist = Path("mobile_app/ios/Runner/Info.plist").read_text(encoding="utf-8")

    assert "LSApplicationQueriesSchemes" in info_plist
    assert "<string>comgooglemaps</string>" in info_plist
    assert "<string>maps</string>" in info_plist


def test_ios_build_settings_allow_a_local_untracked_configuration() -> None:
    for name in ("Debug", "Release"):
        contents = Path(f"mobile_app/ios/Flutter/{name}.xcconfig").read_text(
            encoding="utf-8"
        )
        assert '#include? "Seismik.xcconfig"' in contents
    assert Path("mobile_app/ios/Flutter/Seismik.xcconfig.example").is_file()
    assert "mobile_app/ios/Flutter/Seismik.xcconfig" in Path(".gitignore").read_text(
        encoding="utf-8"
    )


def test_detector_keeps_a_durable_spool_for_the_events_api() -> None:
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")

    assert "SEISMIK_ALERT_SPOOL_DIR" in compose
    assert "detector-spool:/var/lib/seismik/spool" in compose


def test_release_signing_still_requires_the_production_keystore() -> None:
    """La verificación de compilación no debe poder firmar una distribución."""

    gradle = Path("mobile_app/android/app/build.gradle.kts").read_text(encoding="utf-8")

    assert 'System.getenv("SEISMIK_KEYSTORE")' in gradle
    assert 'signingConfigs.getByName("release")' in gradle
    assert 'System.getenv("SEISMIK_KEYSTORE").isNullOrEmpty()' in gradle
