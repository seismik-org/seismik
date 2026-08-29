from pathlib import Path


def test_api_image_contains_official_source_catalog() -> None:
    dockerfile = Path("Dockerfile.api").read_text(encoding="utf-8")

    assert "COPY official_sources.json ./official_sources.json" in dockerfile
