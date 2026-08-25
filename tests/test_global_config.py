import json
from pathlib import Path

from eew.config import Settings

PROJECT = Path(__file__).resolve().parents[1]


def test_generated_global_config_is_valid(monkeypatch) -> None:
    monkeypatch.delenv("SEISMIK_SHARD_COUNT", raising=False)
    monkeypatch.delenv("SEISMIK_SHARD_INDEX", raising=False)
    settings = Settings.load(PROJECT / "config.global.json")
    assert len(settings.seedlink.providers) == 3
    assert sum(len(provider.stations) for provider in settings.seedlink.providers) > 1000


def test_global_zones_partition_without_loss(monkeypatch) -> None:
    counts = []
    monkeypatch.setenv("SEISMIK_SHARD_COUNT", "5")
    for index in range(5):
        monkeypatch.setenv("SEISMIK_SHARD_INDEX", str(index))
        settings = Settings.load(PROJECT / "config.global.json")
        counts.append(sum(len(provider.stations) for provider in settings.seedlink.providers))
    coverage = json.loads((PROJECT / "data" / "global_coverage.json").read_text(encoding="utf-8"))
    assert sum(counts) == coverage["selected_stations"]
    assert all(count > 0 for count in counts)


def test_country_filter_keeps_only_complete_zones(monkeypatch) -> None:
    monkeypatch.setenv("SEISMIK_SHARD_COUNT", "1")
    monkeypatch.setenv("SEISMIK_SHARD_INDEX", "0")
    monkeypatch.setenv("SEISMIK_ACTIVE_COUNTRIES", "CO")
    settings = Settings.load(PROJECT / "config.global.json")
    stations = [station for provider in settings.seedlink.providers for station in provider.stations]
    assert stations
    assert {station.country_code for station in stations} == {"CO"}
    zones = {station.zone_id for station in stations}
    assert all(sum(item.zone_id == zone for item in stations) >= 3 for zone in zones)
