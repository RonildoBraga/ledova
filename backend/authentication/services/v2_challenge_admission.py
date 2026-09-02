import uuid
from datetime import datetime, timedelta
from functools import reduce
from operator import or_

from django.db import DEFAULT_DB_ALIAS, transaction
from django.db.models import Q

from authentication.models import AuthenticationChallengeDelivery
from authentication.security import (
    ChallengeDigest,
    ChallengeKeyConfiguration,
    ChallengeRateDigests,
    V2TrustedProxyConfiguration,
    destination_rate_digests,
    request_ip_rate_digests,
)
from authentication.services.v2_query_privacy import _require_unrecorded_v2_connection

_ADMISSION_ERROR = "V2 challenge service unavailable."
_ALLOWED_PURPOSES = frozenset(
    {
        AuthenticationChallengeDelivery.Purpose.SIGNUP,
        AuthenticationChallengeDelivery.Purpose.EMAIL_CHANGE,
    }
)
_IP_LIMIT = 20
_RATE_WINDOW = timedelta(seconds=3600)
_DELIVERY_LEASE = timedelta(seconds=120)
_DUMMY_DESTINATION_KEY = "unknown-context@invalid.example"


class V2ChallengeAdmissionError(RuntimeError):
    pass


def _raise_admission_error():
    raise V2ChallengeAdmissionError(_ADMISSION_ERROR) from None


def _validated_ip_aliases(ip_rates, configuration):
    aliases = None
    try:
        if not isinstance(ip_rates, ChallengeRateDigests) or not isinstance(configuration, ChallengeKeyConfiguration):
            raise TypeError
        candidate_aliases = ip_rates.aliases
        expected_ids = tuple(sorted(configuration.rate_keys))
        candidate_ids = tuple(alias.key_id for alias in candidate_aliases)
        current_alias = next(alias for alias in candidate_aliases if alias.key_id == configuration.current_rate_kid)
        valid = (
            isinstance(candidate_aliases, tuple)
            and all(isinstance(alias, ChallengeDigest) for alias in candidate_aliases)
            and candidate_ids == expected_ids
            and len(set(candidate_ids)) == len(candidate_ids)
            and ip_rates.current == current_alias
            and ip_rates.current.key_id == configuration.current_rate_kid
        )
        if valid:
            aliases = candidate_aliases
    except Exception:
        aliases = None

    if aliases is None:
        _raise_admission_error()

    return aliases


def _advisory_lock_ids(aliases):
    lock_ids = None
    try:
        values = tuple(int.from_bytes(alias.digest[:8], "big", signed=True) for alias in aliases)
        if values and all(len(alias.digest) == 32 for alias in aliases):
            lock_ids = tuple(sorted(set(values)))
    except Exception:
        lock_ids = None

    if lock_ids is None:
        _raise_admission_error()

    return lock_ids


def _database_clock(cursor):
    cursor.execute("SELECT clock_timestamp()")
    row = cursor.fetchone()
    if not isinstance(row, tuple) or len(row) != 1:
        _raise_admission_error()
    return row[0]


def _record_unknown_context_ip_suppression(
    *,
    purpose,
    ip_rates,
    challenge_configuration,
    using,
    post_lock_clock,
):
    if not isinstance(purpose, str) or purpose not in _ALLOWED_PURPOSES or not callable(post_lock_clock):
        _raise_admission_error()
    aliases = _validated_ip_aliases(ip_rates, challenge_configuration)
    selected = _require_unrecorded_v2_connection(using=using)
    if selected.vendor != "postgresql":
        _raise_admission_error()
    safe_entry_state = False
    try:
        safe_entry_state = selected.in_atomic_block is False and selected.get_autocommit() is True
    except Exception:
        safe_entry_state = False
    if not safe_entry_state:
        _raise_admission_error()

    lock_ids = _advisory_lock_ids(aliases)
    identity_filter = reduce(
        or_,
        (Q(rate_key_id=alias.key_id, ip_rate_digest=alias.digest) for alias in aliases),
    )

    with transaction.atomic(using=selected.alias, durable=True):
        with selected.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED, NOT DEFERRABLE")
            for lock_id in lock_ids:
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", [lock_id])
            at = post_lock_clock(cursor)

        if not isinstance(at, datetime) or at.tzinfo is None:
            _raise_admission_error()

        deliveries = AuthenticationChallengeDelivery.objects.using(selected.alias)
        admitted_count = deliveries.filter(
            identity_filter,
            reserved_at__gt=at - _RATE_WINDOW,
        ).count()
        if admitted_count >= _IP_LIMIT:
            return None

        deliveries.create(
            uuid=uuid.uuid4(),
            challenge=None,
            purpose=purpose,
            status=AuthenticationChallengeDelivery.Status.SUPPRESSED,
            rate_key_id=ip_rates.current.key_id,
            destination_rate_digest=None,
            ip_rate_digest=ip_rates.current.digest,
            proof_key_id=None,
            proof_digest=None,
            reserved_at=at,
            lease_expires_at=at + _DELIVERY_LEASE,
            sending_at=None,
            accepted_at=None,
            proof_expires_at=None,
            resolved_at=at,
        )
    return None


def _record_unknown_context_request_ip_suppression(
    *,
    purpose,
    request,
    trusted_proxy_configuration: V2TrustedProxyConfiguration,
    challenge_configuration: ChallengeKeyConfiguration,
    using: str = DEFAULT_DB_ALIAS,
) -> None:
    failed = False
    try:
        if not isinstance(purpose, str) or purpose not in _ALLOWED_PURPOSES:
            raise ValueError
        destination_rate_digests(
            _DUMMY_DESTINATION_KEY,
            configuration=challenge_configuration,
        )
        ip_rates = request_ip_rate_digests(
            request,
            trusted_proxy_configuration=trusted_proxy_configuration,
            challenge_configuration=challenge_configuration,
        )
        _record_unknown_context_ip_suppression(
            purpose=purpose,
            ip_rates=ip_rates,
            challenge_configuration=challenge_configuration,
            using=using,
            post_lock_clock=_database_clock,
        )
    except Exception:
        failed = True

    if failed:
        _raise_admission_error()
    return None


def record_unknown_signup_context_ip_suppression(
    *,
    request,
    trusted_proxy_configuration: V2TrustedProxyConfiguration,
    challenge_configuration: ChallengeKeyConfiguration,
    using: str = DEFAULT_DB_ALIAS,
) -> None:
    return _record_unknown_context_request_ip_suppression(
        purpose=AuthenticationChallengeDelivery.Purpose.SIGNUP,
        request=request,
        trusted_proxy_configuration=trusted_proxy_configuration,
        challenge_configuration=challenge_configuration,
        using=using,
    )


def record_unknown_email_change_context_ip_suppression(
    *,
    request,
    trusted_proxy_configuration: V2TrustedProxyConfiguration,
    challenge_configuration: ChallengeKeyConfiguration,
    using: str = DEFAULT_DB_ALIAS,
) -> None:
    return _record_unknown_context_request_ip_suppression(
        purpose=AuthenticationChallengeDelivery.Purpose.EMAIL_CHANGE,
        request=request,
        trusted_proxy_configuration=trusted_proxy_configuration,
        challenge_configuration=challenge_configuration,
        using=using,
    )
