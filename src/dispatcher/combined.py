"""One always-on Cloud Run worker for delivery and integrations.

Both workloads wait on Redis or make network calls; keeping them in separate
one-vCPU services doubled the idle CPU bill without improving correctness.
They share a single health endpoint and fail together so Cloud Run restarts a
known-good pair rather than leaving half of the alert pipeline alive.
"""
from __future__ import annotations

import asyncio
import logging

from dispatcher.consumer import run_dispatcher
from dispatcher.integrations import run_integrations
from runtime_health import start_health_server

LOGGER = logging.getLogger(__name__)


async def run_combined() -> None:
    health_server = start_health_server()
    dispatcher = asyncio.create_task(run_dispatcher(serve_health=False), name="dispatcher")
    integrations = asyncio.create_task(
        run_integrations(serve_health=False), name="integrations"
    )
    tasks = (dispatcher, integrations)
    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
        for task in done:
            # Propagate an unexpected exit: Cloud Run will restart the pair.
            task.result()
        # A clean unexpected exit is also unhealthy for an always-on worker.
        raise RuntimeError("combined worker stopped unexpectedly")
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        health_server.shutdown()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)sZ %(levelname)s %(name)s %(message)s",
    )
    asyncio.run(run_combined())


if __name__ == "__main__":
    main()
