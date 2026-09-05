from unittest import skipUnless

from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

MIGRATE_BEFORE = [("tokens", "0013_remove_transferorder_signature_request")]
MIGRATE_FROM = [("tokens", "0014_settlement_asset_columns")]
MIGRATE_TO = [("tokens", "0015_fold_stablecoin_into_asset")]
MIGRATE_LATEST = [("tokens", "0016_drop_stablecoin")]
BASE = "base"
_migration_modules = getattr(settings, "MIGRATION_MODULES", {})
MIGRATIONS_ENABLED = not ("tokens" in _migration_modules and _migration_modules["tokens"] is None)


@skipUnless(MIGRATIONS_ENABLED, "Migration execution is required")
class StablecoinFoldMigrationTest(TransactionTestCase):
    reset_sequences = False

    def setUp(self):
        super().setUp()
        self.addCleanup(self.restore_latest_schema)
        self.old_apps = self.migrate(MIGRATE_FROM)
        self.stablecoin = self.old_apps.get_model("tokens", "Stablecoin")
        self.asset = self.old_apps.get_model("assets", "Asset")
        self.deployment = self.old_apps.get_model("assets", "AssetChainDeployment")

    def migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    def restore_latest_schema(self):
        for model in ("SwapOrder", "TransferOrder", "MintRequest"):
            self.old_apps.get_model("tokens", model)._base_manager.all().delete()
        self.old_apps.get_model("tokens", "Stablecoin")._base_manager.all().delete()
        self.migrate(MIGRATE_LATEST)

    def fold(self):
        new_apps = self.migrate(MIGRATE_TO)
        return new_apps.get_model("assets", "Asset"), new_apps.get_model("assets", "AssetChainDeployment")

    def coin(self, symbol="TUSD", address="0x" + "5" * 40, name="Tenant dollar", decimals=2):
        return self.stablecoin._base_manager.create(
            symbol=symbol, name=name, contract_address=address, decimals=decimals, is_active=True
        )

    def test_a_stablecoin_is_matched_to_the_asset_that_shares_its_symbol(self):
        asset = self.asset._base_manager.create(
            symbol="TUSD", name="Tenant dollar", asset_type="stablecoin", decimals=2, is_verified=True
        )
        self.coin(symbol="tusd")

        Asset, Deployment = self.fold()

        self.assertEqual(Asset._base_manager.filter(symbol__iexact="tusd").count(), 1)
        deployment = Deployment._base_manager.get(asset_id=asset.pk, chain=BASE)
        self.assertEqual((deployment.contract_address, deployment.decimals), ("0x" + "5" * 40, 2))

    def test_a_stablecoin_is_matched_by_its_settlement_chain_contract_address(self):
        asset = self.asset._base_manager.create(
            symbol="AUDY", name="AUDY", asset_type="stablecoin", decimals=2, is_verified=True
        )
        self.deployment._base_manager.create(
            asset_id=asset.pk, chain=BASE, contract_address="0x" + "AB" * 20, decimals=2, is_active=True
        )
        self.coin(symbol="OTHER", address="0x" + "ab" * 20)

        Asset, Deployment = self.fold()

        self.assertFalse(Asset._base_manager.filter(symbol="OTHER").exists())
        self.assertEqual(Deployment._base_manager.filter(asset_id=asset.pk).count(), 1)

    def test_an_unmatched_stablecoin_becomes_a_fresh_asset_with_its_deployment(self):
        self.coin(symbol="NEWC", address="0x" + "7" * 40, name="New coin", decimals=6)

        Asset, Deployment = self.fold()

        asset = Asset._base_manager.get(symbol="NEWC")
        self.assertEqual((asset.name, asset.asset_type, asset.decimals), ("New coin", "stablecoin", 6))
        self.assertTrue(asset.is_verified)
        deployment = Deployment._base_manager.get(asset_id=asset.pk)
        self.assertEqual(
            (deployment.chain, deployment.contract_address, deployment.decimals), (BASE, "0x" + "7" * 40, 6)
        )

    def test_a_disagreeing_address_refuses_the_fold_before_anything_is_written(self):
        asset = self.asset._base_manager.create(
            symbol="AUDY", name="AUDY", asset_type="stablecoin", decimals=2, is_verified=True
        )
        self.deployment._base_manager.create(
            asset_id=asset.pk, chain=BASE, contract_address="0x" + "1" * 40, decimals=2, is_active=True
        )
        coin = self.coin(symbol="AUDY", address="0x" + "2" * 40)
        mint = self.mint_request(coin)

        with self.assertRaises(RuntimeError) as refusal:
            self.fold()

        self.assertIn("0x" + "2" * 40, str(refusal.exception))
        self.assertIn("Reconcile the addresses", str(refusal.exception))
        deployment = self.deployment._base_manager.get(asset_id=asset.pk, chain=BASE)
        self.assertEqual(deployment.contract_address, "0x" + "1" * 40)
        mint = self.old_apps.get_model("tokens", "MintRequest")._base_manager.get(pk=mint.pk)
        self.assertIsNone(mint.settlement_asset_id)

    def test_the_three_foreign_keys_are_copied_and_the_reverse_puts_them_back(self):
        coin = self.coin()
        tenant = self.tenant_rows(coin)

        Asset, _ = self.fold()

        asset = Asset._base_manager.get(symbol="TUSD")
        for model_name, column, _, pk in tenant:
            row = self.old_apps.get_model("tokens", model_name)._base_manager.get(pk=pk)
            self.assertEqual(getattr(row, column), asset.pk)

        self.migrate(MIGRATE_FROM)

        restored = self.old_apps.get_model("tokens", "Stablecoin")._base_manager.get(symbol="TUSD")
        self.assertEqual(restored.contract_address, "0x" + "5" * 40)
        for model_name, column, legacy, pk in tenant:
            row = self.old_apps.get_model("tokens", model_name)._base_manager.get(pk=pk)
            self.assertIsNone(getattr(row, column))
            self.assertEqual(getattr(row, legacy), restored.pk)

    def test_unapplying_the_drop_survives_a_database_that_holds_swap_orders(self):
        coin = self.coin()
        tenant = self.tenant_rows(coin)
        swap_pk = dict((name, pk) for name, _, _, pk in tenant)["SwapOrder"]

        self.migrate(MIGRATE_LATEST)
        self.migrate(MIGRATE_TO)

        swap = self.old_apps.get_model("tokens", "SwapOrder")._base_manager.get(pk=swap_pk)
        self.assertIsNotNone(swap.payment_asset_id)
        self.assertIsNone(swap.payment_token_id)

    def test_rolling_back_to_the_previous_release_keeps_the_swap_order(self):
        coin = self.coin()
        tenant = self.tenant_rows(coin)
        swap_pk = dict((name, pk) for name, _, _, pk in tenant)["SwapOrder"]

        self.migrate(MIGRATE_LATEST)
        previous = self.migrate(MIGRATE_BEFORE)

        swap = previous.get_model("tokens", "SwapOrder")._base_manager.get(pk=swap_pk)
        coin = previous.get_model("tokens", "Stablecoin")._base_manager.get(pk=swap.payment_token_id)
        self.assertEqual((coin.symbol, coin.contract_address), ("TUSD", "0x" + "5" * 40))

        self.migrate(MIGRATE_FROM)

    def test_the_fold_supports_every_folded_asset_for_settlement(self):
        from operators.models import Operator

        Operator.objects.create(name="Ledova", receiving_wallet_chain=BASE)
        self.coin()

        Asset, _ = self.fold()

        asset = Asset._base_manager.get(symbol="TUSD")
        self.assertEqual([row.pk for row in Operator.get().supported_settlement_assets.all()], [asset.pk])

        self.migrate(MIGRATE_FROM)

        self.assertEqual(Operator.get().supported_settlement_assets.count(), 0)

    def mint_request(self, coin, user=None):
        from datetime import date

        from django.contrib.auth import get_user_model

        if user is None:
            user = get_user_model().objects.create_user(email="mint@example.test", password="pw-12345678")
        return self.old_apps.get_model("tokens", "MintRequest")._base_manager.create(
            stablecoin_id=coin.pk,
            recipient_address="0x" + "b" * 40,
            recipient_name="Alice",
            amount=10000,
            deposit_reference="REF-1",
            deposit_date=date(2026, 9, 1),
            requested_by_id=user.pk,
        )

    def tenant_rows(self, coin):
        from datetime import timedelta
        from decimal import Decimal

        from django.contrib.auth import get_user_model
        from django.utils import timezone

        from companies.models import Company, CompanyType
        from tokens.models import ShareToken, ShareTokenStatus
        from users.models import UserAccount, UserProfile
        from wallets.models import Wallet

        user = get_user_model().objects.create_user(email="fold@example.test", password="pw-12345678")
        profile = UserProfile.objects.create(user=user, full_name="Fold owner")
        account = UserAccount.objects.create(account_number="FOLD-1")
        account.user_profiles.add(profile)
        wallet = Wallet.objects.create(user_account=account, address="0x" + "a" * 40, chain=BASE)
        company = Company.objects.create(
            owner=user, name="Fold Pty Ltd", company_type=CompanyType.PROPRIETARY, acn="123456789"
        )
        token = ShareToken.objects.create(
            company=company,
            name="Fold shares",
            symbol="FLD",
            total_supply="1000",
            status=ShareTokenStatus.DEPLOYED,
            contract_address="0x" + "c" * 40,
        )

        order_model = self.old_apps.get_model("tokens", "TransferOrder")
        orders = [
            order_model._base_manager.create(
                token_id=token.pk,
                payment_token_id=coin.pk,
                wallet_id=wallet.pk,
                owner_account_id=account.pk,
                wallet_address=wallet.address,
                order_type=order_type,
                quantity=10,
                price_per_share=Decimal("1.50"),
            )
            for order_type in ("SELL", "BUY")
        ]
        swap = self.old_apps.get_model("tokens", "SwapOrder")._base_manager.create(
            sell_order_id=orders[0].pk,
            buy_order_id=orders[1].pk,
            share_token_id=token.pk,
            payment_token_id=coin.pk,
            seller_address=wallet.address,
            buyer_address=wallet.address,
            share_amount=10,
            payment_amount=1500,
            nonce=1,
            order_hash="0x" + "1" * 64,
            expires_at=timezone.now() + timedelta(hours=1),
        )
        mint = self.mint_request(coin, user=user)
        return [
            ("TransferOrder", "payment_asset_id", "payment_token_id", orders[0].pk),
            ("SwapOrder", "payment_asset_id", "payment_token_id", swap.pk),
            ("MintRequest", "settlement_asset_id", "stablecoin_id", mint.pk),
        ]
