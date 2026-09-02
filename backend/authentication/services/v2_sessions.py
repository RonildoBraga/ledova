import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from authentication.models import AuthSession, RefreshCredential
from authentication.security import (
    V2KeyMaterial,
    decode_v2_refresh_token,
    encode_v2_confirmation_token,
    encode_v2_refresh_token,
    load_v2_key_material,
    refresh_confirmation_digest,
    refresh_secret_digest,
    refresh_secret_matches,
)

_POLICY_ERROR = "Invalid v2 session policy."
_DEVICE_LABEL_ERROR = "Invalid v2 device label."
_RANDOM_SOURCE_ERROR = "Invalid v2 random source."
_SELECTOR_GENERATION_ERROR = "Unable to create v2 refresh credential."
_REJECTION_CODES = frozenset(
    {
        "user_inactive",
        "invalid_refresh",
        "session_revoked",
        "refresh_expired",
        "refresh_reused",
    }
)


@dataclass(frozen=True)
class V2SessionPolicy:
    absolute_lifetime: timedelta = timedelta(days=30)
    refresh_lifetime: timedelta = timedelta(days=7)
    browser_collision_window: timedelta = timedelta(seconds=5)
    browser_confirmation_lifetime: timedelta = timedelta(seconds=10)

    def __post_init__(self):
        limits = (
            (self.absolute_lifetime, timedelta(days=30)),
            (self.refresh_lifetime, timedelta(days=7)),
            (self.browser_collision_window, timedelta(seconds=5)),
            (self.browser_confirmation_lifetime, timedelta(seconds=10)),
        )
        if any(not isinstance(value, timedelta) or value <= timedelta(0) or value > cap for value, cap in limits):
            raise ValueError(_POLICY_ERROR)


DEFAULT_V2_SESSION_POLICY = V2SessionPolicy()


@dataclass(frozen=True, repr=False)
class SessionIssued:
    session_id: uuid.UUID
    refresh_token: str
    refresh_expires_at: datetime
    session_expires_at: datetime
    code: str = field(default="session_issued", init=False)

    def __repr__(self):
        return (
            "SessionIssued(session_id=<redacted>, refresh_token=<redacted>, "
            "refresh_expires_at=<redacted>, session_expires_at=<redacted>, code='session_issued')"
        )


@dataclass(frozen=True, repr=False)
class RefreshRotated:
    session_id: uuid.UUID
    refresh_token: str
    refresh_expires_at: datetime
    session_expires_at: datetime
    code: str = field(default="refresh_rotated", init=False)

    def __repr__(self):
        return (
            "RefreshRotated(session_id=<redacted>, refresh_token=<redacted>, "
            "refresh_expires_at=<redacted>, session_expires_at=<redacted>, code='refresh_rotated')"
        )


@dataclass(frozen=True, repr=False)
class BrowserRefreshRaced:
    session_id: uuid.UUID
    confirmation_token: str
    confirmation_expires_at: datetime
    code: str = field(default="refresh_raced", init=False)

    def __repr__(self):
        return (
            "BrowserRefreshRaced(session_id=<redacted>, confirmation_token=<redacted>, "
            "confirmation_expires_at=<redacted>, code='refresh_raced')"
        )


@dataclass(frozen=True, repr=False)
class SessionRejected:
    code: str

    def __post_init__(self):
        if self.code not in _REJECTION_CODES:
            raise ValueError("Invalid v2 session rejection code.")

    def __repr__(self):
        return f"SessionRejected(code={self.code!r})"


def _validated_device_label(value):
    if not isinstance(value, str) or len(value) > 80 or not all(character.isprintable() for character in value):
        raise ValueError(_DEVICE_LABEL_ERROR)
    return value


def _random_exact(random_bytes, length):
    try:
        value = random_bytes(length)
    except Exception:
        raise ValueError(_RANDOM_SOURCE_ERROR) from None
    if not isinstance(value, (bytes, bytearray, memoryview)) or len(value) != length:
        raise ValueError(_RANDOM_SOURCE_ERROR)
    return bytes(value)


def _resolved_key_material(key_material):
    if key_material is None:
        return load_v2_key_material()
    if not isinstance(key_material, V2KeyMaterial):
        raise TypeError("Invalid v2 key material.")
    return V2KeyMaterial(
        access_signing_key=key_material.access_signing_key,
        refresh_hmac_key=key_material.refresh_hmac_key,
    )


def _validated_policy(policy):
    if not isinstance(policy, V2SessionPolicy):
        raise ValueError(_POLICY_ERROR)
    return policy


def _create_refresh_credential(session, *, at, policy, random_bytes, key_material):
    for _attempt in range(4):
        selector = uuid.UUID(bytes=_random_exact(random_bytes, 16))
        if not RefreshCredential.objects.filter(pk=selector).exists():
            break
    else:
        raise RuntimeError(_SELECTOR_GENERATION_ERROR)
    secret = _random_exact(random_bytes, 32)
    token = encode_v2_refresh_token(selector, secret)
    parts = decode_v2_refresh_token(token)
    expires_at = min(at + policy.refresh_lifetime, session.absolute_expires_at)
    credential = RefreshCredential.objects.create(
        uuid=parts.selector,
        session=session,
        secret_digest=refresh_secret_digest(parts.selector, parts.secret, key_material.refresh_hmac_key),
        expires_at=expires_at,
    )
    return credential, token


def _issue_session(user_id, client_type, *, device_label, policy, clock, random_bytes, key_material):
    label = _validated_device_label(device_label)
    policy = _validated_policy(policy)
    material = _resolved_key_material(key_material)
    User = get_user_model()

    with transaction.atomic():
        user = User.objects.select_for_update().filter(pk=user_id).first()
        if user is None or not user.is_active or not user.is_email_verified:
            return SessionRejected("user_inactive")

        at = clock()
        session = AuthSession.objects.create(
            user=user,
            client_type=client_type,
            device_label=label,
            absolute_expires_at=at + policy.absolute_lifetime,
            last_used_at=at,
        )
        credential, token = _create_refresh_credential(
            session,
            at=at,
            policy=policy,
            random_bytes=random_bytes,
            key_material=material,
        )
        return SessionIssued(
            session_id=session.uuid,
            refresh_token=token,
            refresh_expires_at=credential.expires_at,
            session_expires_at=session.absolute_expires_at,
        )


def issue_browser_session(
    user_id,
    *,
    device_label="",
    policy=DEFAULT_V2_SESSION_POLICY,
    clock=timezone.now,
    random_bytes=secrets.token_bytes,
    key_material=None,
):
    return _issue_session(
        user_id,
        AuthSession.ClientType.BROWSER,
        device_label=device_label,
        policy=policy,
        clock=clock,
        random_bytes=random_bytes,
        key_material=key_material,
    )


def issue_native_session(
    user_id,
    *,
    device_label="",
    policy=DEFAULT_V2_SESSION_POLICY,
    clock=timezone.now,
    random_bytes=secrets.token_bytes,
    key_material=None,
):
    return _issue_session(
        user_id,
        AuthSession.ClientType.NATIVE,
        device_label=device_label,
        policy=policy,
        clock=clock,
        random_bytes=random_bytes,
        key_material=key_material,
    )


def _rotation_topology(selector):
    return RefreshCredential.objects.filter(uuid=selector).values_list("session_id", "session__user_id").first()


def _locked_rotation_state(selector, topology):
    session_id, user_id = topology
    User = get_user_model()
    user = User.objects.select_for_update().filter(pk=user_id).first()
    if user is None:
        return None

    session = AuthSession.objects.select_for_update().filter(pk=session_id, user_id=user_id).first()
    if session is None:
        return None

    credential = RefreshCredential.objects.select_for_update().filter(pk=selector, session=session).first()
    if credential is None:
        return None
    return user, session, credential


def _revoke_credentials(session, at):
    credentials = RefreshCredential.objects.filter(session=session)
    credentials.filter(revoked_at__isnull=True).update(revoked_at=at)
    credentials.filter(
        confirmation_nonce_digest__isnull=False,
        confirmation_consumed_at__isnull=True,
    ).update(confirmation_consumed_at=at)


def _revoke_session(session, at, reason):
    session.status = AuthSession.Status.REVOKED
    session.revoked_at = at
    session.revoke_reason = reason
    session.save(update_fields=["status", "revoked_at", "revoke_reason", "updated_at"])
    _revoke_credentials(session, at)


def _rotate_live(session, credential, *, at, policy, random_bytes, key_material):
    credential.used_at = at
    credential.save(update_fields=["used_at", "updated_at"])
    successor, token = _create_refresh_credential(
        session,
        at=at,
        policy=policy,
        random_bytes=random_bytes,
        key_material=key_material,
    )
    credential.replaced_by = successor
    credential.save(update_fields=["replaced_by", "updated_at"])
    session.last_used_at = at
    session.save(update_fields=["last_used_at", "updated_at"])
    return RefreshRotated(
        session_id=session.uuid,
        refresh_token=token,
        refresh_expires_at=successor.expires_at,
        session_expires_at=session.absolute_expires_at,
    )


def _browser_collision(session, credential, *, at, policy, random_bytes, key_material):
    inside_window = (
        credential.used_at is not None and timedelta(0) <= at - credential.used_at < policy.browser_collision_window
    )
    successor = (
        RefreshCredential.objects.select_for_update().filter(pk=credential.replaced_by_id, session=session).first()
    )
    successor_is_live = (
        successor is not None
        and successor.used_at is None
        and successor.revoked_at is None
        and successor.expires_at > at
    )
    confirmation_exists = RefreshCredential.objects.filter(
        session=session,
        confirmation_nonce_digest__isnull=False,
    ).exists()
    if not inside_window or not successor_is_live or confirmation_exists:
        _revoke_session(session, at, AuthSession.RevokeReason.REFRESH_REUSED)
        return SessionRejected("refresh_reused")

    nonce = _random_exact(random_bytes, 32)
    confirmation_expires_at = min(
        at + policy.browser_confirmation_lifetime,
        session.absolute_expires_at,
        successor.expires_at,
    )
    credential.confirmation_nonce_digest = refresh_confirmation_digest(
        session.uuid,
        credential.uuid,
        nonce,
        key_material.refresh_hmac_key,
    )
    credential.confirmation_expires_at = confirmation_expires_at
    credential.save(
        update_fields=[
            "confirmation_nonce_digest",
            "confirmation_expires_at",
            "updated_at",
        ]
    )
    session.status = AuthSession.Status.REFRESH_CONFIRMATION_REQUIRED
    session.save(update_fields=["status", "updated_at"])
    return BrowserRefreshRaced(
        session_id=session.uuid,
        confirmation_token=encode_v2_confirmation_token(nonce),
        confirmation_expires_at=confirmation_expires_at,
    )


def _rotate_refresh(
    refresh_token,
    client_type,
    *,
    policy,
    clock,
    random_bytes,
    key_material,
):
    try:
        parts = decode_v2_refresh_token(refresh_token)
    except ValueError:
        return SessionRejected("invalid_refresh")

    policy = _validated_policy(policy)
    material = _resolved_key_material(key_material)
    topology = _rotation_topology(parts.selector)
    if topology is None:
        return SessionRejected("invalid_refresh")

    with transaction.atomic():
        state = _locked_rotation_state(parts.selector, topology)
        if state is None:
            return SessionRejected("invalid_refresh")
        user, session, credential = state
        at = clock()

        if not refresh_secret_matches(
            credential.secret_digest,
            credential.uuid,
            parts.secret,
            material.refresh_hmac_key,
        ):
            return SessionRejected("invalid_refresh")

        if session.client_type != client_type:
            return SessionRejected("invalid_refresh")
        if not user.is_active or not user.is_email_verified:
            reason = (
                AuthSession.RevokeReason.ACCOUNT_DISABLED
                if not user.is_active
                else AuthSession.RevokeReason.EMAIL_CHANGE
            )
            if session.status == AuthSession.Status.REVOKED:
                _revoke_credentials(session, at)
            else:
                _revoke_session(session, at, reason)
            return SessionRejected("session_revoked")
        if session.status == AuthSession.Status.REVOKED:
            _revoke_credentials(session, at)
            return SessionRejected("session_revoked")
        if session.status == AuthSession.Status.REFRESH_CONFIRMATION_REQUIRED:
            _revoke_session(session, at, AuthSession.RevokeReason.REFRESH_REUSED)
            return SessionRejected("refresh_reused")
        if session.absolute_expires_at <= at:
            return SessionRejected("refresh_expired")
        if credential.used_at is not None:
            if client_type == AuthSession.ClientType.BROWSER:
                return _browser_collision(
                    session,
                    credential,
                    at=at,
                    policy=policy,
                    random_bytes=random_bytes,
                    key_material=material,
                )
            _revoke_session(session, at, AuthSession.RevokeReason.REFRESH_REUSED)
            return SessionRejected("refresh_reused")
        if credential.revoked_at is not None:
            _revoke_session(session, at, AuthSession.RevokeReason.REFRESH_REUSED)
            return SessionRejected("refresh_reused")
        if credential.expires_at <= at:
            return SessionRejected("refresh_expired")
        return _rotate_live(
            session,
            credential,
            at=at,
            policy=policy,
            random_bytes=random_bytes,
            key_material=material,
        )


def rotate_browser_refresh(
    refresh_token,
    *,
    policy=DEFAULT_V2_SESSION_POLICY,
    clock=timezone.now,
    random_bytes=secrets.token_bytes,
    key_material=None,
):
    return _rotate_refresh(
        refresh_token,
        AuthSession.ClientType.BROWSER,
        policy=policy,
        clock=clock,
        random_bytes=random_bytes,
        key_material=key_material,
    )


def rotate_native_refresh(
    refresh_token,
    *,
    policy=DEFAULT_V2_SESSION_POLICY,
    clock=timezone.now,
    random_bytes=secrets.token_bytes,
    key_material=None,
):
    return _rotate_refresh(
        refresh_token,
        AuthSession.ClientType.NATIVE,
        policy=policy,
        clock=clock,
        random_bytes=random_bytes,
        key_material=key_material,
    )
