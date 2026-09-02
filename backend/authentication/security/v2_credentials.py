import base64
import binascii
import hashlib
import hmac
import os
import re
import uuid
from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

_BASE64URL_PATTERN = re.compile(r"[A-Za-z0-9_-]+={0,2}\Z")
_KEY_CONFIGURATION_ERROR = "Invalid v2 authentication key configuration."
_REFRESH_MATERIAL_ERROR = "Invalid v2 refresh credential material."
_REFRESH_DIGEST_DOMAIN = b"ledova:v2:refresh"


class V2KeyMaterialError(ImproperlyConfigured):
    pass


@dataclass(frozen=True, repr=False)
class V2KeyMaterial:
    access_signing_key: bytes
    refresh_hmac_key: bytes

    def __repr__(self):
        return "V2KeyMaterial(access_signing_key=<redacted>, refresh_hmac_key=<redacted>)"


def _decode_key(value):
    if not isinstance(value, str) or not _BASE64URL_PATTERN.fullmatch(value):
        raise V2KeyMaterialError(_KEY_CONFIGURATION_ERROR)

    try:
        encoded = value.encode("ascii")
        decoded = base64.b64decode(encoded, altchars=b"-_", validate=True)
    except (UnicodeEncodeError, binascii.Error, ValueError):
        raise V2KeyMaterialError(_KEY_CONFIGURATION_ERROR) from None

    if base64.urlsafe_b64encode(decoded).decode("ascii") != value or len(decoded) < 32:
        raise V2KeyMaterialError(_KEY_CONFIGURATION_ERROR)

    return decoded


def load_v2_key_material():
    access_signing_value = os.environ.get("V2_ACCESS_SIGNING_KEY_B64")
    refresh_hmac_value = os.environ.get("V2_REFRESH_HMAC_KEY_B64")
    access_signing_key = _decode_key(access_signing_value)
    refresh_hmac_key = _decode_key(refresh_hmac_value)
    secret_key = settings.SECRET_KEY.encode("utf-8")

    invalid_separation = (
        hmac.compare_digest(access_signing_key, refresh_hmac_key)
        or hmac.compare_digest(access_signing_key, secret_key)
        or hmac.compare_digest(refresh_hmac_key, secret_key)
        or hmac.compare_digest(access_signing_value.encode("ascii"), secret_key)
        or hmac.compare_digest(refresh_hmac_value.encode("ascii"), secret_key)
    )
    if invalid_separation:
        raise V2KeyMaterialError(_KEY_CONFIGURATION_ERROR)

    return V2KeyMaterial(
        access_signing_key=access_signing_key,
        refresh_hmac_key=refresh_hmac_key,
    )


def _refresh_bytes(value):
    if not isinstance(value, (bytes, bytearray, memoryview)):
        raise ValueError(_REFRESH_MATERIAL_ERROR)
    return bytes(value)


def _selector_bytes(selector):
    try:
        return selector.bytes if isinstance(selector, uuid.UUID) else uuid.UUID(str(selector)).bytes
    except (AttributeError, TypeError, ValueError):
        raise ValueError(_REFRESH_MATERIAL_ERROR) from None


def refresh_secret_digest(selector, secret, key):
    secret_bytes = _refresh_bytes(secret)
    key_bytes = _refresh_bytes(key)
    if len(secret_bytes) != 32 or len(key_bytes) < 32:
        raise ValueError(_REFRESH_MATERIAL_ERROR)

    message = _REFRESH_DIGEST_DOMAIN + b"\x00" + _selector_bytes(selector) + b"\x00" + secret_bytes
    return hmac.new(key_bytes, message, hashlib.sha256).digest()


def refresh_secret_matches(stored_digest, selector, secret, key):
    digest_bytes = _refresh_bytes(stored_digest)
    if len(digest_bytes) != hashlib.sha256().digest_size:
        return False
    expected_digest = refresh_secret_digest(selector, secret, key)
    return hmac.compare_digest(digest_bytes, expected_digest)
