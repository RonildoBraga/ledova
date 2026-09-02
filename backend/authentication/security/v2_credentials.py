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
_CONFIRMATION_MATERIAL_ERROR = "Invalid v2 refresh confirmation material."
_CONFIRMATION_DIGEST_DOMAIN = b"ledova:v2:refresh-confirmation"
_REFRESH_TOKEN_ERROR = "Invalid v2 refresh token."
_CONFIRMATION_TOKEN_ERROR = "Invalid v2 confirmation token."
_REFRESH_TOKEN_PREFIX = "lrv2."
_CONFIRMATION_TOKEN_PREFIX = "lvc2."
_UNPADDED_BASE64URL_PATTERN = re.compile(r"[A-Za-z0-9_-]+\Z")


class V2KeyMaterialError(ImproperlyConfigured):
    pass


@dataclass(frozen=True, repr=False)
class V2KeyMaterial:
    access_signing_key: bytes
    refresh_hmac_key: bytes

    def __post_init__(self):
        keys = (self.access_signing_key, self.refresh_hmac_key)
        if any(not isinstance(key, bytes) or len(key) < 32 for key in keys):
            raise V2KeyMaterialError(_KEY_CONFIGURATION_ERROR)

        secret_key = settings.SECRET_KEY.encode("utf-8")
        padded_keys = tuple(base64.urlsafe_b64encode(key) for key in keys)
        textual_keys = padded_keys + tuple(key.rstrip(b"=") for key in padded_keys)
        if (
            hmac.compare_digest(keys[0], keys[1])
            or any(hmac.compare_digest(key, secret_key) for key in keys)
            or any(hmac.compare_digest(key, secret_key) for key in textual_keys)
        ):
            raise V2KeyMaterialError(_KEY_CONFIGURATION_ERROR)

    def __repr__(self):
        return "V2KeyMaterial(access_signing_key=<redacted>, refresh_hmac_key=<redacted>)"


@dataclass(frozen=True, repr=False)
class V2RefreshTokenParts:
    selector: uuid.UUID
    secret: bytes

    def __repr__(self):
        return "V2RefreshTokenParts(selector=<redacted>, secret=<redacted>)"


@dataclass(frozen=True, repr=False)
class V2ConfirmationTokenParts:
    nonce: bytes

    def __repr__(self):
        return "V2ConfirmationTokenParts(nonce=<redacted>)"


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


def _identifier_bytes(value, error_message):
    try:
        return value.bytes if isinstance(value, uuid.UUID) else uuid.UUID(str(value)).bytes
    except (AttributeError, TypeError, ValueError):
        raise ValueError(error_message) from None


def _encode_unpadded(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode_unpadded(value, *, prefix, encoded_length, decoded_length, error_message):
    if not isinstance(value, str) or not value.startswith(prefix):
        raise ValueError(error_message)

    encoded = value[len(prefix) :]
    if len(encoded) != encoded_length or not _UNPADDED_BASE64URL_PATTERN.fullmatch(encoded):
        raise ValueError(error_message)

    try:
        padded = encoded + "=" * (-len(encoded) % 4)
        decoded = base64.b64decode(padded.encode("ascii"), altchars=b"-_", validate=True)
    except (UnicodeEncodeError, binascii.Error, ValueError):
        raise ValueError(error_message) from None

    if len(decoded) != decoded_length or _encode_unpadded(decoded) != encoded:
        raise ValueError(error_message)
    return decoded


def encode_v2_refresh_token(selector, secret):
    try:
        secret_bytes = _refresh_bytes(secret)
    except ValueError:
        raise ValueError(_REFRESH_TOKEN_ERROR) from None
    if len(secret_bytes) != 32:
        raise ValueError(_REFRESH_TOKEN_ERROR)
    selector_bytes = _identifier_bytes(selector, _REFRESH_TOKEN_ERROR)
    return _REFRESH_TOKEN_PREFIX + _encode_unpadded(selector_bytes + secret_bytes)


def decode_v2_refresh_token(value):
    decoded = _decode_unpadded(
        value,
        prefix=_REFRESH_TOKEN_PREFIX,
        encoded_length=64,
        decoded_length=48,
        error_message=_REFRESH_TOKEN_ERROR,
    )
    return V2RefreshTokenParts(selector=uuid.UUID(bytes=decoded[:16]), secret=decoded[16:])


def encode_v2_confirmation_token(nonce):
    try:
        nonce_bytes = _refresh_bytes(nonce)
    except ValueError:
        raise ValueError(_CONFIRMATION_TOKEN_ERROR) from None
    if len(nonce_bytes) != 32:
        raise ValueError(_CONFIRMATION_TOKEN_ERROR)
    return _CONFIRMATION_TOKEN_PREFIX + _encode_unpadded(nonce_bytes)


def decode_v2_confirmation_token(value):
    decoded = _decode_unpadded(
        value,
        prefix=_CONFIRMATION_TOKEN_PREFIX,
        encoded_length=43,
        decoded_length=32,
        error_message=_CONFIRMATION_TOKEN_ERROR,
    )
    return V2ConfirmationTokenParts(nonce=decoded)


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


def refresh_confirmation_digest(session_id, predecessor_id, nonce, key):
    nonce_bytes = _refresh_bytes(nonce)
    key_bytes = _refresh_bytes(key)
    if len(nonce_bytes) != 32 or len(key_bytes) < 32:
        raise ValueError(_CONFIRMATION_MATERIAL_ERROR)

    message = b"\x00".join(
        (
            _CONFIRMATION_DIGEST_DOMAIN,
            _identifier_bytes(session_id, _CONFIRMATION_MATERIAL_ERROR),
            _identifier_bytes(predecessor_id, _CONFIRMATION_MATERIAL_ERROR),
            nonce_bytes,
        )
    )
    return hmac.new(key_bytes, message, hashlib.sha256).digest()


def refresh_confirmation_matches(stored_digest, session_id, predecessor_id, nonce, key):
    digest_bytes = _refresh_bytes(stored_digest)
    if len(digest_bytes) != hashlib.sha256().digest_size:
        return False
    expected_digest = refresh_confirmation_digest(session_id, predecessor_id, nonce, key)
    return hmac.compare_digest(digest_bytes, expected_digest)
