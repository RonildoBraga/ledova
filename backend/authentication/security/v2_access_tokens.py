import base64
import binascii
import hmac
import math
import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from datetime import timezone as datetime_timezone
from types import MappingProxyType

import jwt
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone

from authentication.security.v2_credentials import V2KeyMaterial

INITIAL_ACCESS_KID = "ledova-v2-access-hs256-1"

_ALGORITHM = "HS256"
_HEADER_TYPE = "at+jwt"
_TOKEN_TYPE = "access"
_TOKEN_VERSION = 2
_ISSUER = "urn:ledova:auth"
_AUDIENCE = "urn:ledova:api"
_MAX_LIFETIME = timedelta(seconds=900)
_MAX_TOKEN_BYTES = 1024
_MAX_USER_ID = (1 << 63) - 1
_KID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
_SUBJECT_PATTERN = re.compile(r"[1-9][0-9]*\Z")
_COMPACT_SEGMENT_PATTERN = re.compile(r"[A-Za-z0-9_-]+\Z")
_HEADER_KEYS = frozenset({"alg", "typ", "kid"})
_PAYLOAD_KEYS = frozenset({"typ", "ver", "sub", "sid", "jti", "iat", "exp", "iss", "aud"})
_CONFIGURATION_ERROR = "Invalid v2 access token configuration."
_TOKEN_ERROR = "Invalid v2 access token."


class AccessTokenConfigurationError(ImproperlyConfigured):
    pass


class AccessTokenError(ValueError):
    pass


@dataclass(frozen=True, repr=False, init=False)
class AccessTokenConfiguration:
    current_kid: str
    signing_key: bytes
    verifier_keys: Mapping[str, bytes]

    def __init__(self, *_args, **_kwargs):
        raise AccessTokenConfigurationError(_CONFIGURATION_ERROR)

    @classmethod
    def _create(cls, *, current_kid, signing_key, verifier_keys):
        if not _valid_kid(current_kid) or not _valid_key(signing_key):
            raise AccessTokenConfigurationError(_CONFIGURATION_ERROR)
        if not isinstance(verifier_keys, Mapping):
            raise AccessTokenConfigurationError(_CONFIGURATION_ERROR)

        verifier_keys = dict(verifier_keys)
        if not verifier_keys or any(not _valid_kid(kid) or not _valid_key(key) for kid, key in verifier_keys.items()):
            raise AccessTokenConfigurationError(_CONFIGURATION_ERROR)
        current_key = verifier_keys.get(current_kid)
        if current_key is None or not hmac.compare_digest(current_key, signing_key):
            raise AccessTokenConfigurationError(_CONFIGURATION_ERROR)

        keys = tuple(verifier_keys.values())
        if any(hmac.compare_digest(key, other) for index, key in enumerate(keys) for other in keys[index + 1 :]):
            raise AccessTokenConfigurationError(_CONFIGURATION_ERROR)
        instance = object.__new__(cls)
        object.__setattr__(instance, "current_kid", current_kid)
        object.__setattr__(instance, "signing_key", signing_key)
        object.__setattr__(instance, "verifier_keys", MappingProxyType(verifier_keys))
        return instance

    def __repr__(self):
        return "AccessTokenConfiguration(current_kid=<redacted>, signing_key=<redacted>, verifier_keys=<redacted>)"


@dataclass(frozen=True, repr=False)
class AccessTokenIssued:
    access_token: str
    access_expires_at: datetime

    def __repr__(self):
        return "AccessTokenIssued(access_token=<redacted>, access_expires_at=<redacted>)"


@dataclass(frozen=True, repr=False)
class AccessTokenClaims:
    user_id: int
    session_id: uuid.UUID
    token_id: uuid.UUID
    issued_at: datetime
    expires_at: datetime

    def __repr__(self):
        return (
            "AccessTokenClaims(user_id=<redacted>, session_id=<redacted>, token_id=<redacted>, "
            "issued_at=<redacted>, expires_at=<redacted>)"
        )


def _valid_kid(value):
    return isinstance(value, str) and _KID_PATTERN.fullmatch(value) is not None


def _valid_key(value):
    return isinstance(value, bytes) and len(value) >= 32


def _encoded_key_forms(key):
    padded = base64.urlsafe_b64encode(key)
    return padded, padded.rstrip(b"=")


def _aware_epoch(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise AccessTokenError(_TOKEN_ERROR)
    try:
        return math.floor(value.timestamp())
    except (OSError, OverflowError, ValueError):
        raise AccessTokenError(_TOKEN_ERROR) from None


def _validated_compact_segments(token):
    if not isinstance(token, str) or not token.isascii() or len(token.encode("ascii")) > _MAX_TOKEN_BYTES:
        raise AccessTokenError(_TOKEN_ERROR)
    segments = token.split(".")
    if len(segments) != 3:
        raise AccessTokenError(_TOKEN_ERROR)
    for segment in segments:
        if _COMPACT_SEGMENT_PATTERN.fullmatch(segment) is None:
            raise AccessTokenError(_TOKEN_ERROR)
        try:
            padded = segment + "=" * (-len(segment) % 4)
            decoded = base64.b64decode(padded.encode("ascii"), altchars=b"-_", validate=True)
        except (binascii.Error, UnicodeEncodeError, ValueError):
            raise AccessTokenError(_TOKEN_ERROR) from None
        if base64.urlsafe_b64encode(decoded).rstrip(b"=").decode("ascii") != segment:
            raise AccessTokenError(_TOKEN_ERROR)
    return segments


def _validated_configuration(configuration):
    if not isinstance(configuration, AccessTokenConfiguration):
        raise AccessTokenConfigurationError(_CONFIGURATION_ERROR)
    return AccessTokenConfiguration._create(
        current_kid=configuration.current_kid,
        signing_key=configuration.signing_key,
        verifier_keys=configuration.verifier_keys,
    )


def resolve_access_config(key_material, *, current_kid=INITIAL_ACCESS_KID, verifier_keys=None):
    if not isinstance(key_material, V2KeyMaterial):
        raise AccessTokenConfigurationError(_CONFIGURATION_ERROR)
    try:
        material = V2KeyMaterial(
            access_signing_key=key_material.access_signing_key,
            refresh_hmac_key=key_material.refresh_hmac_key,
        )
    except Exception:
        raise AccessTokenConfigurationError(_CONFIGURATION_ERROR) from None

    try:
        accepted_keys = {current_kid: material.access_signing_key} if verifier_keys is None else dict(verifier_keys)
    except (TypeError, ValueError):
        raise AccessTokenConfigurationError(_CONFIGURATION_ERROR) from None
    secret_key = settings.SECRET_KEY.encode("utf-8")
    for key in accepted_keys.values():
        if not _valid_key(key):
            raise AccessTokenConfigurationError(_CONFIGURATION_ERROR)
        textual_forms = _encoded_key_forms(key)
        if hmac.compare_digest(key, material.refresh_hmac_key) or hmac.compare_digest(key, secret_key):
            raise AccessTokenConfigurationError(_CONFIGURATION_ERROR)
        if any(hmac.compare_digest(form, secret_key) for form in textual_forms):
            raise AccessTokenConfigurationError(_CONFIGURATION_ERROR)

    return AccessTokenConfiguration._create(
        current_kid=current_kid,
        signing_key=material.access_signing_key,
        verifier_keys=accepted_keys,
    )


def resolve_access_expiry(at, session_expires_at, lifetime=_MAX_LIFETIME):
    issued_epoch = _aware_epoch(at)
    session_expiry_epoch = _aware_epoch(session_expires_at)
    if not isinstance(lifetime, timedelta) or lifetime < timedelta(seconds=1) or lifetime > _MAX_LIFETIME:
        raise AccessTokenError(_TOKEN_ERROR)
    try:
        access_expiry_epoch = min(math.floor((at + lifetime).timestamp()), session_expiry_epoch)
    except (OSError, OverflowError, ValueError):
        raise AccessTokenError(_TOKEN_ERROR) from None
    if access_expiry_epoch <= issued_epoch:
        return None
    return datetime.fromtimestamp(access_expiry_epoch, tz=datetime_timezone.utc)


def issue_access_token(
    user_id,
    session_id,
    *,
    issued_at,
    expires_at,
    session_expires_at,
    token_id,
    configuration,
):
    config = _validated_configuration(configuration)
    issued_epoch = _aware_epoch(issued_at)
    expires_epoch = _aware_epoch(expires_at)
    session_expires_epoch = _aware_epoch(session_expires_at)
    if type(user_id) is not int or user_id <= 0 or user_id > _MAX_USER_ID:
        raise AccessTokenError(_TOKEN_ERROR)
    if not isinstance(session_id, uuid.UUID):
        raise AccessTokenError(_TOKEN_ERROR)
    if not isinstance(token_id, uuid.UUID) or token_id.version != 4 or token_id.variant != uuid.RFC_4122:
        raise AccessTokenError(_TOKEN_ERROR)
    if (
        expires_epoch <= issued_epoch
        or expires_epoch > session_expires_epoch
        or expires_epoch - issued_epoch > int(_MAX_LIFETIME.total_seconds())
    ):
        raise AccessTokenError(_TOKEN_ERROR)

    payload = {
        "typ": _TOKEN_TYPE,
        "ver": _TOKEN_VERSION,
        "sub": str(user_id),
        "sid": str(session_id),
        "jti": str(token_id),
        "iat": issued_epoch,
        "exp": expires_epoch,
        "iss": _ISSUER,
        "aud": _AUDIENCE,
    }
    try:
        token = jwt.encode(
            payload,
            config.signing_key,
            algorithm=_ALGORITHM,
            headers={"typ": _HEADER_TYPE, "kid": config.current_kid},
        )
    except Exception:
        raise AccessTokenError(_TOKEN_ERROR) from None
    _validated_compact_segments(token)
    return AccessTokenIssued(
        access_token=token,
        access_expires_at=datetime.fromtimestamp(expires_epoch, tz=datetime_timezone.utc),
    )


def _canonical_uuid(value, *, version=None):
    if not isinstance(value, str):
        raise AccessTokenError(_TOKEN_ERROR)
    try:
        parsed = uuid.UUID(value)
    except (AttributeError, TypeError, ValueError):
        raise AccessTokenError(_TOKEN_ERROR) from None
    if str(parsed) != value:
        raise AccessTokenError(_TOKEN_ERROR)
    if version is not None and (parsed.version != version or parsed.variant != uuid.RFC_4122):
        raise AccessTokenError(_TOKEN_ERROR)
    return parsed


def verify_access_token(token, *, configuration, clock=timezone.now):
    config = _validated_configuration(configuration)
    try:
        _validated_compact_segments(token)

        header = jwt.get_unverified_header(token)
        if (
            not isinstance(header, dict)
            or frozenset(header) != _HEADER_KEYS
            or header.get("alg") != _ALGORITHM
            or header.get("typ") != _HEADER_TYPE
            or not isinstance(header.get("kid"), str)
        ):
            raise AccessTokenError(_TOKEN_ERROR)
        verification_key = config.verifier_keys.get(header["kid"])
        if verification_key is None:
            raise AccessTokenError(_TOKEN_ERROR)

        payload = jwt.decode(
            token,
            verification_key,
            algorithms=[_ALGORITHM],
            audience=_AUDIENCE,
            issuer=_ISSUER,
            leeway=0,
            options={
                "require": tuple(_PAYLOAD_KEYS),
                "strict_aud": True,
                "verify_iat": False,
                "verify_exp": False,
            },
        )
        if not isinstance(payload, dict) or frozenset(payload) != _PAYLOAD_KEYS:
            raise AccessTokenError(_TOKEN_ERROR)
        if payload["typ"] != _TOKEN_TYPE or type(payload["ver"]) is not int or payload["ver"] != _TOKEN_VERSION:
            raise AccessTokenError(_TOKEN_ERROR)
        if not isinstance(payload["sub"], str) or _SUBJECT_PATTERN.fullmatch(payload["sub"]) is None:
            raise AccessTokenError(_TOKEN_ERROR)
        user_id = int(payload["sub"])
        if user_id > _MAX_USER_ID:
            raise AccessTokenError(_TOKEN_ERROR)
        if type(payload["iat"]) is not int or type(payload["exp"]) is not int:
            raise AccessTokenError(_TOKEN_ERROR)
        if payload["iss"] != _ISSUER or payload["aud"] != _AUDIENCE:
            raise AccessTokenError(_TOKEN_ERROR)

        session_id = _canonical_uuid(payload["sid"])
        token_id = _canonical_uuid(payload["jti"], version=4)
        lifetime = payload["exp"] - payload["iat"]
        now_epoch = _aware_epoch(clock())
        if lifetime <= 0 or lifetime > int(_MAX_LIFETIME.total_seconds()):
            raise AccessTokenError(_TOKEN_ERROR)
        if payload["iat"] > now_epoch or payload["exp"] <= now_epoch:
            raise AccessTokenError(_TOKEN_ERROR)

        return AccessTokenClaims(
            user_id=user_id,
            session_id=session_id,
            token_id=token_id,
            issued_at=datetime.fromtimestamp(payload["iat"], tz=datetime_timezone.utc),
            expires_at=datetime.fromtimestamp(payload["exp"], tz=datetime_timezone.utc),
        )
    except AccessTokenError:
        raise
    except Exception:
        raise AccessTokenError(_TOKEN_ERROR) from None
