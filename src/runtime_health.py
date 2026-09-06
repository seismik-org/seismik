"""Minimal HTTP health endpoint for long-running Cloud Run workers."""
from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable

DetailsProvider = Callable[[], dict[str, Any]]


def _make_handler(details: DetailsProvider | None) -> type[BaseHTTPRequestHandler]:
    class _HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib callback name
            if self.path not in {"/", "/healthz", "/health/ready"}:
                self.send_response(404)
                self.end_headers()
                return
            body: dict[str, Any] = {"status": "ok"}
            if details is not None:
                try:
                    body["delivery"] = details()
                except Exception as error:  # noqa: BLE001 - la salud nunca falla duro
                    body["delivery_error"] = str(error)[:200]
            payload = json.dumps(body, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, _format: str, *_args: object) -> None:
            return

    return _HealthHandler


def start_health_server(details: DetailsProvider | None = None) -> ThreadingHTTPServer:
    """Start a daemon health server and return it for optional shutdown.

    ``details`` allows a worker to publish counters (for example the detector
    link towards the events API) without adding a dependency on FastAPI.
    """

    port = int(os.getenv("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), _make_handler(details))
    threading.Thread(target=server.serve_forever, name="health-server", daemon=True).start()
    return server
