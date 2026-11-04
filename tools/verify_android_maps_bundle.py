"""Check the actual AAB's Maps metadata, without printing its API key.

Wire fields follow Android's tools/aapt2/Resources.proto (XmlNode/XmlElement/
XmlAttribute). No third-party packages, temporary plaintext manifests or keys.
"""
from __future__ import annotations

import hmac
import os
import sys
import zipfile
from collections.abc import Iterator
from pathlib import Path


def _varint(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    for shift in range(0, 70, 7):
        if offset >= len(data):
            raise ValueError("Truncated manifest")
        byte = data[offset]
        offset += 1
        value |= (byte & 127) << shift
        if not byte & 128:
            return value, offset
    raise ValueError("Invalid manifest integer")


def _fields(data: bytes) -> Iterator[tuple[int, bytes | int]]:
    offset = 0
    while offset < len(data):
        tag, offset = _varint(data, offset)
        field, wire = tag >> 3, tag & 7
        if wire == 0:
            value, offset = _varint(data, offset)
            yield field, value
        elif wire in (1, 2, 5):
            length = 8 if wire == 1 else 4
            if wire == 2:
                length, offset = _varint(data, offset)
            end = offset + length
            if end > len(data):
                raise ValueError("Truncated manifest field")
            yield field, data[offset:end]
            offset = end
        else:
            raise ValueError("Unsupported manifest wire type")


def _text(fields: list[tuple[int, bytes | int]], number: int) -> str:
    return next((value.decode("utf-8") for field, value in fields
                 if field == number and isinstance(value, bytes)), "")


def _attribute(data: bytes) -> tuple[str, str]:
    fields = list(_fields(data))
    name, value = _text(fields, 2), _text(fields, 3)
    if not value:
        for field, item in fields:
            if field == 6 and isinstance(item, bytes):
                for kind, string in _fields(item):
                    if kind in (2, 3) and isinstance(string, bytes):
                        value = _text(list(_fields(string)), 1)
    return name, value


def _elements(node: bytes, depth: int = 0) -> Iterator[tuple[str, dict[str, str]]]:
    if depth > 64:
        raise ValueError("Manifest nesting exceeds limit")
    for field, element in _fields(node):
        if field != 1 or not isinstance(element, bytes):
            continue
        fields = list(_fields(element))
        attributes = dict(_attribute(value) for number, value in fields
                          if number == 4 and isinstance(value, bytes))
        yield _text(fields, 3), attributes
        for number, child in fields:
            if number == 5 and isinstance(child, bytes):
                yield from _elements(child, depth + 1)


def verify_bundle(path: Path, expected: str) -> None:
    if not expected.strip():
        raise ValueError("Expected Maps key is missing")
    with zipfile.ZipFile(path) as bundle:
        info = bundle.getinfo("base/manifest/AndroidManifest.xml")
        if info.file_size > 5_000_000:
            raise ValueError("Unexpected manifest size")
        elements = list(_elements(bundle.read(info)))
    if not any(name == "manifest" and attrs.get("package") == "com.seismik.app"
               for name, attrs in elements):
        raise ValueError("Unexpected Android application package")
    values = [attrs.get("value", "").strip() for name, attrs in elements
              if name == "meta-data" and attrs.get("name") == "com.google.android.geo.API_KEY"]
    if len(values) != 1 or not hmac.compare_digest(values[0], expected.strip()):
        raise ValueError("AAB Maps key is missing or does not match the configured key")


if __name__ == "__main__":
    try:
        verify_bundle(Path(sys.argv[1]), os.getenv("SEISMIK_GOOGLE_MAPS_API_KEY", ""))
    except (ValueError, OSError, KeyError, zipfile.BadZipFile, IndexError):
        print("FAIL: AAB Maps configuration could not be verified. No key values are displayed.", file=sys.stderr)
        raise SystemExit(1) from None
    print("PASS: com.seismik.app AAB contains the expected Maps API key (value hidden).")
