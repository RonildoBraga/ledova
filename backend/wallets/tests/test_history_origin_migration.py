from decimal import Decimal
from unittest import skipUnless

from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone

from assets.services.identity import native_asset_for_chain
from shared.tests.schema import restore_every_migration
from shared.tests.tenants import make_tenant

BEFORE = ("wallets", "0014_wallet_network_identity")
AFTER = ("wallets", "0015_transaction_imported_from_history")
_migration_modules = getattr(settings, "MIGRATION_MODULES", {})
MIGRATIONS_ENABLED = not ("wallets" in _migration_modules and _migration_modules["wallets"] is None)


@skipUnless(MIGRATIONS_ENABLED, "History origin migration execution is required")
class HistoryOriginMigrationTest(TransactionTestCase):
    def test_existing_records_keep_every_field_without_guessing_their_origin(self):
        tenant = make_tenant("history-migration")
        native = native_asset_for_chain(tenant.wallet.chain)
        self.addCleanup(restore_every_migration)
        executor = MigrationExecutor(connection)
        executor.migrate([BEFORE])
        old = executor.loader.project_state([BEFORE]).apps
        transactions = old.get_model("wallets", "Transaction").objects
        for index, status in enumerate(("pending", "confirmed", "failed", "success")):
            transactions.create(
                wallet_id=tenant.wallet.pk,
                user_account_id=tenant.account.pk,
                asset_id=native.pk,
                tx_hash="0x" + f"{index + 300:064x}",
                chain=tenant.wallet.chain,
                from_address=tenant.wallet.address,
                to_address="0x" + "62" * 20,
                amount=Decimal("1.2"),
                deducted_amount=Decimal("1.2") if index == 0 else None,
                status=status,
                block_number=75,
                block_timestamp=timezone.now() - timezone.timedelta(days=7),
            )
        before = list(transactions.order_by("pk").values())
        executor = MigrationExecutor(connection)
        executor.migrate([AFTER])
        new = executor.loader.project_state([AFTER]).apps
        after = list(new.get_model("wallets", "Transaction").objects.order_by("pk").values())
        self.assertEqual(len(after), len(before))
        for record in after:
            self.assertFalse(record.pop("imported_from_history"))
        self.assertEqual(after, before)
