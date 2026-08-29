from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import numpy as np
from obspy import Trace, UTCDateTime

from eew.alerts import AlertDispatcher
from eew.coincidence import ZoneCoincidenceRouter
from eew.config import (
    AlertSettings,
    CoincidenceSettings,
    DetectionSettings,
    SeedLinkProvider,
    SeedLinkSettings,
    StationSubscription,
)
from eew.seedlink import SeedLinkProviderWorker, create_seedlink_client


class FakeConnection:
    def __init__(self) -> None:
        self.timeout: float | None = None
        self.terminated = False

    def set_net_timeout(self, timeout: float) -> None:
        self.timeout = timeout

    def terminate(self) -> None:
        self.terminated = True


class FakeClient:
    def __init__(self, on_data: Any, fail: bool, stop: Any) -> None:
        self.conn = FakeConnection()
        self.on_data = on_data
        self.fail = fail
        self.stop = stop
        self.selected: list[tuple[str, str, str]] = []

    def select_stream(self, network: str, station: str, selector: str) -> None:
        self.selected.append((network, station, selector))

    def run(self) -> None:
        if self.fail:
            raise ConnectionError("corte simulado")
        trace = Trace(data=np.zeros(100, dtype=np.float64))
        trace.stats.network = "CM"
        trace.stats.station = "ARGC"
        trace.stats.location = "00"
        trace.stats.channel = "HHZ"
        trace.stats.starttime = UTCDateTime("2026-01-01T00:00:00Z")
        trace.stats.sampling_rate = 100.0
        self.on_data(trace)
        self.stop()


def test_client_applies_timeout_before_connect(monkeypatch: Any) -> None:
    observed: dict[str, float | None] = {}

    def connect(client: Any) -> None:
        observed["connect_timeout"] = client.conn.timeout
        observed["network_timeout"] = client.conn.netto

    monkeypatch.setattr(
        "eew.seedlink.EasySeedLinkClient.connect",
        connect,
    )

    client = create_seedlink_client(
        "seedlink.example:18000",
        on_data=lambda _trace: None,
        on_seedlink_error=lambda: None,
        on_terminate=lambda: None,
        network_timeout_seconds=7,
    )

    assert observed == {"connect_timeout": 7, "network_timeout": 7}
    assert client.conn.timeout == 7


def test_worker_recovers_after_simulated_connection_cut() -> None:
    provider = SeedLinkProvider(
        id="test-co",
        server="seedlink.invalid:18000",
        country_code="CO",
        stations=(
            StationSubscription(
                "CM", "ARGC", "HHZ", "00", "00HHZ", "CO", "CO"
            ),
        ),
    )
    seedlink = SeedLinkSettings(
        providers=(provider,),
        reconnect_initial_seconds=0.001,
        reconnect_max_seconds=0.002,
        reconnect_jitter_fraction=0,
        network_timeout_seconds=7,
    )
    clients: list[FakeClient] = []
    worker: SeedLinkProviderWorker

    def factory(_server: str, **callbacks: Any) -> FakeClient:
        assert callbacks["network_timeout_seconds"] == 7
        client = FakeClient(
            callbacks["on_data"],
            fail=not clients,
            stop=lambda: worker.stop(),
        )
        clients.append(client)
        return client

    worker = SeedLinkProviderWorker(
        provider,
        seedlink,
        DetectionSettings(filter_enabled=False),
        ZoneCoincidenceRouter(CoincidenceSettings()),
        AlertDispatcher(AlertSettings()),
        client_factory=factory,  # type: ignore[arg-type]
        jitter_source=lambda low, _high: low,
    )
    worker.run_forever()

    assert len(clients) == 2
    assert all(client.conn.timeout == 7 for client in clients)
    assert all(client.conn.terminated for client in clients)
    assert clients[1].selected == [("CM", "ARGC", "00HHZ")]
    assert worker.consecutive_failures == 1


def test_station_health_reports_fresh_and_stale_packets() -> None:
    provider = SeedLinkProvider(
        id="test-co",
        server="seedlink.invalid:18000",
        country_code="CO",
        stations=(StationSubscription("CM", "ARGC", "HHZ", "00", "00HHZ", "CO", "CO"),),
    )
    worker = SeedLinkProviderWorker(
        provider,
        SeedLinkSettings(providers=(provider,), station_stale_after_seconds=10),
        DetectionSettings(filter_enabled=False),
        ZoneCoincidenceRouter(CoincidenceSettings(max_station_lag_seconds=5)),
        AlertDispatcher(AlertSettings()),
    )
    processor = next(iter(worker.processors.values()))
    trace = Trace(data=np.zeros(100, dtype=np.float64))
    trace.stats.network = "CM"
    trace.stats.station = "ARGC"
    trace.stats.location = "00"
    trace.stats.channel = "HHZ"
    trace.stats.starttime = UTCDateTime("2026-01-01T00:00:00Z")
    trace.stats.sampling_rate = 100.0
    processor.process(trace, received_at=datetime(2026, 1, 1, 0, 0, 2, tzinfo=timezone.utc))

    fresh = worker.health_snapshot(datetime(2026, 1, 1, 0, 0, 3, tzinfo=timezone.utc))
    row = next(iter(fresh.values()))
    assert row["healthy"] is True
    assert row["reason"] == "ok"
    assert row["packet_lag_seconds"] == 1.01

    stale = worker.health_snapshot(datetime(2026, 1, 1, 0, 0, 20, tzinfo=timezone.utc))
    row = next(iter(stale.values()))
    assert row["healthy"] is False
    assert row["reason"] == "stale"
