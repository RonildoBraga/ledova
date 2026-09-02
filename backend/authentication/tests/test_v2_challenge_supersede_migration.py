from datetime import UTC, datetime, timedelta
from importlib import import_module
from unittest import skipUnless
from unittest.mock import patch
from uuid import UUID

from django.conf import settings
from django.db import IntegrityError, connection, migrations, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder
from django.test import TransactionTestCase

MIGRATE_FROM = [("authentication", "0004_v2_challenge_schema")]
MIGRATE_TO = [("authentication", "0005_auth_del_superseded_proof_shapes")]
MIGRATE_LATEST = MIGRATE_TO
MIGRATION_NAME = "0005_auth_del_superseded_proof_shapes"
PROOF_CONSTRAINT_NAME = "auth_del_proof_state"
PURPOSE_CONSTRAINT_NAME = "auth_del_supersede_purpose"
DELIVERY_TABLE = "authentication_challenge_delivery"
_migration_modules = getattr(settings, "MIGRATION_MODULES", {})
MIGRATIONS_ENABLED = not ("authentication" in _migration_modules and _migration_modules["authentication"] is None)


@skipUnless(MIGRATIONS_ENABLED, "Migration execution is required")
class V2ChallengeSupersedeMigrationTest(TransactionTestCase):
    reset_sequences = False
    now = datetime(2026, 9, 2, 14, 0, tzinfo=UTC)

    def setUp(self):
        super().setUp()
        self.addCleanup(self.restore_latest_schema)
        self.old_apps = self.migrate(MIGRATE_FROM)
        self.old_user = self.old_apps.get_model("authentication", "CustomUser")
        self.old_challenge = self.old_apps.get_model("authentication", "AuthenticationChallenge")
        self.old_delivery = self.old_apps.get_model("authentication", "AuthenticationChallengeDelivery")

    def migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    def restore_latest_schema(self):
        self.migrate(MIGRATE_LATEST)

    def create_challenge(self, ordinal, purpose="signup"):
        user = self.old_user._base_manager.create(
            email=f"migration-owner-{ordinal}@example.test",
            password="!",
        )
        values = {
            "uuid": UUID(f"10000000-0000-4000-8000-{ordinal:012d}"),
            "user_id": user.pk,
            "purpose": purpose,
            "transport": "browser",
            "status": "open",
            "pending_context_key_id": "synthetic-proof-key-1",
            "pending_context_digest": bytes([ordinal]) * 32,
            "otp_failure_count": 0,
            "created_at": self.now,
            "expires_at": self.now + timedelta(hours=2),
        }
        if purpose == "email_change":
            values["target_email"] = f"new-owner-{ordinal}@example.test"
        if purpose == "password_reset":
            values["pending_context_key_id"] = None
            values["pending_context_digest"] = None
        return self.old_challenge._base_manager.create(**values)

    def delivery_values(self, status, ordinal, purpose="signup"):
        values = {
            "uuid": UUID(f"20000000-0000-4000-8000-{ordinal:012d}"),
            "challenge_id": self.create_challenge(ordinal, purpose).pk,
            "purpose": purpose,
            "status": status,
            "rate_key_id": "synthetic-rate-key-1",
            "destination_rate_digest": bytes([ordinal + 16]) * 32,
            "ip_rate_digest": bytes([ordinal + 32]) * 32,
            "reserved_at": self.now,
            "lease_expires_at": self.now + timedelta(minutes=10),
        }
        if status in {"sending", "ambiguous", "active"}:
            values.update(
                proof_key_id="synthetic-proof-key-1",
                proof_digest=bytes([ordinal + 48]) * 32,
                sending_at=self.now + timedelta(seconds=10),
            )
        if status == "active":
            values.update(
                accepted_at=self.now + timedelta(seconds=20),
                proof_expires_at=self.now + timedelta(hours=1),
            )
        return values

    def create_delivery(self, status, ordinal, purpose="signup"):
        return self.old_delivery._base_manager.create(**self.delivery_values(status, ordinal, purpose))

    def delivery_snapshot(self, delivery):
        return (
            delivery.status,
            delivery.challenge_id,
            delivery.purpose,
            delivery.rate_key_id,
            bytes(delivery.destination_rate_digest),
            bytes(delivery.ip_rate_digest),
            delivery.proof_key_id,
            None if delivery.proof_digest is None else bytes(delivery.proof_digest),
            delivery.reserved_at,
            delivery.lease_expires_at,
            delivery.sending_at,
            delivery.accepted_at,
            delivery.proof_expires_at,
            delivery.resolved_at,
        )

    def test_migration_is_atomic_and_exactly_replaces_the_named_constraint(self):
        migration = import_module("authentication.migrations.0005_auth_del_superseded_proof_shapes").Migration
        operations = migration.operations

        self.assertTrue(migration.atomic)
        self.assertEqual(migration.dependencies, MIGRATE_FROM)
        self.assertEqual(len(operations), 3)
        self.assertIsInstance(operations[0], migrations.RemoveConstraint)
        self.assertEqual(
            (operations[0].model_name, operations[0].name),
            ("authenticationchallengedelivery", PROOF_CONSTRAINT_NAME),
        )
        self.assertIsInstance(operations[1], migrations.AddConstraint)
        self.assertEqual(
            (operations[1].model_name, operations[1].constraint.name),
            ("authenticationchallengedelivery", PROOF_CONSTRAINT_NAME),
        )
        self.assertIsInstance(operations[2], migrations.AddConstraint)
        self.assertEqual(
            (operations[2].model_name, operations[2].constraint.name),
            ("authenticationchallengedelivery", PURPOSE_CONSTRAINT_NAME),
        )

    def test_forward_and_reverse_preserve_every_existing_proof_shape(self):
        deliveries = [
            self.create_delivery(status, ordinal)
            for ordinal, status in enumerate(("reserved", "sending", "ambiguous", "active"), start=1)
        ]
        expected = {delivery.pk: self.delivery_snapshot(delivery) for delivery in deliveries}

        current_apps = self.migrate(MIGRATE_TO)
        current_delivery = current_apps.get_model("authentication", "AuthenticationChallengeDelivery")
        self.assertEqual(
            {
                delivery.pk: self.delivery_snapshot(delivery)
                for delivery in current_delivery._base_manager.order_by("uuid")
            },
            expected,
        )

        reversed_apps = self.migrate(MIGRATE_FROM)
        reversed_delivery = reversed_apps.get_model("authentication", "AuthenticationChallengeDelivery")
        self.assertEqual(
            {
                delivery.pk: self.delivery_snapshot(delivery)
                for delivery in reversed_delivery._base_manager.order_by("uuid")
            },
            expected,
        )

    def test_every_valid_proof_shape_can_transition_to_superseded(self):
        vectors = (
            ("reserved", "email_change"),
            ("sending", "email_change"),
            ("ambiguous", "email_change"),
            ("active", "signup"),
            ("active", "email_change"),
            ("active", "password_reset"),
        )
        deliveries = [
            self.create_delivery(status, ordinal, purpose) for ordinal, (status, purpose) in enumerate(vectors, start=5)
        ]
        preserved = {delivery.pk: self.delivery_snapshot(delivery)[1:13] for delivery in deliveries}
        current_apps = self.migrate(MIGRATE_TO)
        current_delivery = current_apps.get_model("authentication", "AuthenticationChallengeDelivery")
        resolved_at = self.now + timedelta(minutes=1)

        for delivery in deliveries:
            with self.subTest(status=delivery.status):
                updated = current_delivery._base_manager.filter(pk=delivery.pk).update(
                    status="superseded",
                    resolved_at=resolved_at,
                )
                self.assertEqual(updated, 1)
                stored = current_delivery._base_manager.get(pk=delivery.pk)
                self.assertEqual(stored.status, "superseded")
                self.assertEqual(stored.resolved_at, resolved_at)
                self.assertEqual(
                    self.delivery_snapshot(stored)[1:13],
                    preserved[delivery.pk],
                )

    def test_malformed_mixed_superseded_proof_shapes_remain_rejected(self):
        current_apps = self.migrate(MIGRATE_TO)
        current_delivery = current_apps.get_model("authentication", "AuthenticationChallengeDelivery")
        malformed = []

        proof_key_without_proof = self.delivery_values("reserved", 12, "email_change")
        proof_key_without_proof.update(
            status="superseded",
            proof_key_id="synthetic-proof-key-1",
            resolved_at=self.now + timedelta(minutes=1),
        )
        malformed.append(proof_key_without_proof)

        proof_without_sending = self.delivery_values("reserved", 13, "email_change")
        proof_without_sending.update(
            status="superseded",
            proof_key_id="synthetic-proof-key-1",
            proof_digest=b"p" * 32,
            resolved_at=self.now + timedelta(minutes=1),
        )
        malformed.append(proof_without_sending)

        accepted_without_expiry = self.delivery_values("sending", 14, "email_change")
        accepted_without_expiry.update(
            status="superseded",
            accepted_at=self.now + timedelta(seconds=20),
            resolved_at=self.now + timedelta(minutes=1),
        )
        malformed.append(accepted_without_expiry)

        expiry_without_acceptance = self.delivery_values("sending", 15, "email_change")
        expiry_without_acceptance.update(
            status="superseded",
            proof_expires_at=self.now + timedelta(hours=1),
            resolved_at=self.now + timedelta(minutes=1),
        )
        malformed.append(expiry_without_acceptance)

        for values in malformed:
            with self.subTest(uuid=str(values["uuid"])):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    current_delivery._base_manager.create(**values)

        self.assertFalse(
            current_delivery._base_manager.filter(pk__in=[values["uuid"] for values in malformed]).exists()
        )

    def test_unaccepted_supersession_is_rejected_for_other_purposes(self):
        deliveries = [
            self.create_delivery(status, ordinal, purpose)
            for ordinal, (purpose, status) in enumerate(
                (
                    ("signup", "reserved"),
                    ("signup", "sending"),
                    ("signup", "ambiguous"),
                    ("password_reset", "reserved"),
                    ("password_reset", "sending"),
                    ("password_reset", "ambiguous"),
                ),
                start=16,
            )
        ]
        current_apps = self.migrate(MIGRATE_TO)
        current_delivery = current_apps.get_model("authentication", "AuthenticationChallengeDelivery")

        for delivery in deliveries:
            with self.subTest(purpose=delivery.purpose, status=delivery.status):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    current_delivery._base_manager.filter(pk=delivery.pk).update(
                        status="superseded",
                        resolved_at=self.now + timedelta(minutes=1),
                    )

    @skipUnless(connection.features.can_rollback_ddl, "Transactional DDL is required")
    def test_add_constraint_failure_rolls_back_removal_data_and_recorder(self):
        delivery = self.create_delivery("reserved", 22)
        expected = self.delivery_snapshot(delivery)
        original_forwards = migrations.AddConstraint.database_forwards

        def fail_new_constraint(operation, app_label, schema_editor, from_state, to_state):
            if operation.constraint.name == PROOF_CONSTRAINT_NAME:
                raise RuntimeError("Synthetic supersede migration failure.")
            return original_forwards(operation, app_label, schema_editor, from_state, to_state)

        with patch.object(
            migrations.AddConstraint,
            "database_forwards",
            new=fail_new_constraint,
        ):
            with self.assertRaisesRegex(RuntimeError, r"^Synthetic supersede migration failure\.$"):
                self.migrate(MIGRATE_TO)

        self.assertFalse(
            MigrationRecorder(connection).migration_qs.filter(app="authentication", name=MIGRATION_NAME).exists()
        )
        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(cursor, DELIVERY_TABLE)
        self.assertTrue(constraints[PROOF_CONSTRAINT_NAME]["check"])
        stored = self.old_delivery._base_manager.get(pk=delivery.pk)
        self.assertEqual(self.delivery_snapshot(stored), expected)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.old_delivery._base_manager.filter(pk=delivery.pk).update(
                status="superseded",
                resolved_at=self.now + timedelta(minutes=1),
            )

        self.migrate(MIGRATE_TO)

        self.assertTrue(
            MigrationRecorder(connection).migration_qs.filter(app="authentication", name=MIGRATION_NAME).exists()
        )
