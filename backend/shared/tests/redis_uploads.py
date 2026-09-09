import json
import os
import socket
import subprocess
import sys
import time
import uuid

from django.core.cache import caches
from django.test import SimpleTestCase, override_settings
from redis import Redis

from shared.upload_errors import UploadUnavailable
from shared.upload_limits import reserve_bytes, reserve_request


class SharedUploadQuotaTest(SimpleTestCase):
    def setUp(self):
        self.url = os.environ["UPLOAD_TEST_REDIS_URL"]
        self.prefix = "ledova-upload-test-" + uuid.uuid4().hex
        self.redis = Redis.from_url(self.url, socket_timeout=2, socket_connect_timeout=2)
        self.addCleanup(self.redis.close)
        self.addCleanup(self.remove_owned_keys)
        self.redis.ping()
        configuration = {
            "default": {
                "BACKEND": "shared.cache.SharedRedisCache",
                "LOCATION": self.url,
                "KEY_PREFIX": self.prefix,
                "OPTIONS": {"socket_timeout": 2, "socket_connect_timeout": 2},
            }
        }
        cache_settings = override_settings(CACHES=configuration)
        cache_settings.enable()
        self.addCleanup(cache_settings.disable)

    def remove_owned_keys(self):
        keys = list(self.redis.scan_iter(match=self.prefix + "*"))
        if keys:
            self.redis.delete(*keys)

    def test_a_denial_before_expiry_cannot_strand_the_used_byte_total(self):
        cache = caches["default"]
        self.assertTrue(cache.take_upload_bytes("user", 100, 100, 1)[0])
        time.sleep(0.65)
        self.assertFalse(cache.take_upload_bytes("user", 1, 100, 1)[0])
        time.sleep(0.45)

        self.assertTrue(cache.take_upload_bytes("user", 100, 100, 1)[0])
        self.assertFalse(cache.take_upload_bytes("user", 1, 100, 1)[0])

    def test_independent_users_have_independent_byte_windows(self):
        cache = caches["default"]
        self.assertTrue(cache.take_upload_bytes("first", 100, 100, 60)[0])
        self.assertFalse(cache.take_upload_bytes("first", 1, 100, 60)[0])
        self.assertTrue(cache.take_upload_bytes("second", 100, 100, 60)[0])

    def test_real_connection_failure_refuses_both_count_and_byte_reservations(self):
        reserve_request("positive-control")
        reserve_bytes("positive-control", 10)
        with socket.socket() as unavailable:
            unavailable.bind(("127.0.0.1", 0))
            configuration = {
                "default": {
                    "BACKEND": "shared.cache.SharedRedisCache",
                    "LOCATION": f"redis://127.0.0.1:{unavailable.getsockname()[1]}/0",
                    "OPTIONS": {"socket_connect_timeout": 1, "socket_timeout": 1},
                }
            }
            with override_settings(CACHES=configuration):
                for reserve, arguments in ((reserve_request, ("synthetic",)), (reserve_bytes, ("synthetic", 10))):
                    with self.subTest(reserve=reserve), self.assertRaises(UploadUnavailable) as refused:
                        reserve(*arguments)
                    self.assertEqual(refused.exception.status_code, 503)

    def worker(self, kind, concurrent):
        parameters = {"prefix": self.prefix, "kind": kind, "concurrent": concurrent}
        process = subprocess.Popen(
            [sys.executable, "-m", "shared.tests.redis_upload_worker", json.dumps(parameters)],
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
        stdout, stderr = process.communicate(timeout=20)
        self.assertEqual(process.returncode, 0, stderr)
        return json.loads(stdout)

    def test_concurrent_processes_share_atomic_count_and_byte_limits_after_restart(self):
        for kind in ("bytes", "requests"):
            with self.subTest(kind=kind):
                workers = [self.worker(kind, True) for _ in range(4)]
                statuses = [status for worker in workers for status in self.result(worker)]
                self.assertEqual(statuses.count(200), 10, statuses)
                self.assertEqual(statuses.count(429), 30, statuses)
                self.assertEqual(self.result(self.worker(kind, False)), [429] * 10)
