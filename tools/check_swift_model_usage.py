#!/usr/bin/env python3
"""Detecta accesos a miembros que los modelos Swift no declaran.

Un `event.providerDisplayName` que no existe sólo aparece cuando Xcode compila:
en macOS, tras varios minutos, y de uno en uno. Este chequeo compara los
miembros declarados en los modelos con los que usan las vistas y señala el
archivo y la línea exactos en menos de un segundo.

Es deliberadamente conservador: sólo mira variables cuyo tipo se conoce por
convención en este proyecto y sólo reporta miembros inexistentes, nunca errores
de tipo. No sustituye al compilador; adelanta su clase de error más repetida.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
NATIVE = PROJECT_ROOT / "mobile_app/ios/Runner/Native"

# Nombre de variable → tipo, por convención estable en estas vistas.
VARIABLE_TYPES = {
    "event": "SeismicEvent",
    "station": "SeismicStation",
}

MODEL_FILES = {
    "SeismicEvent": "Models/SeismicEvent.swift",
    "SeismicStation": "Models/SeismicStation.swift",
}

STORED_MEMBER = re.compile(
    r"^\s*(?:public\s+|private\s+|internal\s+)*(?:let|var)\s+(\w+)\s*:",
    re.MULTILINE,
)
COMPUTED_MEMBER = re.compile(
    r"^\s*(?:public\s+|private\s+|internal\s+|static\s+)*(?:var|func)\s+(\w+)",
    re.MULTILINE,
)


def declared_members(root: Path, type_name: str) -> set[str]:
    """Miembros del tipo, incluidos los de sus extensiones en el mismo archivo."""

    path = root / MODEL_FILES[type_name]
    if not path.is_file():
        return set()
    text = path.read_text(encoding="utf-8")
    start = text.find(f"struct {type_name}")
    if start == -1:
        return set()
    rest = text[start:]
    following = re.search(r"\n(?:public )?(?:struct|enum|final class) ", rest[1:])
    body = rest[: following.start() + 1] if following else rest
    return set(STORED_MEMBER.findall(body)) | set(COMPUTED_MEMBER.findall(body))


def scan(root: Path = NATIVE) -> list[str]:
    catalogue = {
        type_name: declared_members(root, type_name) for type_name in MODEL_FILES
    }
    findings: list[str] = []
    for path in sorted(root.rglob("*.swift")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split("//")[0]
            for variable, type_name in VARIABLE_TYPES.items():
                members = catalogue.get(type_name)
                if not members:
                    continue
                for match in re.finditer(rf"\b{variable}\.(\w+)", code):
                    member = match.group(1)
                    if member not in members:
                        findings.append(
                            f"{path.relative_to(root)}:{number} "
                            f"{type_name} no declara `{member}`"
                        )
    # Un mismo error repetido en varias líneas se reporta una vez por línea,
    # pero sin duplicar líneas idénticas.
    return sorted(set(findings))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=NATIVE)
    args = parser.parse_args()

    findings = scan(args.root)
    for finding in findings:
        print(f"MIEMBRO INEXISTENTE {finding}", file=sys.stderr)
    print(f"{len(findings)} accesos a miembros inexistentes")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
