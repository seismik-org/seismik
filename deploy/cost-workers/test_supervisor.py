import importlib.util
import pathlib
import subprocess
import sys
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location(
    "worker_supervisor", pathlib.Path(__file__).with_name("supervisor.py")
)
supervisor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(supervisor)


def test_ready_requires_both_workers_and_endpoints():
    processes = [Mock(), Mock()]
    for process in processes:
        process.poll.return_value = None
    response = Mock()
    response.status = 200
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    with patch.object(supervisor.urllib.request, "urlopen", return_value=response) as request:
        assert supervisor.healthy(processes)
        assert request.call_count == 2
    processes[1].poll.return_value = 1
    assert not supervisor.healthy(processes)


def test_unavailable_endpoint_is_not_ready():
    process = Mock()
    process.poll.return_value = None
    with patch.object(supervisor.urllib.request, "urlopen", side_effect=OSError):
        assert not supervisor.healthy([process, process])


def test_shutdown_terminates_children():
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    supervisor.stop_children([process], timeout=2)
    assert process.poll() is not None
