import json
import os
import socket
import subprocess
import sys
import time
import uuid
from copy import deepcopy
from unittest.mock import patch

from django.core.cache import caches
from django.test import SimpleTestCase, override_settings
from redis import Redis
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIClient

from authentication.throttles import EmailRateThrottle
from ledova_backend.settings import base
from shared.api.exceptions import CACHE_UNAVAILABLE

LOGIN = "authentication.views.user.SessionService.login"


class SharedRedisThrottleTests(SimpleTestCase):
    def setUp(self):
        self.url = os.environ["THROTTLE_TEST_REDIS_URL"]
        self.prefix = "ledova-throttle-test-" + uuid.uuid4().hex
        self.configuration = deepcopy(base.CACHES)
        self.configuration["default"].update(LOCATION=self.url, KEY_PREFIX=self.prefix)
        self.redis = Redis.from_url(self.url, socket_timeout=2, socket_connect_timeout=2)
        self.addCleanup(self.redis.close)
        self.addCleanup(self.remove_owned_keys)
        self.redis.ping()
        cache_settings = override_settings(CACHES=self.configuration)
        cache_settings.enable()
        self.addCleanup(cache_settings.disable)

    def remove_owned_keys(self):
        keys = list(self.redis.scan_iter(match=self.prefix + "*"))
        if keys:
            self.redis.delete(*keys)

    def worker(self, count, email="someone@example.com", concurrent=False):
        parameters = {"prefix": self.prefix, "count": count, "email": email, "concurrent": concurrent, "total": 24}
        process = subprocess.Popen(
            [sys.executable, "-m", "authentication.tests.redis_worker", json.dumps(parameters)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.addCleanup(self.stop_worker, process)
        return process

    @staticmethod
    def stop_worker(process):
        if process.poll() is None:
            process.kill()
        process.communicate()

    def result(self, process):
        stdout, stderr = process.communicate(timeout=40)
        self.assertEqual(process.returncode, 0, stderr)
        return json.loads(stdout)

    def statuses(self, result):
        return [response["status"] for response in result["responses"]]

    def signin(self, email="someone@example.com"):
        return APIClient().post("/api/signin/", {"email": email, "password": "incorrect"}, format="json")

    def test_fresh_processes_share_ten_attempts_and_restart_does_not_reset_them(self):
        first = self.result(self.worker(6, "Someone@Example.COM"))
        second = self.result(self.worker(6))
        restarted = self.result(self.worker(1))

        self.assertEqual(self.statuses(first), [401] * 6)
        self.assertEqual(self.statuses(second), [401] * 4 + [429] * 2)
        self.assertEqual(self.statuses(restarted), [429])
        self.assertEqual(
            [first["credential_checks"], second["credential_checks"], restarted["credential_checks"]], [6, 4, 0]
        )
        self.assertGreater(int(restarted["responses"][0]["retry_after"]), 0)
        self.assertLessEqual(int(restarted["responses"][0]["retry_after"]), 3600)

    def test_concurrent_workers_cannot_lose_attempts_between_read_and_write(self):
        workers = [self.worker(12, concurrent=True), self.worker(12, concurrent=True)]
        results = [self.result(worker) for worker in workers]
        statuses = [value for result in results for value in self.statuses(result)]

        self.assertEqual(statuses.count(401), 10, statuses)
        self.assertEqual(statuses.count(429), 14, statuses)
        self.assertEqual(sum(result["credential_checks"] for result in results), 10)

    def test_another_address_has_its_own_limit(self):
        self.result(self.worker(10))
        with patch(LOGIN, side_effect=AuthenticationFailed("Invalid credentials")):
            self.assertEqual(self.signin().status_code, 429)
            self.assertEqual(self.signin("independent@example.com").status_code, 401)

    def test_window_expires_and_denied_requests_do_not_extend_it(self):
        with patch.object(EmailRateThrottle, "rate", "1/sec", create=True), patch(
            LOGIN, side_effect=AuthenticationFailed("Invalid credentials")
        ) as login:
            self.assertEqual(self.signin().status_code, 401)
            refused = self.signin()
            self.assertEqual(refused.status_code, 429)
            self.assertEqual(refused["Retry-After"], "1")
            deadline = time.monotonic() + 3
            while True:
                time.sleep(0.05)
                response = self.signin()
                if response.status_code != 429 or time.monotonic() >= deadline:
                    break
            self.assertEqual(response.status_code, 401)
            self.assertEqual(login.call_count, 2)

    def test_real_connection_failure_returns_safe_503_before_checking_credentials(self):
        with socket.socket() as unavailable:
            unavailable.bind(("127.0.0.1", 0))
            configuration = deepcopy(self.configuration)
            configuration["default"]["LOCATION"] = f"redis://127.0.0.1:{unavailable.getsockname()[1]}/0"
            with override_settings(CACHES=configuration), patch(LOGIN) as login:
                response = self.signin()
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json()["detail"], CACHE_UNAVAILABLE)
            self.assertNotIn("redis", response.json()["detail"].lower())
            login.assert_not_called()

    def test_rolling_window_releases_only_the_oldest_attempt(self):
        with patch.object(EmailRateThrottle, "rate", "2/sec", create=True), patch(
            LOGIN, side_effect=AuthenticationFailed("Invalid credentials")
        ):
            self.assertEqual(self.signin().status_code, 401)
            time.sleep(0.6)
            self.assertEqual(self.signin().status_code, 401)
            self.assertEqual(self.signin().status_code, 429)
            deadline = time.monotonic() + 0.8
            while True:
                time.sleep(0.025)
                response = self.signin()
                if response.status_code != 429 or time.monotonic() >= deadline:
                    break
            self.assertEqual(response.status_code, 401)
            self.assertEqual(self.signin().status_code, 429)

    def test_regular_cache_values_still_round_trip_through_the_shared_store(self):
        caches["default"].set("transak-shaped-token", {"token": "synthetic", "expires": 42}, timeout=30)
        self.assertEqual(caches["default"].get("transak-shaped-token"), {"token": "synthetic", "expires": 42})
        self.assertTrue(list(self.redis.scan_iter(match=self.prefix + "*transak-shaped-token")))
