"""Ningún secreto ni clave de API debe entrar en el repositorio.

Este proyecto es público. Una clave escrita en el código queda en el historial
de Git para siempre: quitarla después no la borra, sólo la esconde del árbol de
trabajo. Por eso conviene detectarla antes del commit y no después.

Sólo se revisan los archivos que Git sigue. Lo que está ignorado —el
`google-services.json` de Android, el `GoogleService-Info.plist` de iOS, los
`.env`— nunca llega al repositorio y no hace falta vigilarlo aquí.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

# Patrones con muy pocos falsos positivos: cada uno tiene un prefijo propio.
PATTERNS = {
    "clave de API de Google": re.compile(r"AIza[0-9A-Za-z_\-]{35}"),
    "clave privada": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "token de AWS": re.compile(r"AKIA[0-9A-Z]{16}"),
    "token de Slack": re.compile(r"xox[baprs]-[0-9A-Za-z-]{10,}"),
    "clave de Stripe": re.compile(r"sk_live_[0-9A-Za-z]{24,}"),
}

# Extensiones que pueden contener código o configuración legible.
SCANNED_SUFFIXES = {
    ".py", ".swift", ".dart", ".kt", ".kts", ".js", ".ts", ".html", ".css",
    ".json", ".yml", ".yaml", ".plist", ".xml", ".sh", ".ps1", ".md", ".xcconfig",
    ".entitlements", ".pbxproj", ".toml", ".cfg", ".txt",
}

# Este archivo describe los patrones, así que necesariamente los contiene.
SELF = Path(__file__).name


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        pytest.skip("El árbol no es un repositorio de Git")
    return [
        Path(name)
        for name in result.stdout.split("\0")
        if name and Path(name).suffix.lower() in SCANNED_SUFFIXES
    ]


def test_no_tracked_file_contains_a_secret() -> None:
    findings: list[str] = []
    for path in tracked_files():
        if path.name == SELF or not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for label, pattern in PATTERNS.items():
            match = pattern.search(content)
            if match:
                line = content[: match.start()].count("\n") + 1
                # No se reproduce el valor: quedaría en la salida de CI.
                findings.append(f"{path}:{line} parece {label}")

    assert not findings, (
        "Posibles secretos en archivos versionados:\n"
        + "\n".join(findings)
        + "\n\nSi es un falso positivo, ajusta el patrón. Si no lo es, rota la "
        "credencial: quitarla del árbol no la borra del historial."
    )


def test_the_ios_maps_key_comes_from_configuration_not_from_source() -> None:
    """La clave llega por `SEISMIK_GOOGLE_MAPS_API_KEY`, no escrita en el código."""

    delegate = Path("mobile_app/ios/Runner/AppDelegate.swift").read_text(encoding="utf-8")

    assert "SeismikGoogleMapsAPIKey" in delegate, "Debe leerse del Info.plist"
    assert not PATTERNS["clave de API de Google"].search(delegate), (
        "Hay una clave de Google escrita en AppDelegate.swift"
    )


def test_secrets_that_ship_with_the_app_stay_untracked() -> None:
    """Firebase los diseña para viajar en el binario, pero no en el repositorio."""

    gitignore = Path(".gitignore").read_text(encoding="utf-8")

    for path in (
        "mobile_app/ios/Runner/GoogleService-Info.plist",
        "mobile_app/ios/Flutter/Seismik.xcconfig",
    ):
        assert path in gitignore, f"{path} debe seguir ignorado"
