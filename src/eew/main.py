from __future__ import annotations

import argparse
import logging
import os
import signal
from pathlib import Path

from eew.alerts import AlertDispatcher
from eew.config import Settings
from eew.official import OfficialReportService
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
    link: dict[str, AlertDispatcher] = {}
    health_server = start_health_server(
        lambda: link["dispatcher"].health() if "dispatcher" in link else {"pending": 0}
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

    def request_stop(_signum: int, _frame: object) -> None:
        logging.getLogger(__name__).info("Apagado solicitado")
        service.stop()

    signal.signal(signal.SIGINT, request_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, request_stop)

    dispatcher.start()
    try:
        service.run_forever()
    finally:
        service.stop()
        official_reports.close()
        dispatcher.close()
        health_server.shutdown()


if __name__ == "__main__":
    main()
