from __future__ import annotations

import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import audit_central_station_access as audit_tool  # noqa: E402
from audit_central_station_access import lag_summary, select_advertised, selector  # noqa: E402


def test_missing_packets_do_not_become_zero_latency() -> None:
    result = lag_summary([])
    assert result["mean_seconds"] is None
    assert not result["transport_short_probe_pass"]


def test_arithmetic_mean_is_not_median() -> None:
    result = lag_summary([1., 1., 1., 1., 11.])
    assert result["mean_seconds"] == 3
    assert result["p50_seconds"] == 1
    assert result["p95_seconds"] == 11


@pytest.mark.parametrize("lags", [[-1., 1., 1., 1., 1.], [1., 2.], [1., 1., 1., 1., 20.],
                                  [1., 1., 1., 1., float("nan")]])
def test_bad_clock_small_samples_outliers_or_nonfinite_do_not_pass(lags: list[float]) -> None:
    assert not lag_summary(lags)["transport_short_probe_pass"]


def test_location_is_exact_and_blank_location_selector_is_supported() -> None:
    assert selector("CM.RUS.00.HHZ") == ("CM", "RUS", "00HHZ")
    assert selector("IM.ROSC..BHZ") == ("IM", "ROSC", "BHZ")


def test_catalog_does_not_subscribe_unadvertised_or_duplicate_stations() -> None:
    xml = ('<seedlink><station network="CM" name="RUS">'
           '<stream location="00" seedname="HHZ" type="D"/>'
           '</station></seedlink>')
    assert select_advertised(xml, ["CM.RUS.00.HHZ", "CM.PRA.00.HHZ", "CM.RUS.00.HHZ",
                                   "CM.RUS.10.HHZ"]) == ["CM.RUS.00.HHZ"]


def test_metadata_announcements_are_not_waveform_data() -> None:
    xml = ('<seedlink><station network="CM" name="RUS">'
           '<stream location="00" seedname="HHZ" type="L"/>'
           '</station></seedlink>')
    assert select_advertised(xml, ["CM.RUS.00.HHZ"]) == []


def test_info_connection_is_closed_and_not_reused_for_data(monkeypatch: pytest.MonkeyPatch) -> None:
    instances = []
    shutdown_calls = []

    class Connection:
        def __init__(self) -> None:
            self.stop = threading.Event()
            self.socket = SimpleNamespace(shutdown=lambda how: shutdown_calls.append(how))

        def set_net_timeout(self, value: float) -> None:
            pass

        def terminate(self) -> None:
            self.stop.set()

    class Client:
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.conn = Connection()
            self.info_used = False
            self.closed = False
            instances.append(self)

        def connect(self) -> None:
            pass

        def close(self) -> None:
            self.closed = True

        def get_info(self, level: str) -> str:
            self.info_used = True
            return ('<seedlink><station network="CM" name="RUS">'
                    '<stream location="00" seedname="HHZ" type="D"/>'
                    '</station></seedlink>')

        def select_stream(self, *args: str) -> None:
            assert not self.info_used, "INFO protocol state must not leak into sampling"

        def run(self) -> None:
            assert self.conn.timeout >= 30, "collect timeout is not sample-age acceptance"
            self.on_data(SimpleNamespace(id="CM.RUS.00.HHZ", data=[1.], stats=SimpleNamespace(
                endtime=100., starttime=100., delta=.01, sampling_rate=100.)))
            self.conn.stop.wait(1)

    monkeypatch.setattr(audit_tool, "EasySeedLinkClient", Client)
    result = audit_tool.audit("fake.example:18000", ["CM.RUS.00.HHZ"], .1)
    assert len(instances) == 2
    assert instances[0].closed
    assert result["errors"] == []
    assert result["worker_stopped"]
    assert shutdown_calls, "Deadline must interrupt a potentially blocking socket read"
    assert result["streams"]["CM.RUS.00.HHZ"]["packets"] == 1
