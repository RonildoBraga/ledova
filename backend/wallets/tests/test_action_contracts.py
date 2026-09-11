from decimal import Decimal
from unittest.mock import Mock, patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.urls import include, path
from django.utils import timezone
from drf_spectacular.generators import SchemaGenerator
from eth_account.messages import encode_defunct
from rest_framework.routers import SimpleRouter
from rest_framework.test import APITestCase

from assets.models import Asset, AssetChainDeployment, AssetSnapshot
from assets.services.identity import native_asset_for_chain
from assets.views.asset import AssetViewSet
from portfolios.models import Portfolio
from portfolios.views.portfolio import PortfolioViewSet
from users.models import UserAccount, UserProfile
from wallets.models import Holding, Wallet
from wallets.tests.test_broadcast_transfer_guard import RECIPIENT, SIGNER, sign
from wallets.views.wallet import WalletViewSet


class WalletActionContractTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(email="wallet-contract@example.test", password="pw-12345678")
        profile = UserProfile.objects.create(user=cls.user)
        cls.account = UserAccount.objects.create(account_number="WALLET-CONTRACT")
        cls.account.user_profiles.add(profile)
        cls.wallet = Wallet.objects.create(
            user_account=cls.account, address=SIGNER.address, chain="base", verification_status="VERIFIED"
        )
        cls.fund_wallet(cls.wallet)
        cls.asset = native_asset_for_chain("base")
        cls.asset.is_verified = True
        cls.asset.save(update_fields=["is_verified"])
        AssetSnapshot.objects.create(asset=cls.asset, price=1, source_timestamp=timezone.now(), data_source="manual")
        cls.portfolio = Portfolio.objects.create(user_account=cls.account, name="Synthetic portfolio")
        cls.portfolio.wallets.add(cls.wallet)
        router = SimpleRouter()
        router.register("wallets", WalletViewSet, basename="wallet-contract")
        router.register("assets", AssetViewSet, basename="asset-contract")
        router.register("portfolios", PortfolioViewSet, basename="portfolio-contract")
        cls.document = SchemaGenerator(patterns=[path("api/", include(router.urls))]).get_schema(
            request=None, public=True
        )

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.client.force_authenticate(self.user)

    @staticmethod
    def fund_wallet(wallet):
        asset = native_asset_for_chain(wallet.chain)
        AssetChainDeployment.objects.get_or_create(asset=asset, chain=wallet.chain, contract_address=None)
        Holding.objects.create(wallet=wallet, asset=asset, quantity=10)

    def assert_shape(self, schema, body):
        if "$ref" in schema:
            schema = self.document["components"]["schemas"][schema["$ref"].rsplit("/", 1)[-1]]
        if body is None and schema.get("nullable"):
            return
        if "allOf" in schema:
            for candidate in schema["allOf"]:
                self.assert_shape(candidate, body)
            return
        if "oneOf" in schema:
            outcomes = []
            for candidate in schema["oneOf"]:
                try:
                    self.assert_shape(candidate, body)
                    return
                except AssertionError as mismatch:
                    outcomes.append(str(mismatch))
            self.fail("No documented response variant matches: " + "; ".join(outcomes))
        if isinstance(body, list):
            self.assertEqual(schema.get("type"), "array")
            for item in body:
                self.assert_shape(schema.get("items", {}), item)
        if isinstance(body, dict) and "properties" in schema:
            properties = {key.replace("_", "").lower(): value for key, value in schema["properties"].items()}
            received = {key.replace("_", "").lower(): value for key, value in body.items()}
            required = {key.replace("_", "").lower() for key in schema.get("required", [])}
            self.assertLessEqual(required, received.keys())
            self.assertLessEqual(received.keys(), properties.keys())
            for key, value in received.items():
                self.assert_shape(properties[key], value)

    def post_action(self, action, data=None, wallet=None, detail=True):
        wallet = wallet or self.wallet
        suffix = f"{wallet.uuid}/" if detail else ""
        response = self.client.post(f"/api/wallets/{suffix}{action}/", data or {}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        parameter = "{uuid}/" if detail else ""
        schema = self.document["paths"][f"/api/wallets/{parameter}{action}/"]["post"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]
        self.assert_shape(schema, response.json())
        return response.json()

    def test_list_actions_document_arrays_instead_of_pagination_envelopes(self):
        for resource, instance, action in (
            ("wallets", self.wallet, "holdings"),
            ("assets", self.asset, "snapshots"),
            ("portfolios", self.portfolio, "snapshots"),
        ):
            with self.subTest(resource=resource):
                response = self.client.get(f"/api/{resource}/{instance.uuid}/{action}/")
                self.assertEqual(response.status_code, 200, response.data)
                self.assertIsInstance(response.json(), list)
                operation = self.document["paths"][f"/api/{resource}/{{uuid}}/{action}/"]["get"]
                schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
                self.assert_shape(schema, response.json())

    @patch("wallets.tasks.sync_wallet.defer")
    def test_challenge_and_signature_responses_match_the_generated_contract(self, defer):
        challenge = self.post_action("request-verification")
        signature = SIGNER.sign_message(encode_defunct(text=challenge["challenge"])).signature.to_0x_hex()
        verified = self.post_action("verify-signature", {"signature": signature})
        self.assertEqual(verified["verificationStatus"], "VERIFIED")
        defer.assert_called_once()

    def test_a_skipped_sync_documents_its_actual_result_without_inventing_a_task_id(self):
        self.wallet.verification_status = "PENDING"
        self.wallet.save(update_fields=["verification_status"])
        result = self.post_action("sync")
        self.assertFalse(result["success"])
        self.assertEqual(result["syncResult"]["status"], "skipped")
        self.assertNotIn("taskId", result)

    @patch("wallets.services.balance.get_blockchain_client")
    def test_batch_balances_document_the_success_and_partial_failure_shapes(self, get_client):
        get_client.return_value.get_native_balance.side_effect = [Decimal("5"), RuntimeError("Synthetic failure")]
        result = self.post_action(
            "batch-check-balances",
            {"userAccount": str(self.account.pk), "addresses": [SIGNER.address, RECIPIENT], "chain": "base"},
            detail=False,
        )
        self.assertIn("balances", result)
        self.assertIn("errors", result)

    @patch("wallets.services.transfers.get_blockchain_client")
    def test_native_evm_preparation_documents_the_actual_rpc_result(self, get_client):
        client = get_client.return_value
        client.get_gas_price.return_value = 10**9
        client.w3.eth.get_transaction_count.return_value = 1
        client.w3.eth.chain_id = 31337
        result = self.post_action("prepare-transfer", {"toAddress": RECIPIENT, "amountEth": "1"})
        self.assertEqual(result["amountEth"], "1")

    @patch("wallets.services.transfers.get_blockchain_client")
    def test_bitcoin_preparation_keeps_its_distinct_documented_shape(self, get_client):
        wallet = Wallet.objects.create(
            user_account=self.account, address="tb1qsyntheticcontract", chain="bitcoin", verification_status="VERIFIED"
        )
        self.fund_wallet(wallet)
        get_client.return_value.get_gas_price.return_value = Decimal("2")
        result = self.post_action("prepare-transfer", {"toAddress": "tb1qrecipient", "amountBtc": "1"}, wallet=wallet)
        self.assertEqual(result["network"], "BTC")

    @patch("wallets.services.transfers.get_blockchain_client")
    def test_token_preparation_does_not_promise_native_transfer_amount_fields(self, get_client):
        address = "0x" + "c" * 40
        asset = Asset.objects.create(
            symbol="TST", name="Synthetic token", asset_type="stablecoin", decimals=6, is_verified=True
        )
        AssetChainDeployment.objects.create(asset=asset, chain="base", contract_address=address, decimals=6)
        Holding.objects.create(wallet=self.wallet, asset=asset, quantity=10)
        client = get_client.return_value
        client.get_gas_price.return_value = 10**9
        client.estimate_erc20_transfer_gas.return_value = 60000
        client.build_erc20_transfer_data.return_value = "0xa9059cbb"
        client.get_nonce.return_value = 1
        client.w3.eth.chain_id = 31337
        result = self.post_action(
            "prepare-transfer", {"toAddress": RECIPIENT, "amountToken": "1", "tokenContract": address}
        )
        self.assertEqual(result["amountToken"], "1")
        self.assertNotIn("amountEth", result)
        self.assertNotIn("totalCostEth", result)

    @patch("wallets.services.transfers._schedule_confirmation_checks")
    @patch("wallets.services.submissions.get_blockchain_client")
    def test_broadcast_documents_the_real_pending_transaction_fields(self, get_client, schedule):
        get_client.return_value.assert_expected_chain = Mock(return_value=settings.BLOCKCHAIN_CHAIN_ID)
        get_client.return_value.get_mined_nonce.return_value = {
            "chain_id": settings.BLOCKCHAIN_CHAIN_ID,
            "nonce": 0,
            "balance_wei": str(10**32),
            "block_number": 100,
            "block_hash": "0x" + "ab" * 32,
        }
        get_client.return_value.broadcast_transaction.return_value = "0x" + "1" * 64
        result = self.post_action("broadcast-transfer", {"signedTransaction": sign(to=RECIPIENT, value=10**18)})
        self.assertIn("transactionId", result["pendingTransaction"])
        self.assertEqual(result["pendingTransaction"]["holdingQuantity"], "8.999910000000000000")
        schedule.assert_called_once()
