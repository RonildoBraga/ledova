"""One chain-balance helper feeds holding sync and confirmation; one queryset resolves a chain's native asset."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase

from assets.models import Asset, AssetChainDeployment
from users.models import UserAccount
from wallets.models import Holding, Transaction, Wallet
from wallets.services.chain import fetch_chain_balance
from wallets.services.sync import WalletSyncService
from wallets.services.transaction_confirmation import TransactionConfirmationService
from wallets.services.transfers import TransferService

TOKEN = "0x" + "1" * 40


class ChainBalanceTest(TestCase):
    def setUp(self):
        account = UserAccount.objects.create(account_number="CHAIN-ACC")
        self.wallet = Wallet.objects.create(
            user_account=account, address="0x" + "a" * 40, chain="base", verification_status="VERIFIED"
        )
        self.eth = Asset.objects.create(symbol="ETH", name="Ether", asset_type="native_crypto", is_verified=True)
        AssetChainDeployment.objects.create(asset=self.eth, chain="ethereum")
        AssetChainDeployment.objects.create(asset=self.eth, chain="base")
        self.usdc = Asset.objects.create(symbol="USDC", name="USD Coin", asset_type="stablecoin", is_verified=True)
        AssetChainDeployment.objects.create(asset=self.usdc, chain="base", contract_address=TOKEN, decimals=6)
        self.client_mock = MagicMock()
        self.client_mock.get_native_balance.return_value = Decimal("2")
        self.client_mock.get_token_balance.return_value = Decimal("70")

    def test_native_for_chain_needs_an_active_contract_less_deployment(self):
        self.assertEqual(Asset.objects.native_for_chain("base"), self.eth)
        self.assertIsNone(Asset.objects.native_for_chain("bitcoin"))
        AssetChainDeployment.objects.filter(asset=self.eth, chain="base").update(is_active=False)
        self.assertIsNone(Asset.objects.native_for_chain("base"))

    def test_fetch_chain_balance_uses_the_wallet_chain_deployment(self):
        with patch("wallets.services.chain.get_blockchain_client", return_value=self.client_mock) as factory:
            self.assertEqual(fetch_chain_balance(self.wallet, self.eth), Decimal("2"))
            self.assertEqual(fetch_chain_balance(self.wallet, self.usdc), Decimal("70"))

        factory.assert_called_with("base")
        self.client_mock.get_native_balance.assert_called_once_with(self.wallet.address)
        self.client_mock.get_token_balance.assert_called_once_with(
            address=self.wallet.address, contract_address=TOKEN, decimals=6
        )

    def test_fetch_chain_balance_returns_none_without_deployment_or_on_rpc_failure(self):
        bitcoin = Asset.objects.create(symbol="BTC", name="Bitcoin", asset_type="native_crypto")
        with patch("wallets.services.chain.get_blockchain_client", side_effect=RuntimeError("rpc down")) as factory:
            self.assertIsNone(fetch_chain_balance(self.wallet, bitcoin))
            factory.assert_not_called()
            self.assertIsNone(fetch_chain_balance(self.wallet, self.eth))

    def test_holding_sync_writes_chain_balances_and_keeps_unreachable_ones(self):
        eth_holding = Holding.objects.create(wallet=self.wallet, asset=self.eth, quantity=Decimal("1"))
        usdc_holding = Holding.objects.create(wallet=self.wallet, asset=self.usdc, quantity=Decimal("5"))
        self.client_mock.get_token_balance.return_value = None

        with patch("wallets.services.chain.get_blockchain_client", return_value=self.client_mock):
            self.assertEqual(WalletSyncService._sync_holdings_from_blockchain(self.wallet), 1)

        eth_holding.refresh_from_db()
        usdc_holding.refresh_from_db()
        self.assertEqual(eth_holding.quantity, Decimal("2"))
        self.assertIsNotNone(eth_holding.last_synced_at)
        self.assertEqual(usdc_holding.quantity, Decimal("5"))

    def test_confirmation_corrects_the_holding_from_the_chain(self):
        holding = Holding.objects.create(wallet=self.wallet, asset=self.usdc, quantity=Decimal("5"))
        with patch("wallets.services.chain.get_blockchain_client", return_value=self.client_mock):
            TransactionConfirmationService._verify_holding_balance(self.wallet, self.usdc)
        holding.refresh_from_db()
        self.assertEqual(holding.quantity, Decimal("70"))

    def test_native_balance_for_transfers_comes_from_the_chain_native_holding(self):
        self.assertEqual(TransferService._get_native_balance(self.wallet), Decimal("0"))
        Holding.objects.create(wallet=self.wallet, asset=self.eth, quantity=Decimal("0.25"))
        self.assertEqual(TransferService._get_native_balance(self.wallet), Decimal("0.25"))

    def test_pending_transaction_resolves_the_native_asset_by_chain_before_symbol(self):
        with patch("wallets.services.transaction_confirmation.TransactionMonitoringService"):
            result = TransactionConfirmationService.create_pending_transaction(
                wallet=self.wallet, tx_hash="0xpending", to_address="0x" + "b" * 40, amount=Decimal("1")
            )

        self.assertEqual(result["status"], "pending")
        self.assertEqual(Transaction.objects.get(tx_hash="0xpending").asset, self.eth)
        self.assertEqual(Asset.objects.filter(symbol="ETH").count(), 1)
