import uuid
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import OperationalError
from django.test import TestCase, override_settings

from authentication.models import AuthSession
from authentication.security import (
    INITIAL_ACCESS_KID,
    AccessTokenConfigurationError,
    AccessTokenError,
    V2KeyMaterial,
    issue_access_token,
    resolve_access_config,
    resolve_access_expiry,
)
from authentication.services import (
    V2AccessSessionError,
    V2AccessSource,
    bind_v2_access,
)

User = get_user_model()


@override_settings(SECRET_KEY="django-secret-distinct-from-v2-access-keys")
class V2AccessBindingTest(TestCase):
    def setUp(self):
        self.now = datetime(2030, 1, 2, 3, 4, 5, 500000, tzinfo=timezone.utc)
        self.keys = V2KeyMaterial(access_signing_key=b"a" * 32, refresh_hmac_key=b"r" * 32)
        self.configuration = resolve_access_config(self.keys)
        self.user = User.objects.create_user(
            email="member@example.test",
            password="synthetic-password",
            is_active=True,
            is_email_verified=True,
        )

    def create_session(self, client_type=AuthSession.ClientType.BROWSER, **overrides):
        values = {
            "user": self.user,
            "client_type": client_type,
            "status": AuthSession.Status.ACTIVE,
            "absolute_expires_at": self.now + timedelta(hours=1),
            "last_used_at": self.now - timedelta(minutes=1),
        }
        values.update(overrides)
        return AuthSession.objects.create(**values)

    def issue(
        self,
        session,
        *,
        user_id=None,
        session_id=None,
        issued_at=None,
        expires_at=None,
        configuration=None,
    ):
        issued_at = issued_at or self.now
        expires_at = expires_at or resolve_access_expiry(
            issued_at,
            session.absolute_expires_at,
            timedelta(minutes=15),
        )
        return issue_access_token(
            user_id if user_id is not None else self.user.pk,
            session_id or session.uuid,
            issued_at=issued_at,
            expires_at=expires_at,
            session_expires_at=max(session.absolute_expires_at, expires_at),
            token_id=uuid.UUID("00000000-0000-4000-8000-000000000001"),
            configuration=configuration or self.configuration,
        ).access_token

    def bind(self, token, source):
        return bind_v2_access(
            token,
            source=source,
            configuration=self.configuration,
            clock=lambda: self.now,
        )

    def assert_session_rejected(self, token, source, queries=1):
        with self.assertNumQueries(queries):
            with self.assertRaisesMessage(V2AccessSessionError, "Invalid v2 access session."):
                self.bind(token, source)

    def test_browser_and_native_sources_bind_to_the_matching_active_session_in_one_read(self):
        cases = (
            (AuthSession.ClientType.BROWSER, V2AccessSource.BROWSER_COOKIE),
            (AuthSession.ClientType.NATIVE, V2AccessSource.NATIVE_BEARER),
        )
        for client_type, source in cases:
            with self.subTest(source=source):
                session = self.create_session(client_type)
                token = self.issue(session)

                with self.assertNumQueries(1):
                    user, context = self.bind(token, source)

                self.assertEqual(user.pk, self.user.pk)
                self.assertEqual(context.session_id, session.uuid)
                self.assertEqual(context.source, source)
                self.assertEqual(context.access_expires_at, self.now.replace(microsecond=0) + timedelta(minutes=15))
                session.delete()

    def test_source_must_match_the_persisted_client_type(self):
        cases = (
            (AuthSession.ClientType.BROWSER, V2AccessSource.NATIVE_BEARER),
            (AuthSession.ClientType.NATIVE, V2AccessSource.BROWSER_COOKIE),
        )
        for client_type, source in cases:
            with self.subTest(source=source):
                session = self.create_session(client_type)
                self.assert_session_rejected(self.issue(session), source)
                session.delete()

    def test_signed_subject_and_session_must_match_the_same_persisted_row(self):
        session = self.create_session()
        cases = (
            ("subject", self.issue(session, user_id=self.user.pk + 1000)),
            (
                "session",
                self.issue(session, session_id=uuid.UUID("00000000-0000-4000-8000-000000000099")),
            ),
        )

        for field, token in cases:
            with self.subTest(field=field):
                self.assert_session_rejected(token, V2AccessSource.BROWSER_COOKIE)

    def test_only_active_unexpired_sessions_for_active_verified_users_bind(self):
        session = self.create_session()
        token = self.issue(session)

        session.status = AuthSession.Status.REFRESH_CONFIRMATION_REQUIRED
        session.save(update_fields=["status"])
        self.assert_session_rejected(token, V2AccessSource.BROWSER_COOKIE)

        session.status = AuthSession.Status.REVOKED
        session.revoked_at = self.now
        session.revoke_reason = AuthSession.RevokeReason.SIGNED_OUT
        session.save(update_fields=["status", "revoked_at", "revoke_reason"])
        self.assert_session_rejected(token, V2AccessSource.BROWSER_COOKIE)

        session.delete()
        session = self.create_session(absolute_expires_at=self.now)
        expired_token = self.issue(
            session,
            issued_at=self.now - timedelta(minutes=5),
            expires_at=self.now + timedelta(minutes=5),
        )
        self.assert_session_rejected(expired_token, V2AccessSource.BROWSER_COOKIE)

        session.absolute_expires_at = self.now + timedelta(hours=1)
        session.save(update_fields=["absolute_expires_at"])
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        self.assert_session_rejected(expired_token, V2AccessSource.BROWSER_COOKIE)

        self.user.is_active = True
        self.user.is_email_verified = False
        self.user.save(update_fields=["is_active", "is_email_verified"])
        self.assert_session_rejected(expired_token, V2AccessSource.BROWSER_COOKIE)

    def test_access_expiry_cannot_exceed_the_persisted_session_expiry(self):
        session = self.create_session(absolute_expires_at=self.now + timedelta(minutes=5))
        token = self.issue(session, expires_at=self.now + timedelta(minutes=10))

        self.assert_session_rejected(token, V2AccessSource.BROWSER_COOKIE)

    def test_access_expiry_may_equal_the_persisted_session_expiry(self):
        session_expires_at = self.now.replace(microsecond=0) + timedelta(minutes=15)
        session = self.create_session(absolute_expires_at=session_expires_at)
        token = self.issue(session, expires_at=session_expires_at)

        with self.assertNumQueries(1):
            _, context = self.bind(token, V2AccessSource.BROWSER_COOKIE)

        self.assertEqual(context.access_expires_at, session_expires_at)

    def test_invalid_or_expired_tokens_are_rejected_before_any_database_query(self):
        session = self.create_session()
        expired = self.issue(
            session,
            issued_at=self.now - timedelta(minutes=20),
            expires_at=self.now - timedelta(minutes=5),
        )
        wrong_key_configuration = resolve_access_config(
            V2KeyMaterial(access_signing_key=b"w" * 32, refresh_hmac_key=b"z" * 32)
        )
        unknown_kid_configuration = resolve_access_config(
            V2KeyMaterial(access_signing_key=b"u" * 32, refresh_hmac_key=b"v" * 32),
            current_kid="ledova-v2-access-hs256-unknown",
        )
        invalid_tokens = (
            ("malformed", "not.a.token"),
            ("noncanonical", self.issue(session) + "="),
            ("expired", expired),
            ("wrong_signature", self.issue(session, configuration=wrong_key_configuration)),
            ("unknown_kid", self.issue(session, configuration=unknown_kid_configuration)),
        )

        for case, token in invalid_tokens:
            with self.subTest(case=case):
                with self.assertNumQueries(0):
                    with self.assertRaisesMessage(AccessTokenError, "Invalid v2 access token."):
                        self.bind(token, V2AccessSource.BROWSER_COOKIE)

    def test_reviewed_key_rotation_accepts_old_and_current_signer_kids(self):
        session = self.create_session()
        old_token = self.issue(session)
        current_key = b"n" * 32
        rotated_configuration = resolve_access_config(
            V2KeyMaterial(access_signing_key=current_key, refresh_hmac_key=b"r" * 32),
            current_kid="ledova-v2-access-hs256-2",
            verifier_keys={
                INITIAL_ACCESS_KID: self.keys.access_signing_key,
                "ledova-v2-access-hs256-2": current_key,
            },
        )
        current_token = self.issue(session, configuration=rotated_configuration)

        for signer, token in (("old", old_token), ("current", current_token)):
            with self.subTest(signer=signer):
                with self.assertNumQueries(1):
                    user, context = bind_v2_access(
                        token,
                        source=V2AccessSource.BROWSER_COOKIE,
                        configuration=rotated_configuration,
                        clock=lambda: self.now,
                    )
                self.assertEqual(user.pk, self.user.pk)
                self.assertEqual(context.session_id, session.uuid)

        current_only_configuration = resolve_access_config(
            V2KeyMaterial(access_signing_key=current_key, refresh_hmac_key=b"r" * 32),
            current_kid="ledova-v2-access-hs256-2",
            verifier_keys={"ledova-v2-access-hs256-2": current_key},
        )
        with self.assertNumQueries(0):
            with self.assertRaisesMessage(AccessTokenError, "Invalid v2 access token."):
                bind_v2_access(
                    old_token,
                    source=V2AccessSource.BROWSER_COOKIE,
                    configuration=current_only_configuration,
                    clock=lambda: self.now,
                )

    def test_source_requires_the_explicit_enum_and_clock_is_sampled_once(self):
        session = self.create_session()
        token = self.issue(session)
        clock_calls = []

        def clock():
            clock_calls.append(self.now)
            return self.now

        with self.assertRaisesMessage(TypeError, "Invalid v2 access source."):
            bind_v2_access(
                token,
                source="browser_cookie",
                configuration=self.configuration,
                clock=clock,
            )
        self.assertEqual(clock_calls, [])

        with self.assertNumQueries(1):
            bind_v2_access(
                token,
                source=V2AccessSource.BROWSER_COOKIE,
                configuration=self.configuration,
                clock=clock,
            )
        self.assertEqual(clock_calls, [self.now])

    def test_binding_is_read_only_and_the_context_is_immutable_and_redacted(self):
        session = self.create_session()
        token = self.issue(session)
        original_updated_at = session.updated_at
        original_last_used_at = session.last_used_at

        user, context = self.bind(token, V2AccessSource.BROWSER_COOKIE)

        session.refresh_from_db()
        user.refresh_from_db()
        self.assertEqual(session.updated_at, original_updated_at)
        self.assertEqual(session.last_used_at, original_last_used_at)
        self.assertIsNone(user.last_login)
        with self.assertRaises(FrozenInstanceError):
            context.session_id = uuid.uuid4()
        rendered = repr(context)
        self.assertNotIn(str(session.uuid), rendered)
        self.assertNotIn(token, rendered)
        self.assertNotIn(str(self.user.pk), rendered)

    def test_database_failures_propagate_without_becoming_authentication_rejections(self):
        session = self.create_session()
        token = self.issue(session)

        with patch(
            "authentication.services.v2_access.AuthSession.objects.select_related",
            side_effect=OperationalError("synthetic database failure"),
        ):
            with self.assertRaisesMessage(OperationalError, "synthetic database failure"):
                self.bind(token, V2AccessSource.BROWSER_COOKIE)

    def test_configuration_failures_propagate_before_database_access(self):
        session = self.create_session()
        token = self.issue(session)

        with self.assertNumQueries(0):
            with self.assertRaisesMessage(
                AccessTokenConfigurationError,
                "Invalid v2 access token configuration.",
            ):
                bind_v2_access(
                    token,
                    source=V2AccessSource.BROWSER_COOKIE,
                    configuration=object(),
                    clock=lambda: self.now,
                )
