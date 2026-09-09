from decimal import Decimal
from unittest import skipUnless

from django.conf import settings
from django.db import connection
from django.test import TransactionTestCase

from assets.models import Asset, AssetChainDeployment
from shared.tests.schema import migrate_to, restore_every_migration
from users.models import UserAccount
from wallets.models import Holding, Wallet

modules = getattr(settings, "MIGRATION_MODULES", {})
MIGRATIONS_ENABLED = not ("assets" in modules and modules["assets"] is None)


@skipUnless(connection.vendor == "postgresql" and MIGRATIONS_ENABLED, "Real PostgreSQL migrations are required")
class NativeDeploymentMigrationTest(TransactionTestCase):
    def before(self):
        self.addCleanup(restore_every_migration)
        return migrate_to([("assets", "0013_price_provenance")]).get_model("assets", "Asset")

    def test_existing_wallets_and_quantities_keep_their_identity_when_base_is_added(self):
        OldAsset = self.before()
        asset = OldAsset.objects.create(symbol="ETH", name="Ether", asset_type="native_crypto", current_price=7)
        original = AssetChainDeployment.objects.create(asset_id=asset.pk, chain="ethereum", is_active=False)
        account = UserAccount.objects.create(account_number="NATIVE-MIGRATION")
        wallet = Wallet.objects.create(user_account=account, address="0x" + "a" * 40, chain="base")
        holding = Holding.objects.create(wallet=wallet, asset_id=asset.pk, quantity=Decimal("2.5"))

        restore_every_migration()

        self.assertEqual(Asset.objects.native_for_chain("base").pk, asset.pk)
        original.refresh_from_db()
        holding.refresh_from_db()
        self.assertFalse(original.is_active)
        self.assertEqual((holding.wallet_id, holding.asset_id, holding.quantity), (wallet.pk, asset.pk, Decimal("2.5")))
        self.assertEqual(Asset.objects.get(pk=asset.pk).current_price, 7)
        base_id = AssetChainDeployment.objects.get(asset_id=asset.pk, chain="base").pk
        self.before()
        self.assertTrue(AssetChainDeployment.objects.filter(pk=base_id).exists())
        restore_every_migration()
        self.assertEqual(AssetChainDeployment.objects.get(asset_id=asset.pk, chain="base").pk, base_id)
        self.assertEqual(AssetChainDeployment.objects.filter(asset_id=asset.pk).count(), 2)

    def test_existing_configuration_and_inactive_assets_are_preserved(self):
        OldAsset = self.before()
        eth = OldAsset.objects.create(symbol="ETH", name="Ether", asset_type="native_crypto", is_active=False)
        contract = "0x" + "c" * 40
        configured = AssetChainDeployment.objects.create(
            asset_id=eth.pk, chain="base", contract_address=contract, decimals=6, is_active=False
        )
        btc = OldAsset.objects.create(symbol="BTC", name="Bitcoin", asset_type="native_crypto", decimals=8)
        restore_every_migration()
        configured.refresh_from_db()
        self.assertEqual((configured.contract_address, configured.decimals, configured.is_active), (contract, 6, False))
        self.assertFalse(AssetChainDeployment.objects.get(asset_id=eth.pk, chain="ethereum").is_active)
        self.assertIsNone(Asset.objects.native_for_chain("base"))
        self.assertEqual(AssetChainDeployment.objects.get(asset_id=btc.pk, chain="bitcoin").decimals, 8)

    def test_a_non_native_row_with_a_reserved_symbol_is_never_reclassified(self):
        OldAsset = self.before()
        asset = OldAsset.objects.create(symbol="ETH", name="Old token", asset_type="erc20_token")
        restore_every_migration()
        self.assertEqual(Asset.objects.get(pk=asset.pk).asset_type, "erc20_token")
        self.assertFalse(AssetChainDeployment.objects.filter(asset_id=asset.pk).exists())
