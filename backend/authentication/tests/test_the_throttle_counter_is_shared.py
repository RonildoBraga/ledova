from django.core.cache import caches
from django.test import SimpleTestCase

from authentication.throttles import EmailRateThrottle
from ledova_backend.settings import base


class TheThrottleCounterOutlivesOneProcessTest(SimpleTestCase):

    def test_the_deployed_default_cache_is_not_held_in_one_process(self):
        self.assertEqual(base.CACHES["default"]["BACKEND"], "django.core.cache.backends.redis.RedisCache")
        self.assertEqual(base.CACHES["default"]["LOCATION"], base.REDIS_URL)

    def test_the_deployed_cache_is_the_redis_the_stack_already_runs(self):
        self.assertTrue(base.REDIS_URL.startswith("redis://"))
        self.assertEqual(base.CACHES["default"]["KEY_PREFIX"], "ledova")

    def test_the_throttle_counts_in_the_default_cache_rather_than_one_of_its_own(self):
        self.addCleanup(caches["default"].delete, "throttle-store-probe")

        EmailRateThrottle().cache.set("throttle-store-probe", "written by the throttle", 30)

        self.assertEqual(caches["default"].get("throttle-store-probe"), "written by the throttle")

    def test_the_key_is_the_address_so_two_processes_count_the_same_one(self):
        first = EmailRateThrottle().get_cache_key(_a_request("Someone@Example.COM"), None)
        second = EmailRateThrottle().get_cache_key(_a_request("someone@example.com"), None)

        self.assertEqual(first, second)
        self.assertIn("someone@example.com", first)


class _User:
    is_authenticated = False


class _Request:
    def __init__(self, email):
        self.data = {"email": email}
        self.user = _User()


def _a_request(email):
    return _Request(email)
