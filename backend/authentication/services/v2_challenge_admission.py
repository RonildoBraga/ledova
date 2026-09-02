import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from functools import reduce
from operator import or_

from django.db import DEFAULT_DB_ALIAS, transaction
from django.db.models import Q

from authentication.models import (
    AuthenticationChallenge,
    AuthenticationChallengeDelivery,
)
from authentication.security import (
    ChallengeDigest,
    ChallengeKeyConfiguration,
    ChallengeRateDigests,
    V2TrustedProxyConfiguration,
    destination_rate_digests,
    request_ip_rate_digests,
)
from authentication.services.v2_delivery_queue import (
    _enqueue_reserved_v2_delivery,
    _validate_v2_delivery_queue,
)
from authentication.services.v2_query_privacy import _require_unrecorded_v2_connection

_ADMISSION_ERROR = "V2 challenge service unavailable."
_ALL_PURPOSES = frozenset(
    {
        AuthenticationChallengeDelivery.Purpose.SIGNUP,
        AuthenticationChallengeDelivery.Purpose.EMAIL_CHANGE,
        AuthenticationChallengeDelivery.Purpose.PASSWORD_RESET,
    }
)
_UNKNOWN_CONTEXT_PURPOSES = frozenset(
    {
        AuthenticationChallengeDelivery.Purpose.SIGNUP,
        AuthenticationChallengeDelivery.Purpose.EMAIL_CHANGE,
    }
)
_DESTINATION_LIMIT = 5
_PASSWORD_RESET_LIMIT = 3
_IP_LIMIT = 20
_RATE_WINDOW = timedelta(seconds=3600)
_DELIVERY_LEASE = timedelta(seconds=120)
_DUMMY_DESTINATION_KEY = "unknown-context@invalid.example"


class V2ChallengeAdmissionError(RuntimeError):
    pass


class _V2ChallengeAdmissionDecision(Enum):
    ADMITTED = "admitted"
    REFUSED = "refused"


@dataclass(frozen=True, slots=True, repr=False)
class _V2ChallengeAdmissionContext:
    using: str
    purpose: str
    delivery_id: uuid.UUID
    reserved_at: datetime
    lease_expires_at: datetime
    rate_key_id: str
    destination_rate_digest: bytes | None
    ip_rate_digest: bytes

    def __repr__(self):
        return "_V2ChallengeAdmissionContext(<redacted>)"

    __str__ = __repr__


@dataclass(frozen=True, slots=True, repr=False)
class _V2ChallengeAdmissionPlan:
    status: str
    challenge: AuthenticationChallenge | None = None

    def __repr__(self):
        return "_V2ChallengeAdmissionPlan(<redacted>)"

    __str__ = __repr__


def _raise_admission_error():
    raise V2ChallengeAdmissionError(_ADMISSION_ERROR) from None


def _validated_rate_aliases(rates, configuration):
    aliases = None
    try:
        if not isinstance(rates, ChallengeRateDigests) or not isinstance(configuration, ChallengeKeyConfiguration):
            raise TypeError
        candidate_aliases = rates.aliases
        expected_ids = tuple(sorted(configuration.rate_keys))
        candidate_ids = tuple(alias.key_id for alias in candidate_aliases)
        current_alias = next(alias for alias in candidate_aliases if alias.key_id == configuration.current_rate_kid)
        valid = (
            isinstance(candidate_aliases, tuple)
            and all(isinstance(alias, ChallengeDigest) for alias in candidate_aliases)
            and candidate_ids == expected_ids
            and len(set(candidate_ids)) == len(candidate_ids)
            and rates.current == current_alias
            and rates.current.key_id == configuration.current_rate_kid
        )
        if valid:
            aliases = candidate_aliases
    except Exception:
        aliases = None

    if aliases is None:
        _raise_admission_error()

    return aliases


def _validated_ip_aliases(ip_rates, configuration):
    return _validated_rate_aliases(ip_rates, configuration)


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


def _admit_challenge_delivery(
    *,
    purpose,
    destination_rates,
    ip_rates,
    challenge_configuration,
    using,
    post_lock_clock,
    lock_scope,
    apply_admitted,
):
    failed = False
    try:
        if (
            not isinstance(purpose, str)
            or purpose not in _ALL_PURPOSES
            or not callable(post_lock_clock)
            or not callable(lock_scope)
            or not callable(apply_admitted)
        ):
            raise TypeError
        if destination_rates is None:
            if purpose not in _UNKNOWN_CONTEXT_PURPOSES:
                raise ValueError
            destination_aliases = ()
        else:
            destination_aliases = _validated_rate_aliases(destination_rates, challenge_configuration)
        ip_aliases = _validated_rate_aliases(ip_rates, challenge_configuration)
        if destination_aliases and destination_rates.current.key_id != ip_rates.current.key_id:
            raise ValueError

        selected = _require_unrecorded_v2_connection(using=using)
        if selected.vendor != "postgresql":
            raise RuntimeError
        if selected.in_atomic_block is not False or selected.get_autocommit() is not True:
            raise RuntimeError

        lock_ids = _advisory_lock_ids(destination_aliases + ip_aliases)
        destination_filter = None
        if destination_aliases:
            destination_filter = reduce(
                or_,
                (Q(rate_key_id=alias.key_id, destination_rate_digest=alias.digest) for alias in destination_aliases),
            )
        ip_filter = reduce(
            or_,
            (Q(rate_key_id=alias.key_id, ip_rate_digest=alias.digest) for alias in ip_aliases),
        )

        with transaction.atomic(using=selected.alias, durable=True):
            raw_connection = selected.connection
            if raw_connection is None:
                raise RuntimeError
            with selected.cursor() as cursor:
                cursor.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED, NOT DEFERRABLE")
                for lock_id in lock_ids:
                    cursor.execute("SELECT pg_advisory_xact_lock(%s)", [lock_id])

            locked_scope = lock_scope(selected.alias)
            if isinstance(locked_scope, AuthenticationChallenge):
                if (
                    locked_scope._state.adding is not False
                    or locked_scope._state.db != selected.alias
                    or type(locked_scope.pk) is not uuid.UUID
                ):
                    raise ValueError
                locked_scope = (
                    AuthenticationChallenge.objects.using(selected.alias).select_for_update().get(pk=locked_scope.pk)
                )

            with selected.cursor() as cursor:
                at = post_lock_clock(cursor)
            if not isinstance(at, datetime) or at.tzinfo is None:
                raise ValueError

            deliveries = AuthenticationChallengeDelivery.objects.using(selected.alias)
            window_start = at - _RATE_WINDOW
            destination_count = None
            password_reset_count = None
            if destination_filter is not None:
                destination_count = deliveries.filter(
                    destination_filter,
                    reserved_at__gt=window_start,
                ).count()
                if purpose == AuthenticationChallengeDelivery.Purpose.PASSWORD_RESET:
                    password_reset_count = deliveries.filter(
                        destination_filter,
                        purpose=AuthenticationChallengeDelivery.Purpose.PASSWORD_RESET,
                        reserved_at__gt=window_start,
                    ).count()
            ip_count = deliveries.filter(
                ip_filter,
                reserved_at__gt=window_start,
            ).count()

            refused = (
                (destination_count is not None and destination_count >= _DESTINATION_LIMIT)
                or (password_reset_count is not None and password_reset_count >= _PASSWORD_RESET_LIMIT)
                or ip_count >= _IP_LIMIT
            )
            if refused:
                transaction.set_rollback(True, using=selected.alias)
                return _V2ChallengeAdmissionDecision.REFUSED

            context = _V2ChallengeAdmissionContext(
                using=selected.alias,
                purpose=purpose,
                delivery_id=uuid.uuid4(),
                reserved_at=at,
                lease_expires_at=at + _DELIVERY_LEASE,
                rate_key_id=ip_rates.current.key_id,
                destination_rate_digest=(destination_rates.current.digest if destination_rates is not None else None),
                ip_rate_digest=ip_rates.current.digest,
            )
            plan = apply_admitted(locked_scope, context)
            verified = _require_unrecorded_v2_connection(using=selected.alias)
            connection_valid = (
                verified is selected
                and selected.connection is raw_connection
                and selected.in_atomic_block is True
                and selected.get_autocommit() is False
                and transaction.get_rollback(using=selected.alias) is False
            )
            challenge_valid = False
            if isinstance(plan, _V2ChallengeAdmissionPlan):
                if plan.status == AuthenticationChallengeDelivery.Status.SUPPRESSED:
                    challenge_valid = plan.challenge is None
                elif plan.status == AuthenticationChallengeDelivery.Status.RESERVED:
                    challenge = plan.challenge
                    challenge_valid = (
                        isinstance(challenge, AuthenticationChallenge)
                        and challenge is locked_scope
                        and challenge._state.adding is False
                        and challenge._state.db == selected.alias
                        and type(challenge.pk) is uuid.UUID
                        and challenge.purpose == context.purpose
                        and challenge.status == AuthenticationChallenge.Status.OPEN
                        and challenge.resolved_at is None
                        and isinstance(challenge.created_at, datetime)
                        and challenge.created_at.tzinfo is not None
                        and isinstance(challenge.expires_at, datetime)
                        and challenge.expires_at.tzinfo is not None
                        and challenge.created_at <= context.reserved_at < challenge.expires_at
                        and context.destination_rate_digest is not None
                    )
                    if challenge_valid:
                        challenge_valid = (
                            AuthenticationChallenge.objects.using(selected.alias)
                            .filter(
                                pk=challenge.pk,
                                purpose=context.purpose,
                                status=AuthenticationChallenge.Status.OPEN,
                                resolved_at__isnull=True,
                                created_at__lte=context.reserved_at,
                                expires_at__gt=context.reserved_at,
                            )
                            .exists()
                        )
            if not connection_valid or not isinstance(plan, _V2ChallengeAdmissionPlan) or not challenge_valid:
                raise ValueError
            verified = _require_unrecorded_v2_connection(using=selected.alias)
            if verified is not selected or selected.connection is not raw_connection:
                raise ValueError
            if plan.status == AuthenticationChallengeDelivery.Status.RESERVED:
                _validate_v2_delivery_queue(
                    selected=selected,
                    raw_connection=raw_connection,
                )
            deliveries.create(
                uuid=context.delivery_id,
                challenge=plan.challenge,
                purpose=context.purpose,
                status=plan.status,
                rate_key_id=context.rate_key_id,
                destination_rate_digest=context.destination_rate_digest,
                ip_rate_digest=context.ip_rate_digest,
                proof_key_id=None,
                proof_digest=None,
                reserved_at=context.reserved_at,
                lease_expires_at=context.lease_expires_at,
                sending_at=None,
                accepted_at=None,
                proof_expires_at=None,
                resolved_at=(at if plan.status == AuthenticationChallengeDelivery.Status.SUPPRESSED else None),
            )
            if plan.status == AuthenticationChallengeDelivery.Status.RESERVED:
                _enqueue_reserved_v2_delivery(
                    selected=selected,
                    raw_connection=raw_connection,
                    delivery_id=context.delivery_id,
                )
            verified = _require_unrecorded_v2_connection(using=selected.alias)
            if (
                transaction.get_rollback(using=selected.alias)
                or verified is not selected
                or selected.connection is not raw_connection
                or selected.in_atomic_block is not True
                or selected.get_autocommit() is not False
            ):
                raise ValueError
        return _V2ChallengeAdmissionDecision.ADMITTED
    except Exception:
        failed = True

    if failed:
        _raise_admission_error()


def _lock_no_scope(_using):
    return None


def _plan_unknown_context_ip_suppression(locked_scope, context):
    if (
        locked_scope is not None
        or not isinstance(context, _V2ChallengeAdmissionContext)
        or context.purpose not in _UNKNOWN_CONTEXT_PURPOSES
        or context.destination_rate_digest is not None
    ):
        raise ValueError
    return _V2ChallengeAdmissionPlan(
        status=AuthenticationChallengeDelivery.Status.SUPPRESSED,
    )


def _record_unknown_context_ip_suppression(
    *,
    purpose,
    ip_rates,
    challenge_configuration,
    using,
    post_lock_clock,
):
    _admit_challenge_delivery(
        purpose=purpose,
        destination_rates=None,
        ip_rates=ip_rates,
        challenge_configuration=challenge_configuration,
        using=using,
        post_lock_clock=post_lock_clock,
        lock_scope=_lock_no_scope,
        apply_admitted=_plan_unknown_context_ip_suppression,
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
        if not isinstance(purpose, str) or purpose not in _UNKNOWN_CONTEXT_PURPOSES:
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
