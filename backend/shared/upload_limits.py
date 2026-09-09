from django.conf import settings
from django.core.cache import cache
from redis.exceptions import RedisError
from rest_framework.exceptions import Throttled

from shared.upload_errors import UploadUnavailable


def _reserve(method, *args):
    take = getattr(cache, method, None)
    if take is None:
        raise UploadUnavailable()
    try:
        allowed, wait = take(*args)
    except (RedisError, OSError):
        raise UploadUnavailable() from None
    if not allowed:
        raise Throttled(wait=max(1, wait), detail="Upload limit reached. Please try again later.")


def reserve_request(user_id):
    if settings.UPLOAD_REQUESTS_PER_HOUR < 1:
        raise UploadUnavailable()
    _reserve("take_rate_slot", f"upload-request:{user_id}", settings.UPLOAD_REQUESTS_PER_HOUR, 3600)


def reserve_bytes(user_id, amount):
    if settings.UPLOAD_BYTES_PER_HOUR < 1:
        raise UploadUnavailable()
    if amount:
        _reserve("take_upload_bytes", f"upload-bytes:{user_id}", amount, settings.UPLOAD_BYTES_PER_HOUR, 3600)
