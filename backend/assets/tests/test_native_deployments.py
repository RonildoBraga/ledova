from decimal import Decimal
from unittest.mock import Mock, patch

from django.test import TestCase
from rest_framework.test import APIClient

from assets.models import Asset, AssetChainDeployment
from assets.services.identity import native_asset_for_chain
from assets.services.sync import AssetSyncService
from shared.tests.tenants import make_tenant
from wallets.models import Holding, Wallet
from wallets.services.chain import fetch_chain_balance


class NativeDeploymentTest(TestCase):
    def test_fallback_creates_chain_deployments_without_splitting_the_coin(self):
        ethereum = native_asset_for_chain("ethereum")
        base = native_asset_for_chain("base")
        bitcoin = native_asset_for_chain("bitcoin")
        self.assertEqual(base, ethereum)
        self.assertEqual(Asset.objects.filter(symbol="ETH").count(), 1)
        self.assertEqual(Asset.objects.native_for_chain("ethereum"), ethereum)
        self.assertEqual(Asset.objects.native_for_chain("base"), base)
        self.assertEqual(Asset.objects.native_for_chain("bitcoin"), bitcoin)
        self.assertEqual(bitcoin.chain_deployments.get().decimals, 8)

    def test_seed_adds_base_to_an_existing_coin_and_preserves_a_disabled_deployment(self):
        eth = Asset.objects.create(symbol="ETH", name="Ether", asset_type="native_crypto")
        ethereum = AssetChainDeployment.objects.create(asset=eth, chain="ethereum", is_active=False)
        AssetSyncService.ensure_supported_assets()
        AssetSyncService.ensure_supported_assets()
        ethereum.refresh_from_db()
        self.assertFalse(ethereum.is_active)
        self.assertEqual(Asset.objects.native_for_chain("base"), eth)
        self.assertEqual(eth.chain_deployments.count(), 2)
        with self.assertRaisesRegex(ValueError, "unavailable"):
            native_asset_for_chain("ethereum")

    def test_an_inactive_coin_stays_unavailable_after_seeding(self):
        eth = Asset.objects.create(symbol="ETH", name="Ether", asset_type="native_crypto", is_active=False)
        AssetSyncService.ensure_supported_assets()
        self.assertIsNone(Asset.objects.native_for_chain("base"))
        self.assertFalse(eth.chain_deployments.filter(is_active=True).exists())
        with self.assertRaisesRegex(ValueError, "unavailable"):
            native_asset_for_chain("base")

    def test_a_wrong_contract_or_decimal_count_is_preserved_but_never_used_as_native(self):
        tenant = make_tenant("invalid-native")
        wallet = Wallet.objects.create(user_account=tenant.account, address="0x" + "a" * 40, chain="base")
        eth = Asset.objects.create(symbol="ETH", name="Ether", asset_type="native_crypto")
        deployment = AssetChainDeployment.objects.create(asset=eth, chain="base")
        for contract, decimals in (("0x" + "c" * 40, 18), (None, 6)):
            with self.subTest(contract=contract, decimals=decimals):
                deployment.contract_address, deployment.decimals = contract, decimals
                deployment.save()
                AssetSyncService.ensure_supported_assets()
                deployment.refresh_from_db()
                self.assertEqual((deployment.contract_address, deployment.decimals), (contract, decimals))
                self.assertIsNone(Asset.objects.native_for_chain("base"))
                with self.assertRaisesRegex(ValueError, "unavailable"):
                    native_asset_for_chain("base")
                with patch("wallets.services.chain.get_blockchain_client") as provider:
                    self.assertIsNone(fetch_chain_balance(wallet, eth))
                provider.assert_not_called()

    def test_an_unrelated_native_row_does_not_answer_for_base(self):
        unrelated = Asset.objects.create(symbol="AAA", name="Other coin", asset_type="native_crypto")
        AssetChainDeployment.objects.create(asset=unrelated, chain="base")
        self.assertIsNone(Asset.objects.native_for_chain("base"))
        self.assertEqual(native_asset_for_chain("base").symbol, "ETH")

    def test_seed_refuses_to_reclassify_a_token_occupying_the_native_symbol(self):
        asset = Asset.objects.create(symbol="ETH", name="Wrong token", asset_type="erc20_token")
        with self.assertRaisesRegex(ValueError, "not the native coin"):
            AssetSyncService.ensure_supported_assets()
        asset.refresh_from_db()
        self.assertEqual(asset.asset_type, "erc20_token")
        self.assertFalse(asset.chain_deployments.exists())

    def test_missing_native_configuration_is_a_service_error_for_native_and_token_transfers(self):
        tenant = make_tenant("missing-native")
        wallet = Wallet.objects.create(
            user_account=tenant.account, address="0x" + "a" * 40, chain="base", verification_status="VERIFIED"
        )
        eth = Asset.objects.create(symbol="ETH", name="Ether", asset_type="native_crypto")
        AssetChainDeployment.objects.create(asset=eth, chain="ethereum")
        Holding.objects.create(wallet=wallet, asset=eth, quantity=7)
        token = Asset.objects.create(symbol="USDC", name="USD Coin", asset_type="stablecoin", is_verified=True)
        contract = "0x" + "c" * 40
        AssetChainDeployment.objects.create(asset=token, chain="base", contract_address=contract, decimals=6)
        Holding.objects.create(wallet=wallet, asset=token, quantity=10)
        client = APIClient()
        client.force_authenticate(tenant.user)
        for payload in ({"amountEth": "1"}, {"amountToken": "1", "tokenContract": contract}):
            with self.subTest(payload=payload), patch("wallets.services.transfers.get_blockchain_client") as rpc:
                response = client.post(
                    f"/api/wallets/{wallet.pk}/prepare-transfer/",
                    {"toAddress": "0x" + "b" * 40, **payload},
                    format="json",
                )
                self.assertEqual(response.status_code, 503, response.data)
                self.assertIn("configuration", str(response.data))
                self.assertNotIn("0 ETH", str(response.data))
                rpc.assert_not_called()

    def test_the_seeded_base_holding_reads_the_base_rpc(self):
        tenant = make_tenant("base-native")
        wallet = Wallet.objects.create(user_account=tenant.account, address="0x" + "a" * 40, chain="base")
        AssetSyncService.ensure_supported_assets()
        provider = Mock()
        provider.get_native_balance.return_value = Decimal("7")
        with patch("wallets.services.chain.get_blockchain_client", return_value=provider) as factory:
            self.assertEqual(fetch_chain_balance(wallet, Asset.objects.get(symbol="ETH")), Decimal("7"))
        factory.assert_called_once_with("base")
        provider.get_native_balance.assert_called_once_with(wallet.address)
        provider.get_token_balance.assert_not_called()
