from __future__ import annotations

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
from eew.seedlink import SeedLinkProviderWorker


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
