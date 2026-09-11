from unittest import skipUnless

from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone
from rest_framework.test import APITransactionTestCase

from shared.tests.schema import restore_every_migration
from wallets.tests.historical_submissions import (
    historical_financial_state,
    native_submission_at,
)
from wallets.tests.test_submission_durability import SubmissionFixture

BEFORE = ("wallets", "0018_global_submission_identity")
AFTER = ("wallets", "0019_chain_observations")
modules = getattr(settings, "MIGRATION_MODULES", {})
MIGRATIONS_ENABLED = not ("wallets" in modules and modules["wallets"] is None)


@skipUnless(connection.vendor == "postgresql" and MIGRATIONS_ENABLED, "Real PostgreSQL migrations are required")
class ChainObservationMigrationTest(SubmissionFixture, APITransactionTestCase):
    def setUp(self):
        super().setUp()
        self.addCleanup(restore_every_migration)
        executor = MigrationExecutor(connection)
        executor.migrate([BEFORE])
        self.old = executor.loader.project_state([BEFORE]).apps
        self.journal = native_submission_at(self.old, self.wallet, self.native, self.signed())

    def install(self):
        executor = MigrationExecutor(connection)
        executor.migrate([AFTER])
        return executor.loader.project_state([AFTER]).apps

    def claim(self, apps):
        watch = apps.get_model("wallets", "WalletChainWatch").objects.create(
            transaction_id=self.journal.transaction_id,
            wallet_id=self.wallet.pk,
            user_account_id=self.wallet.user_account_id,
            chain="base",
            network=f"evm:{self.journal.chain_id}",
            tx_hash=self.journal.tx_hash,
        )
        watch.generation = 1
        watch.target_fingerprint = "ab" * 32
        watch.last_started_at = timezone.now()
        watch.save(update_fields=["generation", "target_fingerprint", "last_started_at", "updated_at"])
        return watch

    def test_installation_keeps_signed_journals_and_existing_accounting_without_inventing_observations(self):
        before = historical_financial_state(self.old)
        journal = list(self.old.get_model("wallets", "WalletSubmission").objects.values())
        new = self.install()
        self.assertEqual(list(new.get_model("wallets", "WalletSubmission").objects.values()), journal)
        self.assertFalse(new.get_model("wallets", "WalletChainWatch").objects.exists())
        self.assertFalse(new.get_model("wallets", "WalletChainObservation").objects.exists())
        self.assertEqual(historical_financial_state(new), before)
        self.assertEqual(self.claim(new).generation, 1)

    def test_rollback_cannot_discard_completed_observation_evidence(self):
        apps = self.install()
        watch = self.claim(apps)
        row = apps.get_model("wallets", "WalletChainObservation").objects.create(
            watch=watch,
            user_account_id=watch.user_account_id,
            generation=watch.generation,
            target_fingerprint=watch.target_fingerprint,
            started_at=watch.last_started_at,
            result="unknown",
            finality="unknown",
            reason="provider_unavailable",
            policy={"mode": "unconfigured"},
            evidence={},
        )
        watch.latest_observation = row
        watch.last_completed_at = timezone.now()
        watch.save(update_fields=["latest_observation", "last_completed_at", "updated_at"])
        before = list(apps.get_model("wallets", "WalletChainObservation").objects.values())
        financial = historical_financial_state(apps)
        with self.assertRaisesRegex(RuntimeError, "cannot discard recorded evidence"):
            MigrationExecutor(connection).migrate([BEFORE])
        self.assertEqual(list(apps.get_model("wallets", "WalletChainObservation").objects.values()), before)
        self.assertEqual(historical_financial_state(apps), financial)

    def test_rollback_also_retains_an_unfinished_durable_claim(self):
        apps = self.install()
        watch = self.claim(apps)
        with self.assertRaisesRegex(RuntimeError, "cannot discard recorded evidence"):
            MigrationExecutor(connection).migrate([BEFORE])
        self.assertEqual(
            apps.get_model("wallets", "WalletChainWatch").objects.get(pk=watch.pk).generation, watch.generation
        )
        self.assertFalse(apps.get_model("wallets", "WalletChainObservation").objects.exists())
