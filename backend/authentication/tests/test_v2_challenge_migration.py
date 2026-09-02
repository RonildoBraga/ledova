from datetime import UTC, datetime, timedelta
from importlib import import_module
from unittest import skipUnless
from unittest.mock import patch
from uuid import UUID

from django.conf import settings
from django.db import connection, migrations
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder
from django.test import TransactionTestCase

MIGRATE_FROM = [("authentication", "0003_customuser_v2_email_constraints")]
MIGRATE_TO = [("authentication", "0004_v2_challenge_schema")]
MIGRATION_NAME = "0004_v2_challenge_schema"
CHALLENGE_TABLE = "authentication_challenge"
DELIVERY_TABLE = "authentication_challenge_delivery"
CHALLENGE_INDEX_NAMES = [
    "auth_chal_user_state_idx",
    "auth_chal_expiry_idx",
    "auth_chal_ctx_key_idx",
]
DELIVERY_INDEX_NAMES = [
    "auth_del_chal_state_idx",
    "auth_del_lease_idx",
    "auth_del_cleanup_idx",
    "auth_del_dest_rate_idx",
    "auth_del_reset_rate_idx",
    "auth_del_ip_rate_idx",
    "auth_del_proof_key_idx",
]
CHALLENGE_CHECK_NAMES = [
    "auth_chal_purpose_valid",
    "auth_chal_transport_valid",
    "auth_chal_status_valid",
    "auth_chal_context_state",
    "auth_chal_context_len",
    "auth_chal_context_key",
    "auth_chal_target_state",
    "auth_chal_target_ascii",
    "auth_chal_target_canon",
    "auth_chal_failure_range",
    "auth_chal_reset_no_failures",
    "auth_chal_exhausted_state",
    "auth_chal_supersede_purpose",
    "auth_chal_resolved_state",
    "auth_chal_expiry_order",
    "auth_chal_resolved_order",
]
DELIVERY_CHECK_NAMES = [
    "auth_del_purpose_valid",
    "auth_del_status_valid",
    "auth_del_rate_key_valid",
    "auth_del_ip_digest_len",
    "auth_del_dest_digest_len",
    "auth_del_dest_digest_state",
    "auth_del_proof_digest_len",
    "auth_del_proof_key_valid",
    "auth_del_proof_state",
    "auth_del_resolved_state",
    "auth_del_exhausted_purpose",
    "auth_del_challenge_state",
    "auth_del_lease_order",
    "auth_del_sending_order",
    "auth_del_accepted_order",
    "auth_del_proof_expiry_order",
    "auth_del_resolved_order",
    "auth_del_resolved_send_order",
    "auth_del_resolved_accept_order",
]
CHALLENGE_UNIQUE_NAMES = ["auth_chal_open_user_uniq"]
DELIVERY_UNIQUE_NAMES = ["auth_del_one_active", "auth_del_one_inflight"]
_migration_modules = getattr(settings, "MIGRATION_MODULES", {})
MIGRATIONS_ENABLED = not ("authentication" in _migration_modules and _migration_modules["authentication"] is None)


@skipUnless(MIGRATIONS_ENABLED, "Migration execution is required")
class V2ChallengeMigrationTest(TransactionTestCase):
    reset_sequences = False

    def setUp(self):
        super().setUp()
        self.addCleanup(self.restore_latest_schema)
        self.old_apps = self.migrate(MIGRATE_FROM)
        self.old_user = self.old_apps.get_model("authentication", "CustomUser")

    def migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    def restore_latest_schema(self):
        self.migrate(MIGRATE_TO)

    def table_names(self):
        return set(connection.introspection.table_names())

    def test_migration_is_atomic_schema_only_and_operations_are_ordered(self):
        migration = import_module("authentication.migrations.0004_v2_challenge_schema").Migration
        operations = migration.operations
        expected_kinds = (
            [migrations.CreateModel] * 2
            + [migrations.AddIndex] * len(CHALLENGE_INDEX_NAMES)
            + [migrations.AddConstraint] * (len(CHALLENGE_CHECK_NAMES) + len(CHALLENGE_UNIQUE_NAMES))
            + [migrations.AddIndex] * len(DELIVERY_INDEX_NAMES)
            + [migrations.AddConstraint] * (len(DELIVERY_CHECK_NAMES) + len(DELIVERY_UNIQUE_NAMES))
        )

        self.assertTrue(migration.atomic)
        self.assertEqual(migration.dependencies, MIGRATE_FROM)
        self.assertEqual([type(operation) for operation in operations], expected_kinds)
        self.assertEqual(
            [operation.name for operation in operations[:2]],
            ["AuthenticationChallenge", "AuthenticationChallengeDelivery"],
        )
        self.assertEqual(
            [
                (operation.model_name, operation.index.name)
                for operation in operations
                if isinstance(operation, migrations.AddIndex)
            ],
            [
                *[("authenticationchallenge", name) for name in CHALLENGE_INDEX_NAMES],
                *[("authenticationchallengedelivery", name) for name in DELIVERY_INDEX_NAMES],
            ],
        )
        self.assertEqual(
            [
                (operation.model_name, operation.constraint.name)
                for operation in operations
                if isinstance(operation, migrations.AddConstraint)
            ],
            [
                *[("authenticationchallenge", name) for name in CHALLENGE_CHECK_NAMES + CHALLENGE_UNIQUE_NAMES],
                *[("authenticationchallengedelivery", name) for name in DELIVERY_CHECK_NAMES + DELIVERY_UNIQUE_NAMES],
            ],
        )

    def test_forward_reverse_preserves_existing_user_and_recreates_empty_schema(self):
        expected_email = "migration-owner@example.test"
        user = self.old_user._base_manager.create(email=expected_email, password="!")
        current_apps = self.migrate(MIGRATE_TO)
        challenge_model = current_apps.get_model("authentication", "AuthenticationChallenge")
        delivery_model = current_apps.get_model("authentication", "AuthenticationChallengeDelivery")
        now = datetime(2026, 9, 2, 11, 0, tzinfo=UTC)
        challenge_uuid = UUID("10000000-0000-4000-8000-000000000001")
        delivery_uuid = UUID("20000000-0000-4000-8000-000000000001")
        challenge = challenge_model._base_manager.create(
            uuid=challenge_uuid,
            user_id=user.pk,
            purpose="signup",
            transport="browser",
            status="open",
            pending_context_key_id="synthetic-proof-key-1",
            pending_context_digest=b"c" * 32,
            otp_failure_count=0,
            created_at=now,
            expires_at=now + timedelta(hours=1),
        )
        delivery = delivery_model._base_manager.create(
            uuid=delivery_uuid,
            challenge_id=challenge.pk,
            purpose="signup",
            status="reserved",
            rate_key_id="synthetic-rate-key-1",
            destination_rate_digest=b"d" * 32,
            ip_rate_digest=b"i" * 32,
            reserved_at=now,
            lease_expires_at=now + timedelta(seconds=120),
        )

        self.assertEqual(bytes(challenge.pending_context_digest), b"c" * 32)
        self.assertEqual(bytes(delivery.destination_rate_digest), b"d" * 32)
        self.assertEqual(bytes(delivery.ip_rate_digest), b"i" * 32)
        self.assertTrue({CHALLENGE_TABLE, DELIVERY_TABLE}.issubset(self.table_names()))

        reversed_apps = self.migrate(MIGRATE_FROM)
        reversed_user = reversed_apps.get_model("authentication", "CustomUser")._base_manager.get(pk=user.pk)

        self.assertEqual(reversed_user.email.encode("ascii"), expected_email.encode("ascii"))
        self.assertTrue({CHALLENGE_TABLE, DELIVERY_TABLE}.isdisjoint(self.table_names()))

        recreated_apps = self.migrate(MIGRATE_TO)
        recreated_challenge = recreated_apps.get_model("authentication", "AuthenticationChallenge")
        recreated_delivery = recreated_apps.get_model("authentication", "AuthenticationChallengeDelivery")

        self.assertFalse(recreated_challenge._base_manager.exists())
        self.assertFalse(recreated_delivery._base_manager.exists())
        self.assertTrue(
            recreated_apps.get_model("authentication", "CustomUser")
            ._base_manager.filter(pk=user.pk, email=expected_email)
            .exists()
        )

    def test_expected_constraints_and_indexes_are_installed(self):
        self.migrate(MIGRATE_TO)

        with connection.cursor() as cursor:
            challenge_schema = connection.introspection.get_constraints(cursor, CHALLENGE_TABLE)
            delivery_schema = connection.introspection.get_constraints(cursor, DELIVERY_TABLE)

        for name in CHALLENGE_CHECK_NAMES:
            self.assertTrue(challenge_schema[name]["check"], name)
        for name in DELIVERY_CHECK_NAMES:
            self.assertTrue(delivery_schema[name]["check"], name)
        for name in CHALLENGE_UNIQUE_NAMES:
            self.assertTrue(challenge_schema[name]["unique"], name)
        for name in DELIVERY_UNIQUE_NAMES:
            self.assertTrue(delivery_schema[name]["unique"], name)
        for name in CHALLENGE_INDEX_NAMES:
            self.assertTrue(challenge_schema[name]["index"], name)
        for name in DELIVERY_INDEX_NAMES:
            self.assertTrue(delivery_schema[name]["index"], name)

    def test_mid_operation_failure_rolls_back_schema_data_and_recorder(self):
        if not connection.features.can_rollback_ddl:
            self.skipTest("Transactional DDL is required")

        expected_email = "rollback-owner@example.test"
        user = self.old_user._base_manager.create(email=expected_email, password="!")
        original_forwards = migrations.AddConstraint.database_forwards
        observed = []

        def fail_during_delivery_constraints(operation, app_label, schema_editor, from_state, to_state):
            observed.append(operation.constraint.name)
            if operation.constraint.name == "auth_del_status_valid":
                raise RuntimeError("Synthetic challenge migration failure.")
            return original_forwards(operation, app_label, schema_editor, from_state, to_state)

        with patch.object(
            migrations.AddConstraint,
            "database_forwards",
            new=fail_during_delivery_constraints,
        ):
            with self.assertRaisesRegex(RuntimeError, r"^Synthetic challenge migration failure\.$"):
                self.migrate(MIGRATE_TO)

        self.assertIn("auth_del_status_valid", observed)
        self.assertTrue({CHALLENGE_TABLE, DELIVERY_TABLE}.isdisjoint(self.table_names()))
        self.assertFalse(
            MigrationRecorder(connection).migration_qs.filter(app="authentication", name=MIGRATION_NAME).exists()
        )
        stored = self.old_user._base_manager.get(pk=user.pk)
        self.assertEqual(stored.email.encode("ascii"), expected_email.encode("ascii"))

        self.migrate(MIGRATE_TO)

        self.assertTrue({CHALLENGE_TABLE, DELIVERY_TABLE}.issubset(self.table_names()))
        self.assertTrue(
            MigrationRecorder(connection).migration_qs.filter(app="authentication", name=MIGRATION_NAME).exists()
        )
