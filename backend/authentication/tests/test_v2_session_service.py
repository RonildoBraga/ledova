import uuid
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from authentication.models import AuthSession, RefreshCredential
from authentication.security import (
    V2KeyMaterial,
    decode_v2_confirmation_token,
    decode_v2_refresh_token,
    encode_v2_confirmation_token,
    encode_v2_refresh_token,
    refresh_confirmation_digest,
    refresh_confirmation_matches,
    refresh_secret_matches,
)
from authentication.services.v2_sessions import (
    BrowserRefreshConfirmed,
    BrowserRefreshRaced,
    RefreshRotated,
    SessionIssued,
    SessionRejected,
    V2SessionPolicy,
    confirm_browser_refresh,
    issue_browser_session,
    issue_native_session,
    rotate_browser_refresh,
    rotate_native_refresh,
)

User = get_user_model()


class SyntheticRandom:
    def __init__(self):
        self.offset = 1

    def __call__(self, length):
        value = bytes((self.offset + index) % 256 for index in range(length))
        self.offset += length
        return value


class V2SessionServiceTest(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.random_bytes = SyntheticRandom()
        self.keys = V2KeyMaterial(access_signing_key=b"a" * 32, refresh_hmac_key=b"r" * 32)
        self.user = User.objects.create_user(
            email="v2-session@example.test",
            password="test-password-123",
            is_active=True,
            is_email_verified=True,
        )

    def clock(self):
        return self.now

    def service_arguments(self):
        return {
            "clock": self.clock,
            "random_bytes": self.random_bytes,
            "key_material": self.keys,
        }

    def issue_browser(self, **overrides):
        arguments = self.service_arguments()
        arguments.update(overrides)
        return issue_browser_session(self.user.pk, **arguments)

    def issue_native(self, **overrides):
        arguments = self.service_arguments()
        arguments.update(overrides)
        return issue_native_session(self.user.pk, **arguments)

    def rotate_browser(self, token, **overrides):
        arguments = self.service_arguments()
        arguments.update(overrides)
        return rotate_browser_refresh(token, **arguments)

    def rotate_native(self, token, **overrides):
        arguments = self.service_arguments()
        arguments.update(overrides)
        return rotate_native_refresh(token, **arguments)

    def confirm_browser(self, refresh_token, confirmation_token=None, **overrides):
        arguments = {"clock": self.clock, "key_material": self.keys}
        arguments.update(overrides)
        return confirm_browser_refresh(
            refresh_token,
            confirmation_token=confirmation_token,
            **arguments,
        )

    def prepare_browser_confirmation(self):
        issued = self.issue_browser()
        self.now += timedelta(seconds=1)
        rotated = self.rotate_browser(issued.refresh_token)
        self.now += timedelta(seconds=1)
        raced = self.rotate_browser(issued.refresh_token)
        return issued, rotated, raced

    def credential_for(self, token):
        return RefreshCredential.objects.get(pk=decode_v2_refresh_token(token).selector)

    def test_refresh_and_confirmation_tokens_are_canonical_and_redacted(self):
        selector = uuid.UUID("00000000-0000-0000-0000-000000000001")
        secret = bytes(range(32))
        refresh_token = encode_v2_refresh_token(selector, secret)
        refresh_parts = decode_v2_refresh_token(refresh_token)
        confirmation_token = encode_v2_confirmation_token(secret)
        confirmation_parts = decode_v2_confirmation_token(confirmation_token)

        self.assertEqual(len(refresh_token), 69)
        self.assertEqual(refresh_parts.selector, selector)
        self.assertEqual(refresh_parts.secret, secret)
        self.assertEqual(len(confirmation_token), 48)
        self.assertEqual(confirmation_parts.nonce, secret)
        self.assertNotIn("=", refresh_token)
        self.assertNotIn("=", confirmation_token)
        self.assertNotIn(str(selector), repr(refresh_parts))
        self.assertNotIn(secret.hex(), repr(refresh_parts))
        self.assertNotIn(secret.hex(), repr(confirmation_parts))

        confirmation_digest = refresh_confirmation_digest(
            uuid.UUID(int=1),
            uuid.UUID(int=2),
            secret,
            self.keys.refresh_hmac_key,
        )
        self.assertEqual(
            confirmation_digest.hex(),
            "2be22d1eff724d950f8a4b222c68e9bbce80c5ff63a171336d830f2256759e3a",
        )
        self.assertTrue(
            refresh_confirmation_matches(
                confirmation_digest,
                uuid.UUID(int=1),
                uuid.UUID(int=2),
                secret,
                self.keys.refresh_hmac_key,
            )
        )
        for session_id, predecessor_id, nonce, key in (
            (uuid.UUID(int=3), uuid.UUID(int=2), secret, self.keys.refresh_hmac_key),
            (uuid.UUID(int=1), uuid.UUID(int=3), secret, self.keys.refresh_hmac_key),
            (uuid.UUID(int=1), uuid.UUID(int=2), b"x" * 32, self.keys.refresh_hmac_key),
            (uuid.UUID(int=1), uuid.UUID(int=2), secret, b"x" * 32),
        ):
            self.assertFalse(
                refresh_confirmation_matches(
                    confirmation_digest,
                    session_id,
                    predecessor_id,
                    nonce,
                    key,
                )
            )

        for invalid in (
            refresh_token + "=",
            refresh_token.replace("lrv2.", "lrv1."),
            refresh_token[:-1],
            refresh_token + " ",
            "lrv2." + "é" * 64,
        ):
            with self.subTest(invalid=invalid[:8]):
                with self.assertRaisesMessage(ValueError, "Invalid v2 refresh token."):
                    decode_v2_refresh_token(invalid)

        for invalid in (
            confirmation_token + "=",
            confirmation_token.replace("lvc2.", "lvc1."),
            confirmation_token[:-1],
        ):
            with self.subTest(invalid_confirmation=invalid[:8]):
                with self.assertRaisesMessage(ValueError, "Invalid v2 confirmation token."):
                    decode_v2_confirmation_token(invalid)

    def test_policy_rejects_nonpositive_or_extended_windows(self):
        fields_and_caps = (
            ("absolute_lifetime", timedelta(days=30)),
            ("refresh_lifetime", timedelta(days=7)),
            ("browser_collision_window", timedelta(seconds=5)),
            ("browser_confirmation_lifetime", timedelta(seconds=10)),
        )

        for field, cap in fields_and_caps:
            with self.subTest(field=field, boundary="zero"):
                with self.assertRaisesMessage(ValueError, "Invalid v2 session policy."):
                    V2SessionPolicy(**{field: timedelta(0)})
            with self.subTest(field=field, boundary="extended"):
                with self.assertRaisesMessage(ValueError, "Invalid v2 session policy."):
                    V2SessionPolicy(**{field: cap + timedelta(microseconds=1)})

    def test_explicit_issuance_creates_digest_only_browser_and_native_sessions(self):
        browser = self.issue_browser(device_label="Browser")
        native = self.issue_native(device_label="Native")

        self.assertIsInstance(browser, SessionIssued)
        self.assertIsInstance(native, SessionIssued)
        self.assertEqual(browser.code, "session_issued")
        self.assertEqual(native.code, "session_issued")
        self.assertEqual(AuthSession.objects.count(), 2)
        self.assertEqual(RefreshCredential.objects.count(), 2)

        for result, client_type in (
            (browser, AuthSession.ClientType.BROWSER),
            (native, AuthSession.ClientType.NATIVE),
        ):
            session = AuthSession.objects.get(pk=result.session_id)
            credential = self.credential_for(result.refresh_token)
            parts = decode_v2_refresh_token(result.refresh_token)
            self.assertEqual(session.client_type, client_type)
            self.assertEqual(session.last_used_at, self.now)
            self.assertEqual(session.absolute_expires_at, self.now + timedelta(days=30))
            self.assertEqual(credential.expires_at, self.now + timedelta(days=7))
            self.assertTrue(
                refresh_secret_matches(
                    credential.secret_digest,
                    credential.uuid,
                    parts.secret,
                    self.keys.refresh_hmac_key,
                )
            )
            self.assertNotEqual(bytes(credential.secret_digest), parts.secret)
            self.assertNotIn(result.refresh_token, repr(result))
            self.assertNotIn(str(result.session_id), repr(result))

    def test_ineligible_or_unknown_user_cannot_receive_a_session(self):
        cases = (
            (self.user.pk, {"is_active": False, "is_email_verified": True}),
            (self.user.pk, {"is_active": True, "is_email_verified": False}),
            (self.user.pk + 9999, {"is_active": True, "is_email_verified": True}),
        )

        for user_id, state in cases:
            with self.subTest(user_id=user_id, state=state):
                User.objects.filter(pk=self.user.pk).update(**state)
                result = issue_native_session(user_id, **self.service_arguments())
                self.assertEqual(result, SessionRejected("user_inactive"))
                self.assertFalse(AuthSession.objects.exists())
                self.assertFalse(RefreshCredential.objects.exists())

    def test_invalid_device_label_or_random_source_cannot_create_partial_state(self):
        for label in ("x" * 81, "line\nbreak"):
            with self.subTest(label_length=len(label)):
                with self.assertRaisesMessage(ValueError, "Invalid v2 device label."):
                    self.issue_browser(device_label=label)

        with self.assertRaisesMessage(ValueError, "Invalid v2 random source."):
            self.issue_native(random_bytes=lambda length: b"x" * (length - 1))

        self.assertFalse(AuthSession.objects.exists())
        self.assertFalse(RefreshCredential.objects.exists())

    def test_rotation_consumes_and_links_exactly_one_successor(self):
        issued = self.issue_native()
        predecessor = self.credential_for(issued.refresh_token)
        self.now += timedelta(hours=1)

        rotated = self.rotate_native(issued.refresh_token)

        self.assertIsInstance(rotated, RefreshRotated)
        self.assertEqual(rotated.code, "refresh_rotated")
        predecessor.refresh_from_db()
        successor = self.credential_for(rotated.refresh_token)
        session = predecessor.session
        session.refresh_from_db()
        self.assertEqual(predecessor.used_at, self.now)
        self.assertEqual(predecessor.replaced_by, successor)
        self.assertEqual(successor.session, predecessor.session)
        self.assertEqual(RefreshCredential.objects.filter(session=session).count(), 2)
        self.assertEqual(
            RefreshCredential.objects.filter(
                session=session,
                used_at__isnull=True,
                revoked_at__isnull=True,
            ).get(),
            successor,
        )
        self.assertEqual(session.last_used_at, self.now)

    def test_wrong_secret_never_mutates_fresh_or_spent_credential(self):
        issued = self.issue_native()
        parts = decode_v2_refresh_token(issued.refresh_token)
        wrong_token = encode_v2_refresh_token(parts.selector, b"w" * 32)

        fresh_result = self.rotate_native(wrong_token)
        self.assertEqual(fresh_result, SessionRejected("invalid_refresh"))
        self.assertEqual(RefreshCredential.objects.count(), 1)
        self.assertIsNone(self.credential_for(issued.refresh_token).used_at)

        self.now += timedelta(seconds=1)
        self.assertIsInstance(self.rotate_native(issued.refresh_token), RefreshRotated)
        spent_result = self.rotate_native(wrong_token)
        session = AuthSession.objects.get(pk=issued.session_id)
        self.assertEqual(spent_result, SessionRejected("invalid_refresh"))
        self.assertEqual(RefreshCredential.objects.count(), 2)
        self.assertEqual(session.status, AuthSession.Status.ACTIVE)

    def test_native_replay_revokes_session_and_preserves_two_row_history(self):
        issued = self.issue_native()
        self.now += timedelta(seconds=1)
        self.assertIsInstance(self.rotate_native(issued.refresh_token), RefreshRotated)
        predecessor = self.credential_for(issued.refresh_token)
        original_revoked_at = self.now - timedelta(microseconds=1)
        predecessor.revoked_at = original_revoked_at
        predecessor.save(update_fields=["revoked_at"])
        self.now += timedelta(seconds=1)

        replay = self.rotate_native(issued.refresh_token)

        session = AuthSession.objects.get(pk=issued.session_id)
        self.assertEqual(replay, SessionRejected("refresh_reused"))
        self.assertEqual(session.status, AuthSession.Status.REVOKED)
        self.assertEqual(session.revoke_reason, AuthSession.RevokeReason.REFRESH_REUSED)
        self.assertEqual(RefreshCredential.objects.filter(session=session).count(), 2)
        self.assertFalse(RefreshCredential.objects.filter(session=session, revoked_at__isnull=True).exists())
        predecessor.refresh_from_db()
        self.assertEqual(predecessor.revoked_at, original_revoked_at)

    def test_first_browser_collision_enters_confirmation_without_new_successor(self):
        issued = self.issue_browser()
        self.now += timedelta(seconds=1)
        rotated = self.rotate_browser(issued.refresh_token)
        self.now += timedelta(seconds=1)

        raced = self.rotate_browser(issued.refresh_token)

        session = AuthSession.objects.get(pk=issued.session_id)
        predecessor = self.credential_for(issued.refresh_token)
        confirmation = decode_v2_confirmation_token(raced.confirmation_token)
        self.assertIsInstance(rotated, RefreshRotated)
        self.assertIsInstance(raced, BrowserRefreshRaced)
        self.assertEqual(raced.code, "refresh_raced")
        self.assertEqual(session.status, AuthSession.Status.REFRESH_CONFIRMATION_REQUIRED)
        self.assertEqual(RefreshCredential.objects.filter(session=session).count(), 2)
        self.assertTrue(
            refresh_confirmation_matches(
                predecessor.confirmation_nonce_digest,
                session.uuid,
                predecessor.uuid,
                confirmation.nonce,
                self.keys.refresh_hmac_key,
            )
        )
        self.assertNotEqual(bytes(predecessor.confirmation_nonce_digest), confirmation.nonce)
        self.assertNotIn(raced.confirmation_token, repr(raced))
        self.assertNotIn(str(raced.session_id), repr(raced))

    def test_second_or_late_browser_collision_revokes_session(self):
        issued = self.issue_browser()
        self.now += timedelta(seconds=1)
        self.rotate_browser(issued.refresh_token)
        self.now += timedelta(seconds=1)
        self.rotate_browser(issued.refresh_token)
        self.now += timedelta(seconds=1)

        second = self.rotate_browser(issued.refresh_token)

        session = AuthSession.objects.get(pk=issued.session_id)
        predecessor = self.credential_for(issued.refresh_token)
        self.assertEqual(second, SessionRejected("refresh_reused"))
        self.assertEqual(session.status, AuthSession.Status.REVOKED)
        self.assertEqual(session.revoke_reason, AuthSession.RevokeReason.REFRESH_REUSED)
        self.assertIsNotNone(predecessor.confirmation_consumed_at)

        self.user = User.objects.create_user(
            email="late-collision@example.test",
            password="test-password-123",
            is_active=True,
            is_email_verified=True,
        )
        self.now = timezone.now()
        late_issued = self.issue_browser()
        self.now += timedelta(seconds=1)
        self.rotate_browser(late_issued.refresh_token)
        self.now += timedelta(seconds=5)
        late = self.rotate_browser(late_issued.refresh_token)
        late_session = AuthSession.objects.get(pk=late_issued.session_id)
        self.assertEqual(late, SessionRejected("refresh_reused"))
        self.assertEqual(late_session.status, AuthSession.Status.REVOKED)

    def test_client_mismatch_and_expiry_fail_without_rotation(self):
        issued = self.issue_browser()
        mismatch = self.rotate_native(issued.refresh_token)
        self.assertEqual(mismatch, SessionRejected("invalid_refresh"))
        self.assertEqual(RefreshCredential.objects.count(), 1)

        credential = self.credential_for(issued.refresh_token)
        credential.expires_at = self.now
        credential.save(update_fields=["expires_at"])
        expired = self.rotate_browser(issued.refresh_token)
        self.assertEqual(expired, SessionRejected("refresh_expired"))
        self.assertIsNone(self.credential_for(issued.refresh_token).used_at)

        credential.expires_at = self.now + timedelta(days=1)
        credential.save(update_fields=["expires_at"])
        session = AuthSession.objects.get(pk=issued.session_id)
        session.absolute_expires_at = self.now
        session.save(update_fields=["absolute_expires_at"])
        absolute_expired = self.rotate_browser(issued.refresh_token)
        self.assertEqual(absolute_expired, SessionRejected("refresh_expired"))
        self.assertEqual(RefreshCredential.objects.filter(session=session).count(), 1)

    def test_browser_collision_with_expired_successor_revokes_session(self):
        policy = V2SessionPolicy(refresh_lifetime=timedelta(seconds=2))
        issued = self.issue_browser(policy=policy)
        self.now += timedelta(seconds=1)
        self.rotate_browser(issued.refresh_token, policy=policy)
        self.now += timedelta(seconds=2)

        result = self.rotate_browser(issued.refresh_token, policy=policy)

        session = AuthSession.objects.get(pk=issued.session_id)
        self.assertEqual(result, SessionRejected("refresh_reused"))
        self.assertEqual(session.status, AuthSession.Status.REVOKED)

    def test_browser_confirmation_cannot_outlive_successor(self):
        policy = V2SessionPolicy(refresh_lifetime=timedelta(seconds=3))
        issued = self.issue_browser(policy=policy)
        self.now += timedelta(seconds=1)
        rotated = self.rotate_browser(issued.refresh_token, policy=policy)
        self.now += timedelta(seconds=2)

        raced = self.rotate_browser(issued.refresh_token, policy=policy)

        self.assertIsInstance(raced, BrowserRefreshRaced)
        self.assertEqual(raced.confirmation_expires_at, rotated.refresh_expires_at)

    def test_browser_confirmation_consumes_nonce_without_rotating_successor(self):
        issued, rotated, raced = self.prepare_browser_confirmation()
        predecessor = self.credential_for(issued.refresh_token)
        successor = self.credential_for(rotated.refresh_token)
        last_used_at = AuthSession.objects.get(pk=issued.session_id).last_used_at
        self.now += timedelta(seconds=1)

        confirmed = self.confirm_browser(rotated.refresh_token, raced.confirmation_token)

        session = AuthSession.objects.get(pk=issued.session_id)
        predecessor.refresh_from_db()
        successor.refresh_from_db()
        self.assertIsInstance(confirmed, BrowserRefreshConfirmed)
        self.assertEqual(confirmed.code, "refresh_confirmed")
        self.assertEqual(session.status, AuthSession.Status.ACTIVE)
        self.assertEqual(session.last_used_at, last_used_at)
        self.assertEqual(predecessor.confirmation_consumed_at, self.now)
        self.assertIsNotNone(predecessor.confirmation_nonce_digest)
        self.assertIsNone(successor.used_at)
        self.assertIsNone(successor.revoked_at)
        self.assertEqual(RefreshCredential.objects.filter(session=session).count(), 2)
        self.assertNotIn(str(confirmed.session_id), repr(confirmed))

    def test_authenticated_invalid_confirmation_revokes_and_consumes_nonce(self):
        proofs = (None, "malformed", encode_v2_confirmation_token(b"w" * 32))

        for index, proof in enumerate(proofs):
            with self.subTest(proof=index):
                if index:
                    self.user = User.objects.create_user(
                        email=f"confirmation-failure-{index}@example.test",
                        password="test-password-123",
                        is_active=True,
                        is_email_verified=True,
                    )
                    self.now = timezone.now()
                issued, rotated, _raced = self.prepare_browser_confirmation()

                result = self.confirm_browser(rotated.refresh_token, proof)

                session = AuthSession.objects.get(pk=issued.session_id)
                predecessor = self.credential_for(issued.refresh_token)
                self.assertEqual(result, SessionRejected("session_revoked"))
                self.assertEqual(session.status, AuthSession.Status.REVOKED)
                self.assertEqual(session.revoke_reason, AuthSession.RevokeReason.CONFIRMATION_FAILED)
                self.assertIsNotNone(predecessor.confirmation_consumed_at)
                self.assertFalse(
                    RefreshCredential.objects.filter(
                        session=session,
                        revoked_at__isnull=True,
                    ).exists()
                )

    def test_unauthenticated_confirmation_attempts_do_not_mutate_pending_session(self):
        issued, rotated, raced = self.prepare_browser_confirmation()
        successor_parts = decode_v2_refresh_token(rotated.refresh_token)
        wrong_secret = encode_v2_refresh_token(successor_parts.selector, b"w" * 32)
        unknown = encode_v2_refresh_token(uuid.uuid4(), b"u" * 32)

        for refresh_token in ("malformed", wrong_secret, unknown):
            with self.subTest(refresh_token=refresh_token[:8]):
                result = self.confirm_browser(refresh_token, raced.confirmation_token)
                self.assertEqual(result, SessionRejected("invalid_refresh"))

        native = self.issue_native()
        native_result = self.confirm_browser(native.refresh_token, raced.confirmation_token)

        session = AuthSession.objects.get(pk=issued.session_id)
        predecessor = self.credential_for(issued.refresh_token)
        native_session = AuthSession.objects.get(pk=native.session_id)
        self.assertEqual(native_result, SessionRejected("invalid_refresh"))
        self.assertEqual(session.status, AuthSession.Status.REFRESH_CONFIRMATION_REQUIRED)
        self.assertIsNone(predecessor.confirmation_consumed_at)
        self.assertFalse(RefreshCredential.objects.filter(session=session, revoked_at__isnull=False).exists())
        self.assertEqual(native_session.status, AuthSession.Status.ACTIVE)

    def test_late_expired_successor_and_repeated_confirmation_revoke(self):
        issued, rotated, raced = self.prepare_browser_confirmation()
        self.now = raced.confirmation_expires_at

        late = self.confirm_browser(rotated.refresh_token, raced.confirmation_token)

        late_session = AuthSession.objects.get(pk=issued.session_id)
        self.assertEqual(late, SessionRejected("session_revoked"))
        self.assertEqual(late_session.revoke_reason, AuthSession.RevokeReason.CONFIRMATION_FAILED)

        self.user = User.objects.create_user(
            email="confirmation-repeat@example.test",
            password="test-password-123",
            is_active=True,
            is_email_verified=True,
        )
        self.now = timezone.now()
        repeated_issued, repeated_rotated, repeated_raced = self.prepare_browser_confirmation()
        self.now += timedelta(seconds=1)
        self.assertIsInstance(
            self.confirm_browser(repeated_rotated.refresh_token, repeated_raced.confirmation_token),
            BrowserRefreshConfirmed,
        )
        predecessor = self.credential_for(repeated_issued.refresh_token)
        consumed_at = predecessor.confirmation_consumed_at
        self.now += timedelta(seconds=1)

        repeated = self.confirm_browser(repeated_rotated.refresh_token, repeated_raced.confirmation_token)

        repeated_session = AuthSession.objects.get(pk=repeated_issued.session_id)
        predecessor.refresh_from_db()
        self.assertEqual(repeated, SessionRejected("session_revoked"))
        self.assertEqual(repeated_session.revoke_reason, AuthSession.RevokeReason.CONFIRMATION_FAILED)
        self.assertEqual(predecessor.confirmation_consumed_at, consumed_at)

    def test_confirmation_requires_exact_unexpired_successor(self):
        issued, rotated, raced = self.prepare_browser_confirmation()
        other = self.issue_browser()

        wrong_successor = self.confirm_browser(other.refresh_token, raced.confirmation_token)

        pending = AuthSession.objects.get(pk=issued.session_id)
        other_session = AuthSession.objects.get(pk=other.session_id)
        self.assertEqual(wrong_successor, SessionRejected("session_revoked"))
        self.assertEqual(pending.status, AuthSession.Status.REFRESH_CONFIRMATION_REQUIRED)
        self.assertEqual(other_session.revoke_reason, AuthSession.RevokeReason.CONFIRMATION_FAILED)

        successor = self.credential_for(rotated.refresh_token)
        successor.expires_at = self.now
        successor.save(update_fields=["expires_at"])

        expired = self.confirm_browser(rotated.refresh_token, raced.confirmation_token)

        pending.refresh_from_db()
        self.assertEqual(expired, SessionRejected("session_revoked"))
        self.assertEqual(pending.revoke_reason, AuthSession.RevokeReason.CONFIRMATION_FAILED)

    def test_spent_predecessor_cannot_confirm_its_successor(self):
        issued, _rotated, raced = self.prepare_browser_confirmation()

        result = self.confirm_browser(issued.refresh_token, raced.confirmation_token)

        session = AuthSession.objects.get(pk=issued.session_id)
        self.assertEqual(result, SessionRejected("session_revoked"))
        self.assertEqual(session.revoke_reason, AuthSession.RevokeReason.CONFIRMATION_FAILED)

    def test_confirmation_preserves_account_state_precedence(self):
        issued, rotated, raced = self.prepare_browser_confirmation()
        User.objects.filter(pk=self.user.pk).update(is_active=False)

        result = self.confirm_browser(rotated.refresh_token, raced.confirmation_token)

        session = AuthSession.objects.get(pk=issued.session_id)
        self.assertEqual(result, SessionRejected("session_revoked"))
        self.assertEqual(session.revoke_reason, AuthSession.RevokeReason.ACCOUNT_DISABLED)

    def test_confirmation_rolls_back_consumption_and_reactivation_failure(self):
        issued, rotated, raced = self.prepare_browser_confirmation()
        original_save = AuthSession.save

        def save_then_fail(instance, *args, **kwargs):
            result = original_save(instance, *args, **kwargs)
            if instance.status == AuthSession.Status.ACTIVE:
                raise RuntimeError("synthetic confirmation failure")
            return result

        with patch.object(AuthSession, "save", new=save_then_fail):
            with self.assertRaisesMessage(RuntimeError, "synthetic confirmation failure"):
                self.confirm_browser(rotated.refresh_token, raced.confirmation_token)

        session = AuthSession.objects.get(pk=issued.session_id)
        predecessor = self.credential_for(issued.refresh_token)
        successor = self.credential_for(rotated.refresh_token)
        self.assertEqual(session.status, AuthSession.Status.REFRESH_CONFIRMATION_REQUIRED)
        self.assertIsNone(predecessor.confirmation_consumed_at)
        self.assertIsNone(successor.used_at)
        self.assertIsNone(successor.revoked_at)

    def test_inactive_user_revokes_existing_session(self):
        issued = self.issue_native()
        User.objects.filter(pk=self.user.pk).update(is_active=False)

        result = self.rotate_native(issued.refresh_token)

        session = AuthSession.objects.get(pk=issued.session_id)
        self.assertEqual(result, SessionRejected("session_revoked"))
        self.assertEqual(session.status, AuthSession.Status.REVOKED)
        self.assertEqual(session.revoke_reason, AuthSession.RevokeReason.ACCOUNT_DISABLED)
        self.assertFalse(RefreshCredential.objects.filter(session=session, revoked_at__isnull=True).exists())

    def test_issue_and_rotation_roll_back_after_real_credential_insert_failure(self):
        original_save = RefreshCredential.save

        def save_then_fail(instance, *args, **kwargs):
            was_adding = instance._state.adding
            result = original_save(instance, *args, **kwargs)
            if was_adding:
                raise RuntimeError("synthetic post-insert failure")
            return result

        with patch.object(RefreshCredential, "save", new=save_then_fail):
            with self.assertRaisesMessage(RuntimeError, "synthetic post-insert failure"):
                self.issue_native()

        self.assertFalse(AuthSession.objects.exists())
        self.assertFalse(RefreshCredential.objects.exists())

        issued = self.issue_native()
        with patch.object(RefreshCredential, "save", new=save_then_fail):
            with self.assertRaisesMessage(RuntimeError, "synthetic post-insert failure"):
                self.rotate_native(issued.refresh_token)

        predecessor = self.credential_for(issued.refresh_token)
        session = AuthSession.objects.get(pk=issued.session_id)
        self.assertIsNone(predecessor.used_at)
        self.assertIsNone(predecessor.replaced_by_id)
        self.assertEqual(session.status, AuthSession.Status.ACTIVE)
        self.assertEqual(RefreshCredential.objects.filter(session=session).count(), 1)
