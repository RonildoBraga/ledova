import logging
from contextlib import redirect_stderr, redirect_stdout
from importlib import import_module
from io import StringIO
from queue import Queue
from threading import Thread
from time import monotonic, sleep
from unittest import skipUnless
from unittest.mock import patch

from django.conf import settings
from django.db import close_old_connections, connection, migrations
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder
from django.test import TransactionTestCase

MIGRATE_FROM = [("authentication", "0002_authsession_refreshcredential")]
MIGRATE_TO = [("authentication", "0003_customuser_v2_email_constraints")]
MIGRATE_LATEST = [("authentication", "0007_delete_authsession_refreshcredential")]
PREFLIGHT_ERROR = "V2 email migration preflight failed."
MIGRATION_NAME = "0003_customuser_v2_email_constraints"
CONSTRAINT_NAMES = {
    "auth_user_email_v2_ascii_ck",
    "auth_user_email_v2_canon_ck",
    "auth_user_email_v2_key_uniq",
}
_migration_modules = getattr(settings, "MIGRATION_MODULES", {})
MIGRATIONS_ENABLED = not ("authentication" in _migration_modules and _migration_modules["authentication"] is None)


@skipUnless(MIGRATIONS_ENABLED, "Migration execution is required")
class EmailMigrationTest(TransactionTestCase):
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

    def delete_users(self):
        table = connection.ops.quote_name(self.old_user._meta.db_table)
        with connection.cursor() as cursor:
            cursor.execute(f"DELETE FROM {table}")

    def restore_latest_schema(self):
        try:
            self.delete_users()
        finally:
            self.migrate(MIGRATE_LATEST)
        tables = connection.introspection.table_names()
        for table in (
            "authentication_auth_session",
            "authentication_refresh_credential",
            "authentication_challenge",
            "authentication_challenge_delivery",
        ):
            self.assertNotIn(table, tables)

    def assert_preflight_rejected(self, private_value=None):
        stdout = StringIO()
        stderr = StringIO()
        logs = StringIO()
        handler = logging.StreamHandler(logs)
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        try:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                with self.assertRaises(RuntimeError) as raised:
                    self.migrate(MIGRATE_TO)
        finally:
            root_logger.removeHandler(handler)
        self.assertEqual(str(raised.exception), PREFLIGHT_ERROR)
        self.assertEqual(repr(raised.exception), f"RuntimeError('{PREFLIGHT_ERROR}')")
        self.assertIsNone(raised.exception.__cause__)
        self.assertTrue(raised.exception.__suppress_context__)
        captured = stdout.getvalue() + stderr.getvalue() + logs.getvalue()
        if private_value:
            self.assertNotIn(private_value, captured)

    def test_preflight_rejects_invalid_noncanonical_and_non_ascii_rows(self):
        values = [
            "",
            "not-an-email",
            " Owner@EXAMPLE.TEST ",
            "owner\t@example.test",
            "owner\n@example.test",
            "owner\x1f@example.test",
            "owner\x7f@example.test",
            "owner\u00a0@example.test",
            "own\u00e9r@example.test",
        ]
        if connection.vendor == "sqlite":
            values.extend(
                [
                    "owner\x00@example.test",
                    f"{'a' * 64}@{'b' * 63}.{'c' * 63}.{'d' * 62}",
                ]
            )

        for email in values:
            with self.subTest(value=ascii(email)):
                self.old_user._base_manager.create(email=email, password="!")
                self.assert_preflight_rejected(email)
                self.delete_users()

    def test_preflight_rejects_a_noncanonical_collision_set_without_disclosure(self):
        self.old_user._base_manager.create(email="Owner@example.test", password="!")
        self.old_user._base_manager.create(email="owner@example.test ", password="!")

        self.assert_preflight_rejected("Owner@example.test")

    def test_failed_preflight_leaves_schema_recorder_and_data_unchanged_then_retries(self):
        private_value = " Private.Marker.7@example.test "
        original = self.old_user._base_manager.create(email=private_value, password="!")

        self.assert_preflight_rejected(private_value)

        self.assertFalse(
            MigrationRecorder(connection).migration_qs.filter(app="authentication", name=MIGRATION_NAME).exists()
        )
        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(cursor, self.old_user._meta.db_table)
        self.assertFalse(CONSTRAINT_NAMES.intersection(constraints))
        stored = self.old_user._base_manager.get(pk=original.pk)
        self.assertEqual(stored.email.encode("ascii"), private_value.encode("ascii"))

        self.delete_users()
        self.old_user._base_manager.create(email="owner@example.test", password="!")
        self.migrate(MIGRATE_TO)
        self.assertTrue(
            MigrationRecorder(connection).migration_qs.filter(app="authentication", name=MIGRATION_NAME).exists()
        )
        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(cursor, self.old_user._meta.db_table)
        self.assertTrue(CONSTRAINT_NAMES.issubset(constraints))

    def test_partial_constraint_failure_rolls_back_ddl_and_recorder(self):
        expected = "owner@example.test"
        original = self.old_user._base_manager.create(email=expected, password="!")
        original_forwards = migrations.AddConstraint.database_forwards

        def fail_after_first_constraint(operation, app_label, schema_editor, from_state, to_state):
            if operation.constraint.name == "auth_user_email_v2_canon_ck":
                raise RuntimeError("Synthetic constraint failure.")
            return original_forwards(operation, app_label, schema_editor, from_state, to_state)

        with patch.object(migrations.AddConstraint, "database_forwards", new=fail_after_first_constraint):
            with self.assertRaisesRegex(RuntimeError, r"^Synthetic constraint failure\.$"):
                self.migrate(MIGRATE_TO)

        self.assertFalse(
            MigrationRecorder(connection).migration_qs.filter(app="authentication", name=MIGRATION_NAME).exists()
        )
        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(cursor, self.old_user._meta.db_table)
        self.assertFalse(CONSTRAINT_NAMES.intersection(constraints))
        stored = self.old_user._base_manager.get(pk=original.pk)
        self.assertEqual(stored.email.encode("ascii"), expected.encode("ascii"))

    def test_operation_order_is_lock_then_three_constraints(self):
        migration = import_module("authentication.migrations.0003_customuser_v2_email_constraints")
        operations = migration.Migration.operations

        self.assertTrue(migration.Migration.atomic)
        self.assertIsInstance(operations[0], migrations.RunPython)
        self.assertIs(operations[0].code, migration.lock_and_preflight_v2_email)
        self.assertEqual(
            [operation.constraint.name for operation in operations[1:]],
            [
                "auth_user_email_v2_ascii_ck",
                "auth_user_email_v2_canon_ck",
                "auth_user_email_v2_key_uniq",
            ],
        )
        self.assertTrue(all(isinstance(operation, migrations.AddConstraint) for operation in operations[1:]))

    def test_forward_and_reverse_preserve_canonical_email_bytes(self):
        expected = "owner+tag@example.test"
        original = self.old_user._base_manager.create(email=expected, password="!")

        current_apps = self.migrate(MIGRATE_TO)
        current_user = current_apps.get_model("authentication", "CustomUser")._base_manager.get(pk=original.pk)
        self.assertEqual(current_user.email.encode("ascii"), expected.encode("ascii"))

        reversed_apps = self.migrate(MIGRATE_FROM)
        reversed_user = reversed_apps.get_model("authentication", "CustomUser")._base_manager.get(pk=original.pk)
        self.assertEqual(reversed_user.email.encode("ascii"), expected.encode("ascii"))


@skipUnless(connection.vendor == "postgresql", "PostgreSQL locking semantics are required")
class EmailMigrationPostgresLockTest(TransactionTestCase):
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
        self.migrate(MIGRATE_LATEST)

    def writer(self, table, started, outcomes):
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '10s'")
                cursor.execute("SET statement_timeout = '15s'")
                cursor.execute("SELECT pg_backend_pid()")
                backend_pid = cursor.fetchone()[0]
                started.put(backend_pid)
                cursor.execute(f"UPDATE {table} SET id = id WHERE FALSE")
            outcomes.put(None)
        except BaseException as exc:
            outcomes.put(exc)
        finally:
            close_old_connections()

    def wait_until_blocked(self, backend_pid):
        deadline = monotonic() + 5
        while monotonic() < deadline:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_blocking_pids(%s)", [backend_pid])
                if cursor.fetchone()[0]:
                    return True
            sleep(0.01)
        return False

    def test_actual_migration_keeps_preflight_lock_through_constraints_and_commit(self):
        table = connection.ops.quote_name(self.old_user._meta.db_table)
        started = Queue()
        outcomes = Queue()
        worker = None
        blocked = []
        original_forwards = migrations.AddConstraint.database_forwards

        def observe_first_constraint(operation, app_label, schema_editor, from_state, to_state):
            nonlocal worker
            if operation.constraint.name == "auth_user_email_v2_ascii_ck":
                worker = Thread(
                    target=self.writer,
                    args=(table, started, outcomes),
                    name="v2-email-migration-writer",
                )
                worker.start()
                backend_pid = started.get(timeout=5)
                blocked.append(self.wait_until_blocked(backend_pid))
            return original_forwards(operation, app_label, schema_editor, from_state, to_state)

        try:
            with patch.object(migrations.AddConstraint, "database_forwards", new=observe_first_constraint):
                self.migrate(MIGRATE_TO)
        finally:
            if worker is not None:
                worker.join(timeout=16)

        self.assertEqual(blocked, [True])
        self.assertIsNotNone(worker)
        self.assertFalse(worker.is_alive())
        outcome = outcomes.get(timeout=1)
        if outcome is not None:
            raise outcome
