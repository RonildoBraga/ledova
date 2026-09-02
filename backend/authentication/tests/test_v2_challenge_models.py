from datetime import UTC, datetime, timedelta

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db import DataError, IntegrityError, transaction
from django.db.models import NOT_PROVIDED
from django.db.models.deletion import ProtectedError
from django.test import TestCase

from authentication.models import (
    AuthenticationChallenge,
    AuthenticationChallengeDelivery,
)

User = get_user_model()
DEFAULT_RELATION = object()


class V2ChallengeModelTest(TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 2, 10, 0, tzinfo=UTC)
        self.user_sequence = 0

    def create_user(self):
        self.user_sequence += 1
        return User.objects.create_user(
            email=f"challenge-owner-{self.user_sequence}@example.test",
            password="synthetic-test-password",
            is_active=True,
        )

    def challenge_values(self, **overrides):
        purpose = overrides.get("purpose", AuthenticationChallenge.Purpose.SIGNUP)
        status = overrides.get("status", AuthenticationChallenge.Status.OPEN)
        user = overrides.pop("user", DEFAULT_RELATION)
        if user is DEFAULT_RELATION:
            user = self.create_user()
        values = {
            "user": user,
            "purpose": purpose,
            "transport": AuthenticationChallenge.Transport.BROWSER,
            "status": status,
            "pending_context_key_id": "synthetic-proof-key-1",
            "pending_context_digest": b"c" * 32,
            "target_email": None,
            "otp_failure_count": 5 if status == AuthenticationChallenge.Status.EXHAUSTED else 0,
            "created_at": self.now,
            "expires_at": self.now + timedelta(hours=1),
            "resolved_at": None if status == AuthenticationChallenge.Status.OPEN else self.now + timedelta(minutes=1),
        }
        if purpose == AuthenticationChallenge.Purpose.PASSWORD_RESET:
            values["pending_context_key_id"] = None
            values["pending_context_digest"] = None
        if purpose == AuthenticationChallenge.Purpose.EMAIL_CHANGE and status == AuthenticationChallenge.Status.OPEN:
            values["target_email"] = "new-owner@example.test"
        values.update(overrides)
        return values

    def create_challenge(self, **overrides):
        return AuthenticationChallenge.objects.create(**self.challenge_values(**overrides))

    def delivery_values(self, challenge=DEFAULT_RELATION, **overrides):
        purpose = overrides.get("purpose", AuthenticationChallengeDelivery.Purpose.SIGNUP)
        status = overrides.get("status", AuthenticationChallengeDelivery.Status.RESERVED)
        if challenge is DEFAULT_RELATION:
            challenge_purpose = (
                purpose
                if purpose in AuthenticationChallengeDelivery.Purpose.values
                else AuthenticationChallenge.Purpose.SIGNUP
            )
            challenge = self.create_challenge(purpose=challenge_purpose)

        unsent_statuses = {
            AuthenticationChallengeDelivery.Status.RESERVED,
            AuthenticationChallengeDelivery.Status.SUPPRESSED,
        }
        sent_statuses = {
            AuthenticationChallengeDelivery.Status.SENDING,
            AuthenticationChallengeDelivery.Status.AMBIGUOUS,
            AuthenticationChallengeDelivery.Status.REJECTED,
            AuthenticationChallengeDelivery.Status.ABANDONED,
        }
        terminal_statuses = {
            AuthenticationChallengeDelivery.Status.REJECTED,
            AuthenticationChallengeDelivery.Status.ABANDONED,
            AuthenticationChallengeDelivery.Status.SUPPRESSED,
            AuthenticationChallengeDelivery.Status.SUPERSEDED,
            AuthenticationChallengeDelivery.Status.CONSUMED,
            AuthenticationChallengeDelivery.Status.EXHAUSTED,
            AuthenticationChallengeDelivery.Status.EXPIRED,
            AuthenticationChallengeDelivery.Status.INVALIDATED,
        }
        values = {
            "challenge": challenge,
            "purpose": purpose,
            "status": status,
            "rate_key_id": "synthetic-rate-key-1",
            "destination_rate_digest": b"d" * 32,
            "ip_rate_digest": b"i" * 32,
            "proof_key_id": None,
            "proof_digest": None,
            "reserved_at": self.now,
            "lease_expires_at": self.now + timedelta(seconds=120),
            "sending_at": None,
            "accepted_at": None,
            "proof_expires_at": None,
            "resolved_at": self.now + timedelta(seconds=3) if status in terminal_statuses else None,
        }
        if status in sent_statuses or status not in unsent_statuses:
            values["proof_key_id"] = "synthetic-proof-key-1"
            values["proof_digest"] = b"p" * 32
            values["sending_at"] = self.now + timedelta(seconds=1)
        if status not in unsent_statuses | sent_statuses:
            values["accepted_at"] = self.now + timedelta(seconds=2)
            values["proof_expires_at"] = self.now + timedelta(minutes=10)
        values.update(overrides)
        return values

    def create_delivery(self, challenge=DEFAULT_RELATION, **overrides):
        return AuthenticationChallengeDelivery.objects.create(**self.delivery_values(challenge=challenge, **overrides))

    def assert_challenge_rejected(self, **overrides):
        values = self.challenge_values(**overrides)
        with self.assertRaises((DataError, IntegrityError)), transaction.atomic():
            AuthenticationChallenge.objects.create(**values)

    def assert_delivery_rejected(self, challenge=DEFAULT_RELATION, **overrides):
        values = self.delivery_values(challenge=challenge, **overrides)
        with self.assertRaises((DataError, IntegrityError)), transaction.atomic():
            AuthenticationChallengeDelivery.objects.create(**values)

    def test_representative_challenge_states_are_valid(self):
        vectors = [
            {
                "purpose": AuthenticationChallenge.Purpose.SIGNUP,
                "transport": AuthenticationChallenge.Transport.BROWSER,
                "status": AuthenticationChallenge.Status.OPEN,
            },
            {
                "purpose": AuthenticationChallenge.Purpose.EMAIL_CHANGE,
                "transport": AuthenticationChallenge.Transport.NATIVE,
                "status": AuthenticationChallenge.Status.OPEN,
            },
            {
                "purpose": AuthenticationChallenge.Purpose.PASSWORD_RESET,
                "status": AuthenticationChallenge.Status.OPEN,
            },
            {
                "purpose": AuthenticationChallenge.Purpose.SIGNUP,
                "status": AuthenticationChallenge.Status.CONSUMED,
            },
            {
                "purpose": AuthenticationChallenge.Purpose.SIGNUP,
                "status": AuthenticationChallenge.Status.EXHAUSTED,
            },
            {
                "purpose": AuthenticationChallenge.Purpose.EMAIL_CHANGE,
                "status": AuthenticationChallenge.Status.SUPERSEDED,
            },
        ]

        created = [self.create_challenge(**vector) for vector in vectors]

        self.assertEqual(len(created), len(vectors))
        self.assertIsNone(created[2].pending_context_digest)
        self.assertEqual(created[4].otp_failure_count, 5)
        self.assertIsNone(created[5].target_email)

    def test_challenge_choice_context_and_digest_constraints_reject_invalid_rows(self):
        vectors = [
            {"purpose": "unknown"},
            {"transport": "unknown"},
            {"status": "unknown"},
            {"pending_context_key_id": None},
            {"pending_context_digest": None},
            {"pending_context_key_id": ""},
            {"pending_context_key_id": "invalid key"},
            {"pending_context_key_id": "k" * 65},
            {"pending_context_digest": b"c" * 31},
            {
                "purpose": AuthenticationChallenge.Purpose.PASSWORD_RESET,
                "pending_context_key_id": "synthetic-proof-key-1",
                "pending_context_digest": b"c" * 32,
            },
        ]

        for vector in vectors:
            with self.subTest(vector=vector):
                self.assert_challenge_rejected(**vector)

    def test_challenge_target_and_failure_constraints_reject_invalid_rows(self):
        vectors = [
            {"purpose": AuthenticationChallenge.Purpose.EMAIL_CHANGE, "target_email": None},
            {"target_email": "other-owner@example.test"},
            {
                "purpose": AuthenticationChallenge.Purpose.EMAIL_CHANGE,
                "target_email": "New-Owner@example.test",
            },
            {
                "purpose": AuthenticationChallenge.Purpose.EMAIL_CHANGE,
                "target_email": "néw-owner@example.test",
            },
            {
                "purpose": AuthenticationChallenge.Purpose.EMAIL_CHANGE,
                "status": AuthenticationChallenge.Status.CONSUMED,
                "target_email": "new-owner@example.test",
            },
            {"otp_failure_count": 6},
            {"purpose": AuthenticationChallenge.Purpose.PASSWORD_RESET, "otp_failure_count": 1},
            {"status": AuthenticationChallenge.Status.EXHAUSTED, "otp_failure_count": 4},
            {"status": AuthenticationChallenge.Status.OPEN, "otp_failure_count": 5},
            {
                "purpose": AuthenticationChallenge.Purpose.PASSWORD_RESET,
                "status": AuthenticationChallenge.Status.EXHAUSTED,
            },
            {"status": AuthenticationChallenge.Status.SUPERSEDED},
        ]

        for vector in vectors:
            with self.subTest(vector=vector):
                self.assert_challenge_rejected(**vector)

    def test_challenge_resolution_and_time_constraints_reject_invalid_rows(self):
        vectors = [
            {"resolved_at": self.now + timedelta(seconds=1)},
            {"status": AuthenticationChallenge.Status.CONSUMED, "resolved_at": None},
            {"expires_at": self.now},
            {
                "status": AuthenticationChallenge.Status.CONSUMED,
                "resolved_at": self.now - timedelta(seconds=1),
            },
        ]

        for vector in vectors:
            with self.subTest(vector=vector):
                self.assert_challenge_rejected(**vector)

    def test_only_one_open_challenge_per_user_and_purpose_is_allowed(self):
        user = self.create_user()
        original = self.create_challenge(user=user)

        self.assert_challenge_rejected(user=user)
        terminal = self.create_challenge(
            user=user,
            status=AuthenticationChallenge.Status.CONSUMED,
        )
        other_purpose = self.create_challenge(
            user=user,
            purpose=AuthenticationChallenge.Purpose.PASSWORD_RESET,
        )

        self.assertEqual(original.user, user)
        self.assertEqual(terminal.user, user)
        self.assertEqual(other_purpose.user, user)

    def test_representative_delivery_lineages_are_valid(self):
        vectors = [
            {"status": AuthenticationChallengeDelivery.Status.RESERVED},
            {"status": AuthenticationChallengeDelivery.Status.SENDING},
            {"status": AuthenticationChallengeDelivery.Status.AMBIGUOUS},
            {"status": AuthenticationChallengeDelivery.Status.ACTIVE},
            {"status": AuthenticationChallengeDelivery.Status.REJECTED},
            {"status": AuthenticationChallengeDelivery.Status.CONSUMED},
            {"status": AuthenticationChallengeDelivery.Status.EXHAUSTED},
            {
                "challenge": None,
                "status": AuthenticationChallengeDelivery.Status.SUPPRESSED,
                "destination_rate_digest": None,
            },
            {
                "status": AuthenticationChallengeDelivery.Status.ABANDONED,
                "proof_key_id": None,
                "proof_digest": None,
                "sending_at": None,
            },
        ]

        created = [self.create_delivery(**vector) for vector in vectors]

        self.assertEqual(len(created), len(vectors))
        self.assertIsNone(created[7].destination_rate_digest)
        self.assertIsNone(created[8].proof_digest)

    def test_delivery_choice_digest_and_purpose_constraints_reject_invalid_rows(self):
        vectors = [
            {"purpose": "unknown"},
            {"status": "unknown"},
            {"rate_key_id": ""},
            {"rate_key_id": "invalid key"},
            {"rate_key_id": "k" * 65},
            {"ip_rate_digest": b"i" * 31},
            {"destination_rate_digest": b"d" * 31},
            {"destination_rate_digest": None},
            {
                "status": AuthenticationChallengeDelivery.Status.SENDING,
                "proof_digest": b"p" * 31,
            },
            {
                "status": AuthenticationChallengeDelivery.Status.SENDING,
                "proof_key_id": "",
            },
            {
                "status": AuthenticationChallengeDelivery.Status.SENDING,
                "proof_key_id": "invalid key",
            },
            {
                "purpose": AuthenticationChallengeDelivery.Purpose.PASSWORD_RESET,
                "status": AuthenticationChallengeDelivery.Status.EXHAUSTED,
            },
            {
                "purpose": AuthenticationChallengeDelivery.Purpose.PASSWORD_RESET,
                "status": AuthenticationChallengeDelivery.Status.SUPPRESSED,
                "destination_rate_digest": None,
            },
            {"challenge": None},
        ]

        for vector in vectors:
            with self.subTest(vector=vector):
                self.assert_delivery_rejected(**vector)

    def test_delivery_proof_and_resolution_constraints_reject_invalid_rows(self):
        vectors = [
            {
                "status": AuthenticationChallengeDelivery.Status.RESERVED,
                "proof_key_id": "synthetic-proof-key-1",
                "proof_digest": b"p" * 32,
            },
            {
                "status": AuthenticationChallengeDelivery.Status.SENDING,
                "proof_digest": None,
            },
            {
                "status": AuthenticationChallengeDelivery.Status.ACTIVE,
                "accepted_at": None,
            },
            {
                "status": AuthenticationChallengeDelivery.Status.SUPPRESSED,
                "proof_key_id": "synthetic-proof-key-1",
                "proof_digest": b"p" * 32,
                "sending_at": self.now + timedelta(seconds=1),
            },
            {
                "status": AuthenticationChallengeDelivery.Status.ACTIVE,
                "resolved_at": self.now + timedelta(seconds=3),
            },
            {
                "status": AuthenticationChallengeDelivery.Status.REJECTED,
                "resolved_at": None,
            },
        ]

        for vector in vectors:
            with self.subTest(vector=vector):
                self.assert_delivery_rejected(**vector)

    def test_delivery_time_constraints_reject_invalid_rows(self):
        vectors = [
            {"lease_expires_at": self.now},
            {
                "status": AuthenticationChallengeDelivery.Status.SENDING,
                "sending_at": self.now - timedelta(seconds=1),
            },
            {
                "status": AuthenticationChallengeDelivery.Status.SENDING,
                "sending_at": self.now + timedelta(seconds=120),
            },
            {
                "status": AuthenticationChallengeDelivery.Status.ACTIVE,
                "accepted_at": self.now,
            },
            {
                "status": AuthenticationChallengeDelivery.Status.ACTIVE,
                "accepted_at": self.now + timedelta(seconds=120),
            },
            {
                "status": AuthenticationChallengeDelivery.Status.ACTIVE,
                "proof_expires_at": self.now + timedelta(seconds=2),
            },
            {
                "status": AuthenticationChallengeDelivery.Status.SUPPRESSED,
                "resolved_at": self.now - timedelta(seconds=1),
            },
            {
                "status": AuthenticationChallengeDelivery.Status.REJECTED,
                "resolved_at": self.now,
            },
            {
                "status": AuthenticationChallengeDelivery.Status.CONSUMED,
                "resolved_at": self.now + timedelta(seconds=1),
            },
        ]

        for vector in vectors:
            with self.subTest(vector=vector):
                self.assert_delivery_rejected(**vector)

    def test_one_active_and_one_inflight_delivery_can_coexist_but_not_duplicate(self):
        challenge = self.create_challenge()
        active = self.create_delivery(
            challenge=challenge,
            status=AuthenticationChallengeDelivery.Status.ACTIVE,
        )
        reserved = self.create_delivery(
            challenge=challenge,
            status=AuthenticationChallengeDelivery.Status.RESERVED,
        )

        self.assert_delivery_rejected(
            challenge=challenge,
            status=AuthenticationChallengeDelivery.Status.ACTIVE,
        )
        self.assert_delivery_rejected(
            challenge=challenge,
            status=AuthenticationChallengeDelivery.Status.SENDING,
        )
        rejected = self.create_delivery(
            challenge=challenge,
            status=AuthenticationChallengeDelivery.Status.REJECTED,
        )
        abandoned = self.create_delivery(
            challenge=challenge,
            status=AuthenticationChallengeDelivery.Status.ABANDONED,
        )

        self.assertEqual(active.challenge, challenge)
        self.assertEqual(reserved.challenge, challenge)
        self.assertEqual(rejected.challenge, challenge)
        self.assertEqual(abandoned.challenge, challenge)

    def test_delivery_evidence_survives_challenge_deletion(self):
        challenge = self.create_challenge(status=AuthenticationChallenge.Status.CONSUMED)
        delivery = self.create_delivery(
            challenge=challenge,
            status=AuthenticationChallengeDelivery.Status.CONSUMED,
        )
        expected_purpose = delivery.purpose
        expected_destination_digest = bytes(delivery.destination_rate_digest)
        expected_ip_digest = bytes(delivery.ip_rate_digest)

        challenge.delete()

        delivery.refresh_from_db()
        self.assertIsNone(delivery.challenge)
        self.assertEqual(delivery.purpose, expected_purpose)
        self.assertEqual(bytes(delivery.destination_rate_digest), expected_destination_digest)
        self.assertEqual(bytes(delivery.ip_rate_digest), expected_ip_digest)

    def test_retained_challenge_protects_its_user_from_hard_deletion(self):
        user = self.create_user()
        challenge = self.create_challenge(user=user)

        with self.assertRaises(ProtectedError), transaction.atomic():
            user.delete()

        self.assertTrue(User.objects.filter(pk=user.pk).exists())
        self.assertTrue(AuthenticationChallenge.objects.filter(pk=challenge.pk).exists())

    def test_timestamp_fields_are_explicit_and_preserve_supplied_values(self):
        challenge_timestamp_fields = {"created_at", "expires_at", "resolved_at"}
        delivery_timestamp_fields = {
            "reserved_at",
            "lease_expires_at",
            "sending_at",
            "accepted_at",
            "proof_expires_at",
            "resolved_at",
        }
        for model, field_names in [
            (AuthenticationChallenge, challenge_timestamp_fields),
            (AuthenticationChallengeDelivery, delivery_timestamp_fields),
        ]:
            for field_name in field_names:
                field = model._meta.get_field(field_name)
                self.assertFalse(field.auto_now)
                self.assertFalse(field.auto_now_add)
                self.assertIs(field.default, NOT_PROVIDED)

        challenge = self.create_challenge()
        delivery = self.create_delivery(
            challenge=challenge,
            status=AuthenticationChallengeDelivery.Status.ACTIVE,
        )
        challenge.refresh_from_db()
        delivery.refresh_from_db()

        self.assertEqual(challenge.created_at, self.now)
        self.assertEqual(challenge.expires_at, self.now + timedelta(hours=1))
        self.assertEqual(delivery.reserved_at, self.now)
        self.assertEqual(delivery.lease_expires_at, self.now + timedelta(seconds=120))
        self.assertEqual(delivery.sending_at, self.now + timedelta(seconds=1))
        self.assertEqual(delivery.accepted_at, self.now + timedelta(seconds=2))
        self.assertEqual(delivery.proof_expires_at, self.now + timedelta(minutes=10))

    def test_models_exclude_plaintext_credentials_addresses_and_provider_data(self):
        challenge_fields = {field.name for field in AuthenticationChallenge._meta.fields}
        delivery_fields = {field.name for field in AuthenticationChallengeDelivery._meta.fields}
        forbidden_challenge_fields = {
            "context",
            "context_secret",
            "destination",
            "ip_address",
            "otp",
            "otp_code",
            "password_reset_credential",
            "provider_id",
            "provider_message_id",
            "provider_payload",
            "provider_response_body",
            "provider_status",
            "raw_destination",
            "raw_ip",
            "reset_secret",
            "target_address",
        }
        forbidden_delivery_fields = forbidden_challenge_fields | {
            "destination_email",
            "predecessor",
            "provider_error",
            "provider_response",
            "reset_credential",
            "target_email",
        }

        self.assertFalse(challenge_fields & forbidden_challenge_fields)
        self.assertFalse(delivery_fields & forbidden_delivery_fields)
        self.assertIn("target_email", challenge_fields)
        self.assertIn("destination_rate_digest", delivery_fields)
        self.assertIn("ip_rate_digest", delivery_fields)
        self.assertIn("proof_digest", delivery_fields)

    def test_representations_are_redacted_and_models_are_absent_from_admin(self):
        challenge = self.create_challenge(
            purpose=AuthenticationChallenge.Purpose.EMAIL_CHANGE,
            target_email="private-marker@example.test",
        )
        delivery = self.create_delivery(
            challenge=challenge,
            status=AuthenticationChallengeDelivery.Status.ACTIVE,
        )

        self.assertEqual(str(challenge), "AuthenticationChallenge(<redacted>)")
        self.assertEqual(repr(challenge), "AuthenticationChallenge(<redacted>)")
        self.assertEqual(str(delivery), "AuthenticationChallengeDelivery(<redacted>)")
        self.assertEqual(repr(delivery), "AuthenticationChallengeDelivery(<redacted>)")
        rendered = " ".join([str(challenge), repr(challenge), str(delivery), repr(delivery)])
        for private_value in [
            str(challenge.uuid),
            str(delivery.uuid),
            challenge.target_email,
            challenge.pending_context_key_id,
            delivery.rate_key_id,
            delivery.proof_key_id,
        ]:
            self.assertNotIn(private_value, rendered)
        self.assertFalse(admin.site.is_registered(AuthenticationChallenge))
        self.assertFalse(admin.site.is_registered(AuthenticationChallengeDelivery))
