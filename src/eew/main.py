from __future__ import annotations

import argparse
import logging
import os
import signal
from pathlib import Path
from typing import Any

from eew.alerts import AlertDispatcher
from eew.config import Settings
from eew.official import OfficialReportService
from eew.phase_association import PhaseAssociator
from eew.quality_worker import CandidateQualityWorker
from eew.seedlink import SeedLinkDetectionService
from runtime_health import start_health_server


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Motor SeedLink + STA/LTA")
    parser.add_argument(
        "--config",
        default=os.getenv("SEISMIK_CONFIG", "config.json"),
        help="Ruta al archivo JSON (por defecto: config.json o SEISMIK_CONFIG)",
    )
    return parser.parse_args()


def main() -> None:
    # La sonda debe responder antes de abrir SeedLink; el enlace hacia la API
    # se publica en cuanto el despachador existe.
    link: dict[str, Any] = {}
    health_server = start_health_server(
        lambda: {
            "dispatcher": link["dispatcher"].health(),
            "seedlink": link["service"].coverage_snapshot(),
        }
        if "dispatcher" in link and "service" in link
        else {"ready": False, "status": "initializing"}
    )
    args = parse_args()
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)sZ %(levelname)s %(name)s %(message)s",
    )
    logging.Formatter.converter = __import__("time").gmtime

    config_path = Path(args.config)
    settings = Settings.load(config_path)
    dispatcher = AlertDispatcher(settings.alert)
    link["dispatcher"] = dispatcher
    official_reports = OfficialReportService(settings.official_reports, dispatcher.submit)
    service = SeedLinkDetectionService(settings, dispatcher, official_reports.submit)
    quality_worker = None
    if settings.coincidence.phase_association_enabled:
        table_path = Path(settings.coincidence.phase_travel_time_table)
        if not table_path.is_absolute():
            table_path = config_path.parent / table_path
        def on_regional_candidate(candidate: Any) -> None:
            official_reports.submit(candidate)
            if service.live_magnitude is not None:
                service.live_magnitude.schedule(candidate)

        quality_worker = CandidateQualityWorker(
            PhaseAssociator(table_path), dispatcher.submit, on_regional_candidate
        )
        for worker in service.workers:
            worker.on_trigger = quality_worker.observe
            worker.publish_candidate = quality_worker.submit
    link["service"] = service

    def request_stop(_signum: int, _frame: object) -> None:
        logging.getLogger(__name__).info("Apagado solicitado")
        service.stop()

    signal.signal(signal.SIGINT, request_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, request_stop)

    dispatcher.start()
    if quality_worker is not None:
        quality_worker.start()
    try:
        service.run_forever()
    finally:
        service.stop()
        if quality_worker is not None:
            quality_worker.close()
        official_reports.close()
        dispatcher.close()
        health_server.shutdown()


if __name__ == "__main__":
    main()
