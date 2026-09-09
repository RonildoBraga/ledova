from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

from rest_framework.test import APITestCase
from web3 import Web3

from assets.models import Asset, AssetChainDeployment
from integrations.blockchain.ethereum import EthereumClient
from shared.tests.tenants import make_tenant
from wallets.exceptions import InvalidTransactionException
from wallets.models import Holding, Wallet
from wallets.services.signed_transfers import plan_signed_transfer
from wallets.services.transaction_confirmation import TransactionConfirmationService
from wallets.services.transfers import TransferService
from wallets.tests.test_broadcast_transfer_guard import (
    RECIPIENT,
    SIGNER,
    erc20_transfer_data,
    sign,
)

BASE_CONTRACT = Web3.to_checksum_address("0x" + "c" * 40)
ETH_CONTRACT = Web3.to_checksum_address("0x" + "d" * 40)


class DeploymentSelectionTest(APITestCase):
    def setUp(self):
        self.tenant = make_tenant("deployment-selection")
        self.client.force_authenticate(self.tenant.user)
        self.wallet = Wallet.objects.create(user_account=self.tenant.account, address=SIGNER.address, chain="base")
        self.asset = Asset.objects.create(
            symbol="MULTI", name="Multi-chain token", asset_type="erc20_token", is_verified=True
        )
        self.base = AssetChainDeployment.objects.create(
            asset=self.asset, chain="base", contract_address=BASE_CONTRACT, decimals=0
        )
        self.ethereum = AssetChainDeployment.objects.create(
            asset=self.asset, chain="ethereum", contract_address=ETH_CONTRACT, decimals=6
        )
        native = Asset.objects.create(symbol="ETH", name="Ether", asset_type="native_crypto")
        AssetChainDeployment.objects.create(asset=native, chain="base")
        Holding.objects.create(wallet=self.wallet, asset=native, quantity=5)
        Holding.objects.create(wallet=self.wallet, asset=self.asset, quantity=100)

    def test_asset_summary_never_picks_one_of_two_active_networks(self):
        response = self.client.get(f"/api/assets/{self.asset.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["chain"])
        self.assertIsNone(response.json()["contractAddress"])
        self.assertEqual(
            {(row["chain"], row["contractAddress"], row["decimals"]) for row in response.json()["chainDeployments"]},
            {("base", BASE_CONTRACT, 0), ("ethereum", ETH_CONTRACT, 6)},
        )
        response = self.client.get(f"/api/wallets/{self.wallet.pk}/holdings/")
        token = next(row for row in response.json() if row["assetSymbol"] == "MULTI")
        self.assertEqual(token["chain"], "base")
        self.assertIsNone(token["asset"]["contractAddress"])

    def test_only_one_active_deployment_may_supply_the_compatibility_fields(self):
        self.base.is_active = False
        self.base.save(update_fields=["is_active"])
        response = self.client.get(f"/api/assets/{self.asset.pk}/")
        self.assertEqual((response.json()["chain"], response.json()["contractAddress"]), ("ethereum", ETH_CONTRACT))
        self.ethereum.is_active = False
        self.ethereum.save(update_fields=["is_active"])
        response = self.client.get(f"/api/assets/{self.asset.pk}/")
        self.assertIsNone(response.json()["chain"])
        self.assertIsNone(response.json()["contractAddress"])

    def test_preparation_estimates_and_encodes_using_the_wallet_deployments_decimals(self):
        provider = Mock()
        provider.estimate_erc20_transfer_gas.return_value = 50_000
        provider.get_gas_price.return_value = 1
        provider.get_nonce.return_value = 0
        provider.w3.eth.chain_id = 84532
        encoder = SimpleNamespace(w3=Web3(), ERC20_ABI=EthereumClient.ERC20_ABI)
        provider.build_erc20_transfer_data.side_effect = lambda **kwargs: EthereumClient.build_erc20_transfer_data(
            encoder, **kwargs
        )
        with patch("wallets.services.transfers.get_blockchain_client", return_value=provider):
            result = TransferService.prepare_transfer(
                self.wallet, RECIPIENT, amount_token="3", token_contract=BASE_CONTRACT
            )
        provider.estimate_erc20_transfer_gas.assert_called_once_with(
            from_address=self.wallet.address,
            contract_address=BASE_CONTRACT,
            recipient=RECIPIENT,
            amount=Decimal("3"),
            decimals=0,
        )
        self.assertEqual(result["token_decimals"], 0)
        self.assertEqual(result["transaction"]["to"], BASE_CONTRACT)
        self.assertEqual(int(result["transaction"]["data"][-64:], 16), 3)

    def test_signed_units_are_interpreted_on_the_wallet_network(self):
        signed = sign(to=BASE_CONTRACT, data=erc20_transfer_data(RECIPIENT, 3))
        plan = plan_signed_transfer(self.wallet, signed)
        self.assertEqual((plan.token_contract, plan.amount), (BASE_CONTRACT, Decimal("3")))

    def test_preparation_refuses_fractional_base_units_before_any_provider_call(self):
        for decimals, amount in ((0, "1.5"), (0, "0.5"), (6, "1.0000001"), (18, "12345678901.0000000000000000001")):
            with self.subTest(decimals=decimals, amount=amount):
                self.base.decimals = decimals
                self.base.save(update_fields=["decimals"])
                with patch("wallets.services.transfers.get_blockchain_client") as provider:
                    response = self.client.post(
                        f"/api/wallets/{self.wallet.pk}/prepare-transfer/",
                        {"toAddress": RECIPIENT, "amountToken": amount, "tokenContract": BASE_CONTRACT},
                        format="json",
                    )
                self.assertEqual(response.status_code, 400, response.content)
                self.assertIn("decimal places", response.json()["detail"])
                provider.assert_not_called()

    def test_actual_encoder_preserves_exact_units_and_refuses_rounding(self):
        encoder = SimpleNamespace(w3=Web3(), ERC20_ABI=EthereumClient.ERC20_ABI)
        for amount, decimals, units in (
            ("3.000", 0, 3),
            ("1.500000", 6, 1_500_000),
            ("12345678901.123456789012345678", 18, 12345678901123456789012345678),
        ):
            with self.subTest(amount=amount, decimals=decimals):
                encoded = EthereumClient.build_erc20_transfer_data(
                    encoder, BASE_CONTRACT, RECIPIENT, Decimal(amount), decimals
                )
                self.assertEqual(int(encoded[-64:], 16), units)
        for amount, decimals in (("1.5", 0), ("0.5", 0), ("1.0000001", 6), ("1e78", 0), ("NaN", 0)):
            with self.subTest(amount=amount, decimals=decimals):
                with self.assertRaises(ValueError):
                    EthereumClient.build_erc20_transfer_data(
                        encoder, BASE_CONTRACT, RECIPIENT, Decimal(amount), decimals
                    )

    def test_a_deployment_disabled_during_resolution_never_falls_back_to_asset_decimals(self):
        original = TransactionConfirmationService.resolve_transfer_asset

        def resolve_then_disable(wallet, contract):
            asset = original(wallet, contract)
            AssetChainDeployment.objects.filter(pk=self.base.pk).update(is_active=False)
            return asset

        signed = sign(to=BASE_CONTRACT, data=erc20_transfer_data(RECIPIENT, 3))
        with patch.object(TransactionConfirmationService, "resolve_transfer_asset", side_effect=resolve_then_disable):
            with self.assertRaisesRegex(InvalidTransactionException, "configuration"):
                plan_signed_transfer(self.wallet, signed)
