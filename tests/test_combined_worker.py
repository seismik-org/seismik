from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from dispatcher import combined


@pytest.mark.asyncio
async def test_combined_worker_uses_one_health_server_and_stops_the_pair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The cheaper shared worker must not leave integrations running alone."""

    calls: list[tuple[str, bool]] = []
    cancelled = asyncio.Event()
    health = SimpleNamespace(shutdown=lambda: calls.append(("health", True)))

    async def failing_dispatcher(*, serve_health: bool) -> None:
        calls.append(("dispatcher", serve_health))
        raise RuntimeError("dispatcher failed")

    async def waiting_integrations(*, serve_health: bool) -> None:
        calls.append(("integrations", serve_health))
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    monkeypatch.setattr(combined, "start_health_server", lambda: health)
    monkeypatch.setattr(combined, "run_dispatcher", failing_dispatcher)
    monkeypatch.setattr(combined, "run_integrations", waiting_integrations)

    with pytest.raises(RuntimeError, match="dispatcher failed"):
        await combined.run_combined()

    assert ("dispatcher", False) in calls
    assert ("integrations", False) in calls
    assert cancelled.is_set()
    assert ("health", True) in calls


@pytest.mark.asyncio
async def test_clean_worker_exit_also_cancels_the_other_worker(monkeypatch):
    cancelled = asyncio.Event()
    health = SimpleNamespace(shutdown=lambda: None)

    async def finished(*, serve_health):
        return

    async def running(*, serve_health):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    monkeypatch.setattr(combined, "start_health_server", lambda: health)
    monkeypatch.setattr(combined, "run_dispatcher", finished)
    monkeypatch.setattr(combined, "run_integrations", running)
    with pytest.raises(RuntimeError, match="stopped unexpectedly"):
        await asyncio.wait_for(combined.run_combined(), timeout=2)
    assert cancelled.is_set()
