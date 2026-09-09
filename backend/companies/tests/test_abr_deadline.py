import signal
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Event, Thread
from time import monotonic
from unittest.mock import patch
from urllib.parse import parse_qs

from django.test import SimpleTestCase, override_settings

from companies.tests.test_abr_client import ENTITY, registry_xml
from integrations.abr.client import MAX_RESPONSE_BYTES, MAX_WORKER_BYTES, lookup_company


@contextmanager
def local_registry(mode="valid"):
    stopped = Event()
    requests = []
    body = registry_xml(ENTITY)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            requests.append(parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode()))
            self.send_response(200)
            self.send_header("Content-Length", str(MAX_RESPONSE_BYTES + 1 if mode == "oversized" else len(body)))
            self.end_headers()
            if mode == "oversized":
                stopped.wait(10)
                return
            try:
                if mode == "slow":
                    for value in body:
                        if stopped.wait(0.05):
                            return
                        self.wfile.write(bytes([value]))
                        self.wfile.flush()
                else:
                    self.wfile.write(body)
            except OSError:
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", requests
    finally:
        stopped.set()
        server.shutdown()
        server.server_close()
        thread.join(5)


def local_worker(url, dns_marker=None):
    prelude = ""
    if dns_marker:
        prelude = (
            "import socket, time\nfrom pathlib import Path\n"
            "def blocked_dns(*args, **kwargs):\n"
            f"    Path({str(dns_marker)!r}).write_text('entered')\n"
            "    time.sleep(30)\n"
            "socket.getaddrinfo = blocked_dns\n"
        )
    return (
        sys.executable,
        "-c",
        prelude + "from integrations.abr import client, worker\n" + f"client.ABR_SERVICE = {url!r}\nworker.main()\n",
    )


@override_settings(ABR_AUTH_GUID="synthetic-guid-through-stdin")
class ABRLookupDeadlineTest(SimpleTestCase):
    def run_worker(self, command):
        started = monotonic()
        children = []
        real_popen = subprocess.Popen

        def spawn(*args, **kwargs):
            self.assertNotIn("synthetic-guid-through-stdin", str(args))
            self.assertNotIn("synthetic-guid-through-stdin", str(kwargs))
            self.assertEqual(kwargs["stderr"], subprocess.DEVNULL)
            self.assertEqual(kwargs["env"], {"PYTHONDONTWRITEBYTECODE": "1"})
            child = real_popen(*args, **kwargs)
            children.append(child)
            return child

        with patch("integrations.abr.client.WORKER_COMMAND", command), patch(
            "integrations.abr.client.LOOKUP_DEADLINE_SECONDS", 2
        ), patch("integrations.abr.client.subprocess.Popen", side_effect=spawn):
            observation = lookup_company(acn="123456780", abn="")
        elapsed = monotonic() - started
        self.assertEqual(len(children), 1)
        self.assertIsNotNone(children[0].poll())
        self.assertEqual(children[0].wait(timeout=0), children[0].returncode)
        self.assertNotIn("synthetic-guid-through-stdin", repr(observation))
        self.assertLess(elapsed, 6)
        return observation, children[0].returncode

    def test_local_valid_response_crosses_the_pipe_without_exposing_the_guid(self):
        with local_registry() as (url, requests):
            observation, status = self.run_worker(local_worker(url))
        self.assertEqual(observation.entity_name, "Synthetic Example Pty Ltd")
        self.assertEqual(observation.entity_status, "Active")
        self.assertEqual(observation.effective_from.isoformat(), "2025-01-01")
        self.assertEqual(status, 0)
        self.assertEqual(requests[0]["authenticationGuid"], ["synthetic-guid-through-stdin"])

    def test_oversized_response_is_refused_before_waiting_for_its_body(self):
        with local_registry("oversized") as (url, requests):
            observation, status = self.run_worker(local_worker(url))
        self.assertEqual(len(requests), 1)
        self.assertEqual(observation.reason, "invalid_response")
        self.assertEqual(status, 0)

    def test_a_trickling_body_cannot_extend_the_whole_call_deadline(self):
        with local_registry("slow") as (url, requests):
            observation, status = self.run_worker(local_worker(url))
        self.assertEqual(len(requests), 1)
        self.assertEqual(observation.reason, "timeout")
        self.assertEqual(status, -signal.SIGKILL)

    def test_blocked_dns_is_killed_and_reaped_at_the_whole_call_deadline(self):
        with tempfile.TemporaryDirectory() as directory, local_registry() as (url, requests):
            marker = Path(directory) / "dns-entered"
            observation, status = self.run_worker(local_worker(url, dns_marker=marker))
            self.assertEqual(marker.read_text(), "entered")
        self.assertEqual(requests, [])
        self.assertEqual(observation.reason, "timeout")
        self.assertEqual(status, -signal.SIGKILL)

    def test_child_output_is_capped_without_waiting_for_the_child_to_exit(self):
        command = (
            sys.executable,
            "-c",
            f"import sys, time; sys.stdout.buffer.write(b'x' * {MAX_WORKER_BYTES + 1}); "
            "sys.stdout.flush(); time.sleep(30)",
        )
        observation, status = self.run_worker(command)
        self.assertEqual(observation.reason, "invalid_response")
        self.assertEqual(status, -signal.SIGKILL)

    @patch("integrations.abr.client.Timer.start", side_effect=RuntimeError("Synthetic thread exhaustion"))
    def test_deadline_setup_failure_kills_and_reaps_the_child(self, start):
        observation, status = self.run_worker((sys.executable, "-c", "import time; time.sleep(30)"))
        self.assertEqual(observation.reason, "unavailable")
        self.assertEqual(status, -signal.SIGKILL)

    @patch("integrations.abr.client.subprocess.Popen")
    def test_unconfigured_lookup_does_not_start_a_child(self, spawn):
        with override_settings(ABR_AUTH_GUID=""):
            self.assertEqual(lookup_company(acn="123456780", abn="").reason, "unconfigured")
        spawn.assert_not_called()
