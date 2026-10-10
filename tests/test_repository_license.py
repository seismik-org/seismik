"""Keep license metadata honest without overriding earlier or third-party grants."""
import tomllib
from pathlib import Path


def test_restricted_license_preserves_existing_rights() -> None:
    license_text = Path("LICENSE").read_text(encoding="utf-8")
    assert "Seismik Source-Visible License 1.0" in license_text
    assert "not an open-source license" in license_text
    assert "does not relicense third-party" in license_text
    assert "revoke rights already granted" in license_text
    assert "independently developed implementations" in license_text
    assert "Apache License" in Path("docs/licenses/Apache-2.0.txt").read_text(encoding="utf-8")
    metadata = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    assert metadata["project"]["license"] == {"file": "LICENSE"}
    readme = Path("README.md").read_text(encoding="utf-8")
    assert "Licencia Apache-2.0" not in readme
    assert "10 de octubre de 2026" in readme
    assert "failed_validation" in readme
