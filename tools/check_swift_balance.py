#!/usr/bin/env python3
"""Comprueba que cada archivo Swift cierre todo lo que abre.

Xcode sólo existe en macOS y su error para este caso es engañoso: un `}` de más
deja el resto del archivo fuera de su tipo, y el compilador señala la primera
línea que ya no entiende, normalmente decenas de líneas más abajo del problema
real. Este chequeo corre en cualquier sistema y en menos de un segundo, así que
el desbalance se detecta antes de gastar minutos en un build de iOS.

No sustituye al compilador: sólo cubre esta clase de error, que es la que dos
agentes editando el mismo archivo introducen con más facilidad.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = PROJECT_ROOT / "mobile_app/ios"
# Código generado por Flutter y CocoaPods: no lo escribe nadie a mano.
SKIPPED_PARTS = {"ephemeral", "Pods", ".symlinks"}


def strip_literals(line: str) -> str:
    """Elimina cadenas y comentarios de línea para no contar sus símbolos."""

    kept: list[str] = []
    in_string = False
    escaped = False
    index = 0
    while index < len(line):
        char = line[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char == "/" and index + 1 < len(line) and line[index + 1] == "/":
            break
        else:
            kept.append(char)
        index += 1
    return "".join(kept)


def imbalance(path: Path) -> dict[str, int]:
    """Diferencia entre aperturas y cierres; vacío si el archivo está sano."""

    braces = 0
    parens = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        code = strip_literals(line)
        braces += code.count("{") - code.count("}")
        parens += code.count("(") - code.count(")")
    result = {}
    if braces:
        result["llaves"] = braces
    if parens:
        result["parentesis"] = parens
    return result


def swift_sources(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*.swift")
        if not SKIPPED_PARTS.intersection(path.parts)
    )


def check(root: Path = DEFAULT_ROOT) -> dict[Path, dict[str, int]]:
    return {
        path: problems
        for path in swift_sources(root)
        if (problems := imbalance(path))
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()

    sources = swift_sources(args.root)
    broken = check(args.root)
    for path, problems in broken.items():
        detail = ", ".join(f"{name} {value:+d}" for name, value in problems.items())
        print(f"DESBALANCE {path.relative_to(args.root)}: {detail}", file=sys.stderr)
    print(f"{len(sources)} archivos Swift revisados, {len(broken)} con desbalance")
    return 1 if broken else 0


if __name__ == "__main__":
    raise SystemExit(main())
