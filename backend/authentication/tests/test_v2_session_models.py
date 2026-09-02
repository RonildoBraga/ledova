import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import RestrictedError
from django.test import TestCase
from django.utils import timezone

from authentication.models import AuthSession, RefreshCredential
from authentication.security.v2_credentials import refresh_secret_digest

User = get_user_model()


class V2SessionModelTest(TestCase):
    refresh_key = b"k" * 32
    refresh_secret = b"s" * 32

    def setUp(self):
        self.now = timezone.now()
        self.user = User.objects.create_user(
            email="session-owner@example.test",
            password="test-password-123",
            is_active=True,
        )

    def create_session(self, **overrides):
        values = {
            "user": self.user,
            "client_type": AuthSession.ClientType.BROWSER,
            "absolute_expires_at": self.now + timedelta(days=30),
        }
        values.update(overrides)
        return AuthSession.objects.create(**values)

    def create_credential(self, session, **overrides):
        selector = overrides.pop("uuid", uuid.uuid4())
        values = {
            "uuid": selector,
            "session": session,
            "secret_digest": refresh_secret_digest(selector, self.refresh_secret, self.refresh_key),
            "expires_at": self.now + timedelta(days=7),
        }
        values.update(overrides)
        return RefreshCredential.objects.create(**values)

    def test_session_and_credential_store_only_digest_material(self):
        session = self.create_session()
        credential = self.create_credential(session)

        session_fields = {field.name for field in AuthSession._meta.get_fields()}
        credential_fields = {field.name for field in RefreshCredential._meta.get_fields()}
        forbidden_fields = {"access_token", "access_jwt", "refresh_token", "refresh_secret", "secret"}

        self.assertFalse(session_fields & forbidden_fields)
        self.assertFalse(credential_fields & forbidden_fields)
        self.assertEqual(len(bytes(credential.secret_digest)), 32)
        self.assertNotEqual(bytes(credential.secret_digest), self.refresh_secret)
        self.assertEqual(session.refresh_credentials.get(), credential)

    def test_secret_matching_is_selector_bound_and_constant_time_compatible(self):
        session = self.create_session()
        credential = self.create_credential(session)

        self.assertTrue(credential.matches_secret(self.refresh_secret, self.refresh_key))
        self.assertFalse(credential.matches_secret(b"x" * 32, self.refresh_key))
        self.assertFalse(credential.matches_secret(self.refresh_secret, b"y" * 32))

    def test_digest_fields_require_exactly_32_bytes_during_validation(self):
        session = self.create_session()
        credential = self.create_credential(session)
        credential.secret_digest = b"x" * 31
        credential.confirmation_nonce_digest = b"y" * 31

        with self.assertRaises(ValidationError) as raised:
            credential.full_clean()

        self.assertIn("secret_digest", raised.exception.message_dict)
        self.assertIn("confirmation_nonce_digest", raised.exception.message_dict)

    def test_one_session_cannot_have_two_live_credentials(self):
        session = self.create_session()
        self.create_credential(session)

        with self.assertRaises(IntegrityError), transaction.atomic():
            self.create_credential(session)

    def test_spent_or_revoked_credentials_allow_one_successor(self):
        session = self.create_session()
        first = self.create_credential(session)
        first.used_at = self.now
        first.save(update_fields=["used_at"])

        second = self.create_credential(session)
        second.revoked_at = self.now
        second.save(update_fields=["revoked_at"])

        third = self.create_credential(session)
        self.assertEqual(
            RefreshCredential.objects.filter(
                session=session,
                used_at__isnull=True,
                revoked_at__isnull=True,
            ).get(),
            third,
        )

    def test_unspent_credential_cannot_reference_a_successor(self):
        session = self.create_session()
        predecessor = self.create_credential(session)
        successor = self.create_credential(session, used_at=self.now)
        predecessor.replaced_by = successor

        with self.assertRaises(IntegrityError), transaction.atomic():
            predecessor.save(update_fields=["replaced_by"])

    def test_credential_cannot_reference_itself_as_successor(self):
        session = self.create_session()
        credential = self.create_credential(session, used_at=self.now)
        credential.replaced_by = credential

        with self.assertRaises(IntegrityError), transaction.atomic():
            credential.save(update_fields=["replaced_by"])

    def test_replacement_from_another_session_fails_model_validation(self):
        session = self.create_session()
        other_session = self.create_session()
        predecessor = self.create_credential(session)
        predecessor.used_at = self.now
        predecessor.save(update_fields=["used_at"])
        successor = self.create_credential(other_session)
        predecessor.replaced_by = successor

        with self.assertRaises(ValidationError) as raised:
            predecessor.full_clean()

        self.assertIn("replaced_by", raised.exception.message_dict)

    def test_confirmation_state_requires_a_spent_predecessor_and_successor(self):
        session = self.create_session()
        predecessor = self.create_credential(session)
        predecessor.used_at = self.now
        predecessor.save(update_fields=["used_at"])
        successor = self.create_credential(session)
        predecessor.replaced_by = successor
        predecessor.save(update_fields=["replaced_by"])

        predecessor.confirmation_nonce_digest = b"n" * 32
        with self.assertRaises(IntegrityError), transaction.atomic():
            predecessor.save(update_fields=["confirmation_nonce_digest"])

        predecessor.confirmation_expires_at = self.now + timedelta(seconds=10)
        predecessor.save(update_fields=["confirmation_nonce_digest", "confirmation_expires_at"])
        predecessor.confirmation_consumed_at = self.now + timedelta(seconds=1)
        predecessor.save(update_fields=["confirmation_consumed_at"])

    def test_session_can_record_only_one_refresh_collision_confirmation(self):
        session = self.create_session()
        first = self.create_credential(session)
        first.used_at = self.now
        first.save(update_fields=["used_at"])
        second = self.create_credential(session)
        second.used_at = self.now
        second.save(update_fields=["used_at"])
        third = self.create_credential(session)

        first.replaced_by = second
        first.confirmation_nonce_digest = b"a" * 32
        first.confirmation_expires_at = self.now + timedelta(seconds=10)
        first.save(
            update_fields=[
                "replaced_by",
                "confirmation_nonce_digest",
                "confirmation_expires_at",
            ]
        )

        second.replaced_by = third
        second.confirmation_nonce_digest = b"b" * 32
        second.confirmation_expires_at = self.now + timedelta(seconds=10)
        with self.assertRaises(IntegrityError), transaction.atomic():
            second.save(
                update_fields=[
                    "replaced_by",
                    "confirmation_nonce_digest",
                    "confirmation_expires_at",
                ]
            )

    def test_session_state_constraint_enforces_revocation_metadata(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.create_session(status=AuthSession.Status.REVOKED)

        with self.assertRaises(IntegrityError), transaction.atomic():
            self.create_session(
                status=AuthSession.Status.ACTIVE,
                revoked_at=self.now,
                revoke_reason=AuthSession.RevokeReason.SIGNED_OUT,
            )

        revoked = self.create_session(
            status=AuthSession.Status.REVOKED,
            revoked_at=self.now,
            revoke_reason=AuthSession.RevokeReason.SIGNED_OUT,
        )
        pending = self.create_session(status=AuthSession.Status.REFRESH_CONFIRMATION_REQUIRED)
        self.assertTrue(revoked.is_revoked)
        self.assertFalse(pending.is_revoked)

    def test_session_choice_values_are_enforced_by_database_constraints(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.create_session(client_type="unknown")

        with self.assertRaises(IntegrityError), transaction.atomic():
            self.create_session(
                status=AuthSession.Status.REVOKED,
                revoked_at=self.now,
                revoke_reason="unknown",
            )

    def test_expiry_and_state_properties_are_boundary_safe(self):
        session = self.create_session(absolute_expires_at=self.now)
        credential = self.create_credential(session, expires_at=self.now)

        self.assertFalse(session.is_expired(self.now - timedelta(microseconds=1)))
        self.assertTrue(session.is_expired(self.now))
        self.assertFalse(credential.is_expired(self.now - timedelta(microseconds=1)))
        self.assertTrue(credential.is_expired(self.now))
        self.assertFalse(credential.is_spent)
        self.assertFalse(credential.is_revoked)

        credential.used_at = self.now
        credential.revoked_at = self.now
        self.assertTrue(credential.is_spent)
        self.assertTrue(credential.is_revoked)

    def test_hard_user_deletion_cascades_through_v2_credentials(self):
        session = self.create_session()
        self.create_credential(session)

        self.user.delete()

        self.assertFalse(AuthSession.objects.exists())
        self.assertFalse(RefreshCredential.objects.exists())

    def test_individual_successor_deletion_is_restricted_but_session_deletion_cascades(self):
        session = self.create_session()
        predecessor = self.create_credential(session)
        predecessor.used_at = self.now
        predecessor.save(update_fields=["used_at"])
        successor = self.create_credential(session)
        predecessor.replaced_by = successor
        predecessor.save(update_fields=["replaced_by"])

        with self.assertRaises(RestrictedError), transaction.atomic():
            successor.delete()

        session.delete()
        self.assertFalse(RefreshCredential.objects.exists())
