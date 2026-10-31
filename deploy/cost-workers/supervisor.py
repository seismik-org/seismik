"""Supervise unchanged workers; one failed worker restarts the whole instance."""

import json
import os
import signal
import subprocess
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def healthy(processes):
    if len(processes) != 2 or any(process.poll() is not None for process in processes):
        return False
    for port in (8081, 8082):
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/health/ready", timeout=1
            ) as response:
                if response.status != 200:
                    return False
        except (OSError, ValueError):
            return False
    return True


def stop_children(processes, timeout=7):
    for process in processes:
        if process.poll() is None:
            process.terminate()
    deadline = time.monotonic() + timeout
    for process in processes:
        try:
            process.wait(timeout=max(0.01, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def main():
    processes = []
    stopping = threading.Event()
    for name in (signal.SIGINT, signal.SIGTERM):
        signal.signal(name, lambda *_args: stopping.set())

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path not in {"/", "/healthz", "/health/ready"}:
                self.send_error(404)
                return
            ready = healthy(processes)
            body = json.dumps(
                {
                    "status": "ok" if ready else "not_ready",
                    "workers": ["dispatcher_integrations", "event_forwarder"],
                }
            ).encode()
            self.send_response(200 if ready else 503)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "8080"))), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    exit_code = 0
    try:
        dispatcher_env = dict(os.environ, PORT="8081", PYTHONPATH="/app/src")
        processes.append(
            subprocess.Popen(
                ["python", "-m", "dispatcher.combined"], cwd="/app", env=dispatcher_env
            )
        )
        forwarder_env = dict(
            os.environ,
            PORT="8082",
            PYTHONPATH="/opt/forwarder/app/src",
            PYTHONHOME="/opt/forwarder/runtime",
            LD_LIBRARY_PATH="/opt/forwarder/runtime/lib",
        )
        processes.append(
            subprocess.Popen(
                ["/opt/forwarder/runtime/bin/python3.12", "-m", "dispatcher.pubsub_forwarder"],
                cwd="/opt/forwarder/app",
                env=forwarder_env,
            )
        )
        deadline = time.monotonic() + 120
        while not stopping.wait(1):
            if healthy(processes):
                print("Combined workers ready: dispatcher + event_forwarder", flush=True)
                break
            if (
                any(process.poll() is not None for process in processes)
                or time.monotonic() > deadline
            ):
                raise RuntimeError("Worker failed to start")
        while not stopping.wait(1):
            if not healthy(processes):
                raise RuntimeError("Worker exited or health endpoint unavailable")
    except Exception:
        print("Combined worker unhealthy; restarting both workers", flush=True)
        exit_code = 1
    finally:
        stop_children(processes)
        server.shutdown()
        server.server_close()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
