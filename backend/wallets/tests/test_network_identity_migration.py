from decimal import Decimal
from unittest import skipUnless

from django.conf import settings
from django.db import IntegrityError, connection
from django.test import TransactionTestCase

from assets.models import Asset
from shared.tests.schema import migrate_to, restore_every_migration
from users.models import UserAccount
from wallets.models import Holding, Transaction, Wallet

modules = getattr(settings, "MIGRATION_MODULES", {})
MIGRATIONS_ENABLED = not ("wallets" in modules and modules["wallets"] is None)


@skipUnless(connection.vendor == "postgresql" and MIGRATIONS_ENABLED, "Real PostgreSQL migrations are required")
class WalletNetworkIdentityMigrationTest(TransactionTestCase):
    def before(self):
        self.addCleanup(restore_every_migration)
        return migrate_to([("wallets", "0013_signing_preference")]).get_model("wallets", "Wallet")

    def test_adding_a_network_preserves_the_original_wallet_and_its_financial_records(self):
        OldWallet = self.before()
        account = UserAccount.objects.create(account_number="WALLET-MIGRATION")
        original = OldWallet.objects.create(user_account_id=account.pk, address="0x" + "a" * 40, chain="ethereum")
        asset = Asset.objects.create(symbol="MIG", name="Migration", asset_type="erc20_token")
        holding = Holding.objects.create(wallet_id=original.pk, asset=asset, quantity=Decimal("2.5"))
        transfer = Transaction.objects.create(
            wallet_id=original.pk,
            asset=asset,
            tx_hash="old-hash",
            chain="ethereum",
            from_address=original.address,
            to_address="0x" + "b" * 40,
            amount=1,
        )
        restore_every_migration()
        added = Wallet.objects.create(user_account=account, address=original.address, chain="base")
        original.refresh_from_db()
        holding.refresh_from_db()
        transfer.refresh_from_db()
        self.assertNotEqual(added.pk, original.pk)
        self.assertEqual((holding.wallet_id, holding.quantity), (original.pk, Decimal("2.5")))
        self.assertEqual((transfer.wallet_id, transfer.chain, transfer.tx_hash), (original.pk, "ethereum", "old-hash"))

    def test_existing_case_collisions_stop_the_migration_without_merging_or_deleting(self):
        OldWallet = self.before()
        account = UserAccount.objects.create(account_number="WALLET-COLLISION")
        original = OldWallet.objects.create(user_account_id=account.pk, address="0x" + "ab" * 20, chain="base")
        duplicate = OldWallet.objects.create(user_account_id=account.pk, address="0x" + "AB" * 20, chain="base")
        asset = Asset.objects.create(symbol="COL", name="Collision", asset_type="erc20_token")
        holding = Holding.objects.create(wallet_id=original.pk, asset=asset, quantity=Decimal("7.5"))
        try:
            with self.assertRaisesRegex(RuntimeError, "preserving their financial references"):
                restore_every_migration()
            self.assertEqual(set(OldWallet.objects.values_list("pk", flat=True)), {original.pk, duplicate.pk})
            holding.refresh_from_db()
            self.assertEqual((holding.wallet_id, holding.quantity), (original.pk, Decimal("7.5")))
        finally:
            OldWallet.objects.filter(pk=duplicate.pk).delete()
            restore_every_migration()

    def test_reversing_cannot_discard_wallets_to_restore_the_old_constraint(self):
        account = UserAccount.objects.create(account_number="WALLET-REVERSE")
        original = Wallet.objects.create(user_account=account, address="0x" + "a" * 40, chain="ethereum")
        added = Wallet.objects.create(user_account=account, address=original.address, chain="base")
        self.addCleanup(restore_every_migration)
        with self.assertRaises(IntegrityError):
            migrate_to([("wallets", "0013_signing_preference")])
        self.assertEqual(set(Wallet.objects.values_list("pk", flat=True)), {original.pk, added.pk})
