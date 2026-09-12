from unittest import skipUnless

from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from rest_framework.test import APITransactionTestCase

from shared.db import use_operator
from shared.tests.schema import restore_every_migration
from wallets.models import WalletChainObservation, WalletChainWatch, WalletSubmission
from wallets.services.chain_observations import (
    claim_chain_observation,
    observe_wallet_chain,
)
from wallets.tests.test_chain_observations import ChainObservationFixture

BEFORE = ("wallets", "0018_global_submission_identity")
AFTER = ("wallets", "0019_chain_observations")
modules = getattr(settings, "MIGRATION_MODULES", {})
MIGRATIONS_ENABLED = not ("wallets" in modules and modules["wallets"] is None)


@skipUnless(connection.vendor == "postgresql" and MIGRATIONS_ENABLED, "Real PostgreSQL migrations are required")
class ChainObservationMigrationTest(ChainObservationFixture, APITransactionTestCase):
    def test_installation_keeps_signed_journals_and_existing_accounting_without_inventing_observations(self):
        self.addCleanup(restore_every_migration)
        MigrationExecutor(connection).migrate([BEFORE])
        before = self.financial_state()
        with use_operator():
            journal = list(WalletSubmission.objects.values())
        MigrationExecutor(connection).migrate([AFTER])
        with use_operator():
            self.assertEqual(list(WalletSubmission.objects.values()), journal)
            self.assertEqual(WalletChainWatch.objects.count(), 0)
            self.assertEqual(WalletChainObservation.objects.count(), 0)
        self.assertEqual(self.financial_state(), before)
        self.assertEqual(observe_wallet_chain(self.tx_id), "recorded")

    def test_rollback_cannot_discard_completed_observation_evidence(self):
        self.addCleanup(restore_every_migration)
        self.assertEqual(observe_wallet_chain(self.tx_id), "recorded")
        before = self.observations()
        financial = self.financial_state()
        with self.assertRaisesRegex(RuntimeError, "cannot discard recorded evidence"):
            MigrationExecutor(connection).migrate([BEFORE])
        self.assertEqual(self.observations(), before)
        self.assertEqual(self.financial_state(), financial)

    def test_rollback_also_retains_an_unfinished_durable_claim(self):
        self.addCleanup(restore_every_migration)
        claim = claim_chain_observation(self.tx_id)
        with self.assertRaisesRegex(RuntimeError, "cannot discard recorded evidence"):
            MigrationExecutor(connection).migrate([BEFORE])
        self.assertEqual(self.watch().generation, claim.generation)
        self.assertEqual(self.observations(), [])
