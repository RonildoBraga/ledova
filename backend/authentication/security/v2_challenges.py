import base64
import binascii
import hashlib
import hmac
import os
import re
import secrets
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from authentication.security.v2_access_tokens import (
    AccessTokenConfiguration,
    resolve_access_config,
)
from authentication.security.v2_credentials import V2KeyMaterial

INITIAL_CHALLENGE_PROOF_KID = "ledova-v2-challenge-proof-hmac-sha256-1"
INITIAL_CHALLENGE_RATE_KID = "ledova-v2-challenge-rate-hmac-sha256-1"

_PENDING_CONTEXT_PREFIX = "lpv2."
_PASSWORD_RESET_PREFIX = "lpw2."
_CREDENTIAL_ENCODED_LENGTH = 64
_CREDENTIAL_DECODED_LENGTH = 48
_SECRET_LENGTH = 32
_DIGEST_LENGTH = hashlib.sha256().digest_size
_MAX_DESTINATION_LENGTH = 254
_OTP_LIMIT = 1_000_000
_KID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
_UNPADDED_BASE64URL_PATTERN = re.compile(r"[A-Za-z0-9_-]+\Z")
_PADDED_BASE64URL_PATTERN = re.compile(r"[A-Za-z0-9_-]+={0,2}\Z")
_OTP_PATTERN = re.compile(r"[0-9]{6}\Z")
_OTP_PURPOSES = frozenset({"signup", "email_change"})
_PASSWORD_RESET_PURPOSE = "password_reset"
_CONFIGURATION_ERROR = "Invalid v2 challenge key configuration."
_CREDENTIAL_ERROR = "Invalid v2 challenge credential."
_MATERIAL_ERROR = "Invalid v2 challenge digest material."
_OTP_ERROR = "Invalid v2 challenge OTP generator."
_PENDING_CONTEXT_DOMAIN = b"ledova:v2:challenge:pending-context"
_OTP_DOMAIN = b"ledova:v2:challenge:otp"
_PASSWORD_RESET_DOMAIN = b"ledova:v2:challenge:password-reset"
_DESTINATION_RATE_DOMAIN = b"ledova:v2:challenge:destination-rate"
_IP_RATE_DOMAIN = b"ledova:v2:challenge:ip-rate"


class ChallengeKeyConfigurationError(ImproperlyConfigured):
    pass


class ChallengeCredentialError(ValueError):
    pass


class ChallengeMaterialError(ValueError):
    pass


@dataclass(frozen=True, repr=False)
class V2ChallengeCredentialParts:
    selector: uuid.UUID
    secret: bytes

    def __repr__(self):
        return "V2ChallengeCredentialParts(selector=<redacted>, secret=<redacted>)"


@dataclass(frozen=True, repr=False)
class ChallengeDigest:
    key_id: str
    digest: bytes

    def __post_init__(self):
        if not _valid_kid(self.key_id) or not isinstance(self.digest, bytes) or len(self.digest) != _DIGEST_LENGTH:
            raise ChallengeMaterialError(_MATERIAL_ERROR)

    def __repr__(self):
        return "ChallengeDigest(key_id=<redacted>, digest=<redacted>)"


@dataclass(frozen=True, repr=False)
class ChallengeRateDigests:
    current: ChallengeDigest
    aliases: tuple

    def __post_init__(self):
        if (
            not isinstance(self.current, ChallengeDigest)
            or not isinstance(self.aliases, tuple)
            or not self.aliases
            or any(not isinstance(alias, ChallengeDigest) for alias in self.aliases)
            or sum(alias == self.current for alias in self.aliases) != 1
        ):
            raise ChallengeMaterialError(_MATERIAL_ERROR)

    def __repr__(self):
        return "ChallengeRateDigests(current=<redacted>, aliases=<redacted>)"


@dataclass(frozen=True, repr=False, init=False)
class ChallengeKeyConfiguration:
    current_proof_kid: str
    proof_key: bytes
    proof_keys: Mapping
    current_rate_kid: str
    rate_key: bytes
    rate_keys: Mapping

    def __init__(self, *_args, **_kwargs):
        raise ChallengeKeyConfigurationError(_CONFIGURATION_ERROR)

    @classmethod
    def _create(
        cls,
        *,
        current_proof_kid,
        proof_key,
        proof_keys,
        current_rate_kid,
        rate_key,
        rate_keys,
        forbidden_keys,
    ):
        proof_keys = _validated_key_map(proof_keys)
        rate_keys = _validated_key_map(rate_keys)
        if proof_keys.keys() & rate_keys.keys():
            raise ChallengeKeyConfigurationError(_CONFIGURATION_ERROR)
        if not _valid_kid(current_proof_kid) or not _valid_kid(current_rate_kid):
            raise ChallengeKeyConfigurationError(_CONFIGURATION_ERROR)
        if not _valid_key(proof_key) or not _valid_key(rate_key):
            raise ChallengeKeyConfigurationError(_CONFIGURATION_ERROR)
        selected_proof_key = proof_keys.get(current_proof_kid)
        selected_rate_key = rate_keys.get(current_rate_kid)
        if (
            selected_proof_key is None
            or selected_rate_key is None
            or not hmac.compare_digest(selected_proof_key, proof_key)
            or not hmac.compare_digest(selected_rate_key, rate_key)
        ):
            raise ChallengeKeyConfigurationError(_CONFIGURATION_ERROR)

        challenge_keys = tuple(proof_keys.values()) + tuple(rate_keys.values())
        _reject_key_form_collisions(challenge_keys)
        try:
            forbidden_keys = tuple(forbidden_keys)
        except Exception:
            raise ChallengeKeyConfigurationError(_CONFIGURATION_ERROR) from None
        if any(not isinstance(key, bytes) for key in forbidden_keys):
            raise ChallengeKeyConfigurationError(_CONFIGURATION_ERROR)
        forbidden_forms = tuple(_key_forms(key) for key in forbidden_keys)
        for challenge_key in challenge_keys:
            challenge_forms = _key_forms(challenge_key)
            if any(_forms_overlap(challenge_forms, forms) for forms in forbidden_forms):
                raise ChallengeKeyConfigurationError(_CONFIGURATION_ERROR)

        instance = object.__new__(cls)
        object.__setattr__(instance, "current_proof_kid", current_proof_kid)
        object.__setattr__(instance, "proof_key", proof_key)
        object.__setattr__(instance, "proof_keys", MappingProxyType(proof_keys))
        object.__setattr__(instance, "current_rate_kid", current_rate_kid)
        object.__setattr__(instance, "rate_key", rate_key)
        object.__setattr__(instance, "rate_keys", MappingProxyType(rate_keys))
        return instance

    def __repr__(self):
        return (
            "ChallengeKeyConfiguration(current_proof_kid=<redacted>, proof_key=<redacted>, "
            "proof_keys=<redacted>, current_rate_kid=<redacted>, rate_key=<redacted>, "
            "rate_keys=<redacted>)"
        )


def _valid_kid(value):
    return isinstance(value, str) and _KID_PATTERN.fullmatch(value) is not None


def _valid_key(value):
    return isinstance(value, bytes) and len(value) >= 32


def _key_forms(key):
    padded = base64.urlsafe_b64encode(key)
    return tuple(dict.fromkeys((key, padded, padded.rstrip(b"="))))


def _forms_overlap(left, right):
    return any(hmac.compare_digest(left_value, right_value) for left_value in left for right_value in right)


def _reject_key_form_collisions(keys):
    forms = tuple(_key_forms(key) for key in keys)
    if any(_forms_overlap(value, other) for index, value in enumerate(forms) for other in forms[index + 1 :]):
        raise ChallengeKeyConfigurationError(_CONFIGURATION_ERROR)


def _validated_key_map(value):
    if not isinstance(value, Mapping):
        raise ChallengeKeyConfigurationError(_CONFIGURATION_ERROR)
    try:
        copied = dict(value)
    except Exception:
        raise ChallengeKeyConfigurationError(_CONFIGURATION_ERROR) from None
    if not copied or any(not _valid_kid(key_id) or not _valid_key(key) for key_id, key in copied.items()):
        raise ChallengeKeyConfigurationError(_CONFIGURATION_ERROR)
    return copied


def _decode_key(value):
    if not isinstance(value, str) or _PADDED_BASE64URL_PATTERN.fullmatch(value) is None:
        raise ChallengeKeyConfigurationError(_CONFIGURATION_ERROR)
    try:
        encoded = value.encode("ascii")
        decoded = base64.b64decode(encoded, altchars=b"-_", validate=True)
    except (UnicodeEncodeError, binascii.Error, ValueError):
        raise ChallengeKeyConfigurationError(_CONFIGURATION_ERROR) from None
    if base64.urlsafe_b64encode(decoded).decode("ascii") != value or not _valid_key(decoded):
        raise ChallengeKeyConfigurationError(_CONFIGURATION_ERROR)
    return decoded


def _validated_refresh_keys(value, current_key):
    if value is None:
        keys = (current_key,)
    else:
        try:
            keys = tuple(value.values()) if isinstance(value, Mapping) else tuple(value)
        except Exception:
            raise ChallengeKeyConfigurationError(_CONFIGURATION_ERROR) from None
    if not keys or any(not _valid_key(key) for key in keys):
        raise ChallengeKeyConfigurationError(_CONFIGURATION_ERROR)
    if not any(hmac.compare_digest(key, current_key) for key in keys):
        raise ChallengeKeyConfigurationError(_CONFIGURATION_ERROR)
    _reject_key_form_collisions(keys)
    return keys


def resolve_challenge_config(
    key_material,
    access_configuration,
    *,
    proof_key,
    rate_key,
    current_proof_kid=INITIAL_CHALLENGE_PROOF_KID,
    proof_keys=None,
    current_rate_kid=INITIAL_CHALLENGE_RATE_KID,
    rate_keys=None,
    accepted_refresh_keys=None,
):
    try:
        if not isinstance(key_material, V2KeyMaterial) or not isinstance(
            access_configuration, AccessTokenConfiguration
        ):
            raise ChallengeKeyConfigurationError(_CONFIGURATION_ERROR)
        material = V2KeyMaterial(
            access_signing_key=key_material.access_signing_key,
            refresh_hmac_key=key_material.refresh_hmac_key,
        )
        access_config = resolve_access_config(
            material,
            current_kid=access_configuration.current_kid,
            verifier_keys=access_configuration.verifier_keys,
        )
        secret_key = settings.SECRET_KEY.encode("utf-8")
        accepted_proof_keys = {current_proof_kid: proof_key} if proof_keys is None else proof_keys
        accepted_rate_keys = {current_rate_kid: rate_key} if rate_keys is None else rate_keys
        refresh_keys = _validated_refresh_keys(accepted_refresh_keys, material.refresh_hmac_key)
        forbidden_keys = tuple(access_config.verifier_keys.values()) + refresh_keys + (secret_key,)
        return ChallengeKeyConfiguration._create(
            current_proof_kid=current_proof_kid,
            proof_key=proof_key,
            proof_keys=accepted_proof_keys,
            current_rate_kid=current_rate_kid,
            rate_key=rate_key,
            rate_keys=accepted_rate_keys,
            forbidden_keys=forbidden_keys,
        )
    except ChallengeKeyConfigurationError:
        raise
    except Exception:
        raise ChallengeKeyConfigurationError(_CONFIGURATION_ERROR) from None


def load_challenge_config(key_material, access_configuration, *, accepted_refresh_keys=None):
    proof_key = _decode_key(os.environ.get("V2_CHALLENGE_PROOF_HMAC_KEY_B64"))
    rate_key = _decode_key(os.environ.get("V2_CHALLENGE_RATE_HMAC_KEY_B64"))
    return resolve_challenge_config(
        key_material,
        access_configuration,
        proof_key=proof_key,
        rate_key=rate_key,
        accepted_refresh_keys=accepted_refresh_keys,
    )


def _validated_configuration(configuration):
    if not isinstance(configuration, ChallengeKeyConfiguration):
        raise ChallengeKeyConfigurationError(_CONFIGURATION_ERROR)
    return ChallengeKeyConfiguration._create(
        current_proof_kid=configuration.current_proof_kid,
        proof_key=configuration.proof_key,
        proof_keys=configuration.proof_keys,
        current_rate_kid=configuration.current_rate_kid,
        rate_key=configuration.rate_key,
        rate_keys=configuration.rate_keys,
        forbidden_keys=(),
    )


def _uuid4_bytes(value, error_type, error_message):
    if not isinstance(value, uuid.UUID) or value.version != 4 or value.variant != uuid.RFC_4122:
        raise error_type(error_message)
    return value.bytes


def _secret_bytes(value, error_type, error_message):
    if not isinstance(value, bytes) or len(value) != _SECRET_LENGTH:
        raise error_type(error_message)
    return value


def _encode_unpadded(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _encode_credential(prefix, selector, secret):
    selector_bytes = _uuid4_bytes(selector, ChallengeCredentialError, _CREDENTIAL_ERROR)
    secret_bytes = _secret_bytes(secret, ChallengeCredentialError, _CREDENTIAL_ERROR)
    return prefix + _encode_unpadded(selector_bytes + secret_bytes)


def _decode_credential(value, prefix):
    if (
        not isinstance(value, str)
        or len(value) != len(prefix) + _CREDENTIAL_ENCODED_LENGTH
        or not value.startswith(prefix)
    ):
        raise ChallengeCredentialError(_CREDENTIAL_ERROR)
    encoded = value[len(prefix) :]
    if len(encoded) != _CREDENTIAL_ENCODED_LENGTH or _UNPADDED_BASE64URL_PATTERN.fullmatch(encoded) is None:
        raise ChallengeCredentialError(_CREDENTIAL_ERROR)
    try:
        padded = encoded + "=" * (-len(encoded) % 4)
        decoded = base64.b64decode(padded.encode("ascii"), altchars=b"-_", validate=True)
    except (UnicodeEncodeError, binascii.Error, ValueError):
        raise ChallengeCredentialError(_CREDENTIAL_ERROR) from None
    if len(decoded) != _CREDENTIAL_DECODED_LENGTH or _encode_unpadded(decoded) != encoded:
        raise ChallengeCredentialError(_CREDENTIAL_ERROR)
    selector = uuid.UUID(bytes=decoded[:16])
    if selector.version != 4 or selector.variant != uuid.RFC_4122:
        raise ChallengeCredentialError(_CREDENTIAL_ERROR)
    return V2ChallengeCredentialParts(selector=selector, secret=decoded[16:])


def encode_v2_pending_context(selector, secret):
    return _encode_credential(_PENDING_CONTEXT_PREFIX, selector, secret)


def decode_v2_pending_context(value):
    return _decode_credential(value, _PENDING_CONTEXT_PREFIX)


def encode_v2_password_reset_credential(selector, secret):
    return _encode_credential(_PASSWORD_RESET_PREFIX, selector, secret)


def decode_v2_password_reset_credential(value):
    return _decode_credential(value, _PASSWORD_RESET_PREFIX)


def generate_v2_otp(*, randbelow=secrets.randbelow):
    try:
        value = randbelow(_OTP_LIMIT)
    except Exception:
        raise ChallengeMaterialError(_OTP_ERROR) from None
    if type(value) is not int or value < 0 or value >= _OTP_LIMIT:
        raise ChallengeMaterialError(_OTP_ERROR)
    return f"{value:06d}"


def _purpose_bytes(value):
    if not isinstance(value, str) or value not in _OTP_PURPOSES:
        raise ChallengeMaterialError(_MATERIAL_ERROR)
    return value.encode("ascii")


def _destination_bytes(value):
    if not isinstance(value, str) or len(value) > _MAX_DESTINATION_LENGTH or not value.isascii():
        raise ChallengeMaterialError(_MATERIAL_ERROR)
    encoded = value.encode("ascii")
    if (
        not encoded
        or any(byte < 0x20 or byte > 0x7E for byte in encoded)
        or value != value.strip(" ")
        or value != value.lower()
    ):
        raise ChallengeMaterialError(_MATERIAL_ERROR)
    return encoded


def _otp_bytes(value):
    if not isinstance(value, str) or _OTP_PATTERN.fullmatch(value) is None:
        raise ChallengeMaterialError(_MATERIAL_ERROR)
    return value.encode("ascii")


def _digest_key(value):
    if not _valid_key(value):
        raise ChallengeMaterialError(_MATERIAL_ERROR)
    return value


def _frame(value):
    if not isinstance(value, bytes) or len(value) > 0xFFFFFFFF:
        raise ChallengeMaterialError(_MATERIAL_ERROR)
    return len(value).to_bytes(4, "big") + value


def _digest(key, domain, *fields):
    key = _digest_key(key)
    message = b"".join(_frame(value) for value in (domain, *fields))
    return hmac.new(key, message, hashlib.sha256).digest()


def _pending_digest(key, purpose, challenge_id, destination_key, secret):
    return _digest(
        key,
        _PENDING_CONTEXT_DOMAIN,
        _purpose_bytes(purpose),
        _uuid4_bytes(challenge_id, ChallengeMaterialError, _MATERIAL_ERROR),
        _destination_bytes(destination_key),
        _secret_bytes(secret, ChallengeMaterialError, _MATERIAL_ERROR),
    )


def _otp_digest(key, purpose, challenge_id, delivery_id, destination_key, otp):
    return _digest(
        key,
        _OTP_DOMAIN,
        _purpose_bytes(purpose),
        _uuid4_bytes(challenge_id, ChallengeMaterialError, _MATERIAL_ERROR),
        _uuid4_bytes(delivery_id, ChallengeMaterialError, _MATERIAL_ERROR),
        _destination_bytes(destination_key),
        _otp_bytes(otp),
    )


def _password_reset_digest(key, challenge_id, delivery_id, destination_key, secret):
    return _digest(
        key,
        _PASSWORD_RESET_DOMAIN,
        _uuid4_bytes(challenge_id, ChallengeMaterialError, _MATERIAL_ERROR),
        _uuid4_bytes(delivery_id, ChallengeMaterialError, _MATERIAL_ERROR),
        _destination_bytes(destination_key),
        _PASSWORD_RESET_PURPOSE.encode("ascii"),
        _secret_bytes(secret, ChallengeMaterialError, _MATERIAL_ERROR),
    )


def _proof_key(configuration, key_id):
    if not _valid_kid(key_id):
        raise ChallengeKeyConfigurationError(_CONFIGURATION_ERROR)
    key = configuration.proof_keys.get(key_id)
    if key is None:
        raise ChallengeKeyConfigurationError(_CONFIGURATION_ERROR)
    return key


def _stored_digest_matches(stored_digest, expected_digest):
    return (
        isinstance(stored_digest, bytes)
        and len(stored_digest) == _DIGEST_LENGTH
        and hmac.compare_digest(stored_digest, expected_digest)
    )


def pending_context_digest(*, purpose, challenge_id, destination_key, secret, configuration):
    config = _validated_configuration(configuration)
    digest = _pending_digest(config.proof_key, purpose, challenge_id, destination_key, secret)
    return ChallengeDigest(config.current_proof_kid, digest)


def pending_context_matches(
    stored_digest,
    stored_key_id,
    *,
    purpose,
    challenge_id,
    destination_key,
    secret,
    configuration,
):
    config = _validated_configuration(configuration)
    key = _proof_key(config, stored_key_id)
    expected = _pending_digest(key, purpose, challenge_id, destination_key, secret)
    return _stored_digest_matches(stored_digest, expected)


def otp_digest(*, purpose, challenge_id, delivery_id, destination_key, otp, configuration):
    config = _validated_configuration(configuration)
    digest = _otp_digest(config.proof_key, purpose, challenge_id, delivery_id, destination_key, otp)
    return ChallengeDigest(config.current_proof_kid, digest)


def otp_matches(
    stored_digest,
    stored_key_id,
    *,
    purpose,
    challenge_id,
    delivery_id,
    destination_key,
    otp,
    configuration,
):
    config = _validated_configuration(configuration)
    key = _proof_key(config, stored_key_id)
    expected = _otp_digest(key, purpose, challenge_id, delivery_id, destination_key, otp)
    return _stored_digest_matches(stored_digest, expected)


def password_reset_digest(*, challenge_id, delivery_id, destination_key, secret, configuration):
    config = _validated_configuration(configuration)
    digest = _password_reset_digest(config.proof_key, challenge_id, delivery_id, destination_key, secret)
    return ChallengeDigest(config.current_proof_kid, digest)


def password_reset_matches(
    stored_digest,
    stored_key_id,
    *,
    challenge_id,
    delivery_id,
    destination_key,
    secret,
    configuration,
):
    config = _validated_configuration(configuration)
    key = _proof_key(config, stored_key_id)
    expected = _password_reset_digest(key, challenge_id, delivery_id, destination_key, secret)
    return _stored_digest_matches(stored_digest, expected)


def _rate_digests(configuration, domain, fields):
    aliases = tuple(
        ChallengeDigest(key_id, _digest(key, domain, *fields))
        for key_id, key in sorted(configuration.rate_keys.items())
    )
    current = next(alias for alias in aliases if alias.key_id == configuration.current_rate_kid)
    return ChallengeRateDigests(current=current, aliases=aliases)


def destination_rate_digests(destination_key, *, configuration):
    config = _validated_configuration(configuration)
    return _rate_digests(config, _DESTINATION_RATE_DOMAIN, (_destination_bytes(destination_key),))


def _ip_rate_fields(address_family, prefix_length, packed_network):
    if type(address_family) is not int or type(prefix_length) is not int or not isinstance(packed_network, bytes):
        raise ChallengeMaterialError(_MATERIAL_ERROR)
    if (address_family, prefix_length) == (0, 0) and packed_network == b"":
        pass
    elif (address_family, prefix_length) == (4, 32) and len(packed_network) == 4:
        pass
    elif (address_family, prefix_length) == (6, 64) and len(packed_network) == 16 and packed_network[8:] == b"\x00" * 8:
        pass
    else:
        raise ChallengeMaterialError(_MATERIAL_ERROR)
    return bytes((address_family,)), bytes((prefix_length,)), packed_network


def ip_rate_digests(address_family, prefix_length, packed_network, *, configuration):
    config = _validated_configuration(configuration)
    return _rate_digests(
        config,
        _IP_RATE_DOMAIN,
        _ip_rate_fields(address_family, prefix_length, packed_network),
    )
