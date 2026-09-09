import json
import os
import sys
import time

import django
from django.conf import settings
from redis import Redis
from rest_framework.exceptions import APIException


def run():
    parameters = json.loads(sys.argv[1])
    url = os.environ["UPLOAD_TEST_REDIS_URL"]
    settings.configure(
        CACHES={
            "default": {
                "BACKEND": "shared.cache.SharedRedisCache",
                "LOCATION": url,
                "KEY_PREFIX": parameters["prefix"],
            }
        },
        UPLOAD_BYTES_PER_HOUR=100,
        UPLOAD_REQUESTS_PER_HOUR=10,
        USE_I18N=False,
    )
    django.setup()
    from shared.upload_limits import reserve_bytes, reserve_request

    if parameters["concurrent"]:
        with Redis.from_url(url, socket_timeout=2, socket_connect_timeout=2) as redis:
            barrier = parameters["prefix"] + ":barrier:" + parameters["kind"]
            redis.incr(barrier)
            redis.expire(barrier, 30)
            deadline = time.monotonic() + 10
            while int(redis.get(barrier)) < 4:
                if time.monotonic() >= deadline:
                    raise TimeoutError()
                time.sleep(0.01)
    statuses = []
    for _ in range(10):
        try:
            if parameters["kind"] == "bytes":
                reserve_bytes("synthetic-user", 10)
            else:
                reserve_request("synthetic-user")
        except APIException as error:
            statuses.append(error.status_code)
        else:
            statuses.append(200)
    print(json.dumps(statuses))


if __name__ == "__main__":
    run()
