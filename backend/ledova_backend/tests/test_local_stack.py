import importlib.util
import io
import socket
from contextlib import redirect_stderr
from pathlib import Path

import yaml
from django.conf import settings
from django.test import SimpleTestCase

REPO_ROOT = Path(settings.BASE_DIR).parent
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"
PORT_GUARD = REPO_ROOT / "scripts" / "check-port-free.py"
BACKEND_CONTEXT = "./backend"
OPTIONAL_ENV_FILE = "./backend/.env"


def compose_services():
    return yaml.safe_load(COMPOSE_FILE.read_text())["services"]


def declared_env(service):
    return {name: str(value) for name, value in (service.get("environment") or {}).items()}


def optional_env_files(service):
    return [entry["path"] for entry in service.get("env_file") or [] if entry.get("required") is False]


def port_guard():
    spec = importlib.util.spec_from_file_location("check_port_free", PORT_GUARD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ComposeStackTests(SimpleTestCase):
    def setUp(self):
        self.services = compose_services()

    def test_every_service_built_from_the_backend_image_carries_the_forced_environment(self):
        built = [
            name
            for name, service in self.services.items()
            if (service.get("build") or {}).get("context") == BACKEND_CONTEXT
        ]

        self.assertEqual(sorted(built), ["backend", "migrate", "worker"])
        for name in built:
            with self.subTest(service=name):
                environment = declared_env(self.services[name])
                self.assertEqual(environment.get("STORAGE_BACKEND"), "local")
                self.assertEqual(environment.get("DEBUG"), "true")

    def test_the_forced_environment_does_not_come_from_the_optional_env_file(self):
        for name in ("backend", "migrate", "worker"):
            with self.subTest(service=name):
                self.assertIn(OPTIONAL_ENV_FILE, optional_env_files(self.services[name]))
                self.assertEqual(declared_env(self.services[name]).get("DEBUG"), "true")


class PortGuardTests(SimpleTestCase):
    def setUp(self):
        self.guard = port_guard()

    def _run(self, port):
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            code = self.guard.main([str(port)])
        return code, stderr.getvalue()

    def test_a_free_port_passes_silently(self):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]

        code, message = self._run(port)

        self.assertEqual(code, 0)
        self.assertEqual(message, "")

    def test_an_occupied_port_fails_with_the_port_the_variable_and_the_way_out(self):
        with socket.socket() as taken:
            taken.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            taken.bind(("127.0.0.1", 0))
            taken.listen(1)
            port = taken.getsockname()[1]

            code, message = self._run(port)

        self.assertEqual(code, 1)
        self.assertIn(f"CHAIN_TEST_PORT={port}", message)
        self.assertIn("already in use", message)
        self.assertIn("make chain-test CHAIN_TEST_PORT=<port>", message)
