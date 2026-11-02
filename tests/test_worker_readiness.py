from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

import pytest

from api.config import AppSettings
from runtime_health import _make_handler


@contextmanager
def server(details):
    instance = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(details))
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    try:
        yield instance.server_port
    finally:
        instance.shutdown()
        instance.server_close()
        thread.join(timeout=2)


def probe(port, path):
    connection = HTTPConnection("127.0.0.1", port, timeout=2)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        return response.status, json.loads(response.read())
    finally:
        connection.close()


def test_failed_telemetry_fails_readiness_but_keeps_liveness_and_redacts_error():
    def unavailable():
        raise RuntimeError("sensitive-internal-value")

    with server(unavailable) as port:
        status, body = probe(port, "/health/ready")
        assert status == 503 and body["status"] == "not_ready"
        assert body["delivery_error"] == "RuntimeError"
        assert probe(port, "/health/live") == (200, {"status": "ok"})
        assert probe(port, "/healthz")[0] == 200


@pytest.mark.parametrize("status,expected", [("ready", 200), ("degraded", 503)])
def test_seedlink_readiness_tracks_actual_coverage(status, expected):
    with server(lambda: {"seedlink": {"status": status}}) as port:
        assert probe(port, "/health/ready")[0] == expected
        assert probe(port, "/health/live")[0] == 200


def test_initialization_is_not_ready():
    with server(lambda: {"ready": False, "status": "initializing"}) as port:
        assert probe(port, "/health/ready")[0] == 503


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_deployed_environment_requires_edge_secret(environment):
    values = dict(environment=environment, integrity_verification_enabled=True,
                  webhook_hmac_secret="test-webhook", crowd_master_secret="test-crowd",
                  integration_webhook_master_secret="test-integration", consumer_api_key="test-api")
    with pytest.raises(ValueError, match="edge origin secret"):
        AppSettings(**values)
    assert AppSettings(**values, edge_origin_secret="test-edge").environment == environment
