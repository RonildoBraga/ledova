from unittest.mock import patch

from django.core.cache import caches
from django.test import SimpleTestCase
from redis.exceptions import RedisError
from rest_framework.test import APITestCase

from authentication.throttles import EmailRateThrottle
from ledova_backend.settings import base
from shared.api.exceptions import CACHE_UNAVAILABLE

LOGIN = "authentication.views.user.SessionService.login"


class TheDeployedCacheIsConfiguredToOutliveOneProcessTest(SimpleTestCase):

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


class ACacheThatWillNotAnswerIsNotAFiveHundredTest(APITestCase):

    def test_a_throttle_that_cannot_reach_the_cache_answers_503_rather_than_crashing(self):
        with patch.object(EmailRateThrottle, "cache") as cache:
            cache.get.side_effect = RedisError("Error 111 connecting to redis:6379. Connection refused.")

            response = self.client.post("/api/signin/", {"email": "someone@example.com", "password": "x"})

        self.assertEqual(response.status_code, 503, response.content)
        self.assertEqual(response.json()["detail"], CACHE_UNAVAILABLE)

    def test_the_credentials_are_never_reached_when_the_throttle_cannot_count(self):
        with patch.object(EmailRateThrottle, "cache") as cache, patch(LOGIN) as authenticate:
            cache.get.side_effect = RedisError("no route to host")

            response = self.client.post("/api/signin/", {"email": "someone@example.com", "password": "x"})

        self.assertEqual(response.status_code, 503)
        authenticate.assert_not_called()
