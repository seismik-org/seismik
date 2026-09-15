"""Las URL de los .xcconfig de iOS deben sobrevivir al analizador de Xcode."""
from __future__ import annotations

import re
from pathlib import Path

IOS_FLUTTER = Path("mobile_app/ios/Flutter")


def test_urls_in_xcconfig_files_escape_the_comment_marker() -> None:
    """En un .xcconfig `//` inicia un comentario.

    `SEISMIK_API_BASE_URL = https://api.seismik.org` llegaba a la app como
    `https:`: desde el 11 de septiembre ninguna petición salía del iPhone.
    La forma segura es `https:/$()/dominio`.
    """

    offenders = []
    for path in sorted(IOS_FLUTTER.glob("*.xcconfig*")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            setting = line.split("=", 1)
            if line.lstrip().startswith("//") or len(setting) != 2:
                continue
            if re.search(r"[a-z]+://", setting[1]):
                offenders.append(f"{path.name}:{number}: {line.strip()}")
    assert not offenders, offenders


def test_the_example_points_the_app_at_the_production_api() -> None:
    example = (IOS_FLUTTER / "Seismik.xcconfig.example").read_text(encoding="utf-8")
    assert "SEISMIK_API_BASE_URL = https:/$()/api.seismik.org" in example
