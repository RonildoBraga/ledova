from decimal import Decimal
from unittest import skipUnless

from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from assets.services.identity import native_asset_for_chain
from shared.tests.schema import restore_every_migration
from shared.tests.tenants import make_tenant

BEFORE = ("wallets", "0011_wallet_verification_challenge_issued_at")
AFTER = ("wallets", "0012_balance_versions")
_migration_modules = getattr(settings, "MIGRATION_MODULES", {})
MIGRATIONS_ENABLED = not ("wallets" in _migration_modules and _migration_modules["wallets"] is None)


@skipUnless(MIGRATIONS_ENABLED, "Balance version migration execution is required")
class BalanceVersionMigrationTest(TransactionTestCase):
    def test_existing_holdings_keep_their_quantity_without_inventing_a_refundable_generation(self):
        tenant = make_tenant("balance-migration")
        native = native_asset_for_chain(tenant.wallet.chain)
        self.addCleanup(restore_every_migration)
        executor = MigrationExecutor(connection)
        executor.migrate([BEFORE])
        old = executor.loader.project_state([BEFORE]).apps
        holding = old.get_model("wallets", "Holding").objects.create(
            wallet_id=tenant.wallet.pk, asset_id=native.pk, quantity=Decimal("4.998")
        )
        tx = old.get_model("wallets", "Transaction").objects.create(
            wallet_id=tenant.wallet.pk,
            asset_id=native.pk,
            tx_hash="0x" + "57" * 32,
            chain=tenant.wallet.chain,
            from_address=tenant.wallet.address,
            to_address="0x" + "58" * 20,
            amount=Decimal("0.002"),
            deducted_amount=Decimal("0.002"),
        )
        executor = MigrationExecutor(connection)
        executor.migrate([AFTER])
        new = executor.loader.project_state([AFTER]).apps
        migrated_holding = new.get_model("wallets", "Holding").objects.get(pk=holding.pk)
        migrated_tx = new.get_model("wallets", "Transaction").objects.get(pk=tx.pk)
        self.assertEqual(migrated_holding.quantity, Decimal("4.998"))
        self.assertIsNotNone(migrated_holding.balance_version)
        self.assertIsNotNone(migrated_holding.sync_version)
        self.assertEqual(migrated_tx.deducted_amount, Decimal("0.002"))
        self.assertIsNone(migrated_tx.deducted_amount_sync_version)
        self.assertIsNone(migrated_tx.deducted_fee_sync_version)
