import importlib.util
from datetime import date
from urllib.parse import urlparse

import numpy as np
from obspy import Stream, Trace, UTCDateTime
from test_waves import COOKIES, PAYLOAD, WAVES, approved, client, downloads, waves


def test_resources_are_private_even_when_history_is_public(monkeypatch):
    assert client.get("/v1/waves/resources").status_code == 401
    approved(monkeypatch)
    result = client.get("/v1/waves/resources", cookies=COOKIES).json()
    assert len(result["items"]) == 5
    assert {r["format"] for r in result["items"]} == {"JSON", "StationXML"}
    assert all(r["live"] is False and r["validation_status"] == "research_not_validated" for r in result["items"])
    assert all(len(r["sha256"]) == 64 and r["description"] for r in result["items"])


def test_resource_download_shares_integrity_gate_and_auth(monkeypatch):
    downloads(monkeypatch)
    import hashlib

    record = {"id": "b" * 24, "name": "supplements/2026-10-18/selection-response.xml",
              "format": "StationXML", "sha256": hashlib.sha256(PAYLOAD).hexdigest(), "bytes": len(PAYLOAD)}
    monkeypatch.setattr(waves, "resources", lambda: {"items": [record]})
    url = f"/v1/waves/resources/{record['id']}/download"
    assert client.get(url).status_code == 401
    response = client.get(url, cookies=COOKIES)
    assert response.content == PAYLOAD and response.headers["content-type"].startswith("application/xml")
    monkeypatch.setattr(waves, "archive_bytes", lambda _: b"tampered")
    assert client.get(url, cookies=COOKIES).status_code == 502
    assert client.get("/v1/waves/resources/unknown/download", cookies=COOKIES).status_code == 404
    monkeypatch.delenv("WAVES_DOWNLOADS")
    assert client.get(url, cookies=COOKIES).status_code == 404


def test_audit_is_a_case_not_a_confirmed_earthquake(monkeypatch):
    approved(monkeypatch)
    data = client.get("/v1/waves/catalog?group=audit", cookies=COOKIES).json()
    assert data["total"] == 1
    record = data["items"][0]
    assert record["view"]["kind"] == "caso" and record["view"]["magnitude"] is None
    assert record["view"]["traces"] == 30 and record["view"]["stations"] == 6
    preview = client.get(f"/v1/waves/records/{record['id']}/preview", cookies=COOKIES).json()
    assert len(preview["traces"]) == 30
    assert "huecos sin rellenar" in preview["reduction"]
    assert all(t["duration_s"] < 1200 for t in preview["traces"])
    assert {t["channel"] for t in preview["traces"]} == {"HHZ"}


def test_preview_preserves_separated_segments_without_filling(tmp_path):
    spec = importlib.util.spec_from_file_location("wave_previews_test", WAVES / "build-previews.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    traces = []
    for offset in (0, 86400):
        traces.append(Trace(np.arange(1200, dtype=np.int32), header={
            "network": "XX", "station": "TEST", "channel": "HHZ", "sampling_rate": 100,
            "starttime": UTCDateTime("2026-10-01") + offset}))
    path = tmp_path / "split.mseed"
    Stream(traces).write(str(path), format="MSEED")
    result = module.traces_of(path)
    assert len(result) == 2 and sum(t["samples"] for t in result) == 2400
    assert all(t["duration_s"] < 12 and t["gaps_in_file"] == 1 for t in result)
    assert [t["segment_index"] for t in result] == [0, 1]


def test_history_has_primary_sources_and_no_claimed_waveforms():
    response = client.get("/v1/waves/history")
    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "educational_reference" and len(data["items"]) == 10
    assert len([r for r in data["items"] if r["region"] == "colombia"]) == 4
    assert "Magnitud no equivale" in data["notice"]
    for item in data["items"]:
        date.fromisoformat(item["date"])
        host = urlparse(item["source_url"]).hostname
        assert host.endswith(".sgc.gov.co") or host.endswith(".usgs.gov")
        assert item["waveform_status"] == "not_linked" and item["waveform_record_ids"] == []
        assert item["date_basis"] and 0 < item["magnitude"] < 10
    armenia = next(r for r in data["items"] if r["id"] == "eje-cafetero-1999")
    assert armenia["magnitude"] == 6.1 and "ISC" in armenia["source"]


def test_public_history_assets_have_no_private_archive_names():
    source = (WAVES / "static/history.js").read_text("utf-8")
    assert "innerHTML" not in source
    data = (WAVES / "static/historical-earthquakes.json").read_text("utf-8")
    assert "gs://" not in data and ".mseed" not in data and "seismik_session" not in data


def test_audit_filter_clears_incompatible_magnitude_and_event_filters():
    source = (WAVES / "static/waves.js").read_text("utf-8")
    assert '$("group").value === "audit"' in source
    assert '$("kind").value = "caso"' in source and '$("minimum").value = "0"' in source
