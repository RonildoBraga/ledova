from unittest import skipUnless

from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from rest_framework.test import APITransactionTestCase

from shared.tests.schema import restore_every_migration
from wallets.tests.historical_submissions import (
    historical_financial_state,
    native_submission_at,
)
from wallets.tests.test_submission_durability import SubmissionFixture

BEFORE = ("wallets", "0019_chain_observations")
AFTER = ("wallets", "0020_submission_families")
modules = getattr(settings, "MIGRATION_MODULES", {})
MIGRATIONS_ENABLED = not ("wallets" in modules and modules["wallets"] is None)


@skipUnless(connection.vendor == "postgresql" and MIGRATIONS_ENABLED, "Real PostgreSQL migrations are required")
class SubmissionFamilyMigrationTest(SubmissionFixture, APITransactionTestCase):
    def test_backfill_preserves_every_existing_attempt_and_financial_row(self):
        self.addCleanup(restore_every_migration)
        executor = MigrationExecutor(connection)
        executor.migrate([BEFORE])
        old = executor.loader.project_state([BEFORE]).apps
        for nonce, status in enumerate(("pending", "confirmed", "failed", "reorged", "replaced")):
            native_submission_at(old, self.wallet, self.native, self.signed(nonce=nonce, value=10**18), status=status)
        before = historical_financial_state(old)
        attempts = list(old.get_model("wallets", "WalletSubmission").objects.order_by("pk").values())
        executor = MigrationExecutor(connection)
        executor.migrate([AFTER])
        new = executor.loader.project_state([AFTER]).apps
        after = historical_financial_state(new)
        after = (
            after[0],
            [{key: value for key, value in row.items() if key != "balance_projection_id"} for row in after[1]],
            after[2],
        )
        self.assertEqual(after, before)
        stored = list(new.get_model("wallets", "WalletSubmission").objects.order_by("pk").values())
        self.assertEqual(
            [
                {key: value for key, value in row.items() if key not in ("family_id", "kind", "parent_id")}
                for row in stored
            ],
            attempts,
        )
        families = new.get_model("wallets", "WalletSubmissionFamily").objects
        self.assertEqual(families.count(), 5)
        for row in stored:
            family = families.get(pk=row["family_id"])
            self.assertEqual(
                (family.selected_id, family.original_tx_hash, family.original_intent),
                (row["uuid"], row["tx_hash"], row["intent"]),
            )
            self.assertIsNone(family.winner_id)
        self.assertFalse(new.get_model("wallets", "WalletBalanceProjection").objects.exists())
        with self.assertRaisesRegex(RuntimeError, "cannot discard recorded state"):
            MigrationExecutor(connection).migrate([BEFORE])
        self.assertEqual(list(new.get_model("wallets", "WalletSubmission").objects.order_by("pk").values()), stored)
