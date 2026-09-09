import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from copy import deepcopy
from unittest.mock import patch

import django


def run():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ledova_backend.settings.test")
    django.setup()

    from django.core.cache.backends.redis import RedisCache
    from django.test import override_settings
    from redis import Redis
    from rest_framework.exceptions import AuthenticationFailed
    from rest_framework.test import APIClient

    from ledova_backend.settings import base

    parameters = json.loads(sys.argv[1])
    configuration = deepcopy(base.CACHES)
    configuration["default"].update(LOCATION=os.environ["THROTTLE_TEST_REDIS_URL"], KEY_PREFIX=parameters["prefix"])
    control = Redis.from_url(os.environ["THROTTLE_TEST_REDIS_URL"], socket_timeout=2, socket_connect_timeout=2)
    original_get = RedisCache.get

    def hold_history_read(cache, key, *args, **kwargs):
        value = original_get(cache, key, *args, **kwargs)
        if key.startswith("throttle_auth_email_"):
            barrier = parameters["prefix"] + ":history-reads"
            control.incr(barrier)
            deadline = time.monotonic() + 15
            while int(control.get(barrier) or 0) < parameters["total"]:
                if time.monotonic() >= deadline:
                    raise RuntimeError("Concurrent history reads did not reach the barrier")
                time.sleep(0.01)
        return value

    def signin(_):
        response = APIClient().post(
            "/api/signin/", {"email": parameters["email"], "password": "incorrect"}, format="json"
        )
        return {"status": response.status_code, "retry_after": response.get("Retry-After")}

    try:
        with override_settings(CACHES=configuration, ALLOWED_HOSTS=["testserver"]), patch(
            "authentication.views.user.SessionService.login", side_effect=AuthenticationFailed("Invalid credentials")
        ) as login:
            if parameters.get("concurrent"):
                with patch.object(RedisCache, "get", hold_history_read), ThreadPoolExecutor(
                    max_workers=parameters["count"]
                ) as pool:
                    responses = list(pool.map(signin, range(parameters["count"])))
            else:
                responses = [signin(i) for i in range(parameters["count"])]
            return {"responses": responses, "credential_checks": login.call_count}
    finally:
        control.close()


if __name__ == "__main__":
    with redirect_stdout(sys.stderr):
        result = run()
    print(json.dumps(result))
