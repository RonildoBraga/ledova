"""Wallet transfers reach the client for the wallet's own chain; Bitcoin keeps its branch; a token
contract the allowlist has not verified is refused before anything is prepared or broadcast."""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase
from rest_framework.test import APITestCase

from assets.models import Asset, AssetChainDeployment
from users.models import UserAccount, UserProfile
from wallets.exceptions import InvalidTransactionException, UnsupportedChainException
from wallets.models import Transaction, Wallet
from wallets.services.transfers import TransferService

FROM = "0x" + "a" * 40
TO = "0x" + "b" * 40
SIGNED = "0x02f8" + "0" * 60
QUARANTINED = "0x" + "bad" + "0" * 37
UNVERIFIED = SimpleNamespace(symbol="USDC-bad000", decimals=6, is_verified=False)


def _wallet(chain):
    return SimpleNamespace(chain=chain, address=FROM, uuid=uuid4())


@patch.object(TransferService, "_get_native_balance", return_value=Decimal("10"))
@patch("wallets.services.transfers.get_blockchain_client")
class TransferRoutingTest(SimpleTestCase):
    def test_base_native_prepare_uses_the_base_client(self, get_client, _balance):
        client = get_client.return_value
        client.get_gas_price.return_value = 10**9
        client.w3.eth.get_transaction_count.return_value = 3
        client.w3.eth.chain_id = 84532

        result = TransferService.prepare_transfer(_wallet("base"), to_address=TO, amount_eth="1")

        get_client.assert_called_once_with("base")
        self.assertEqual((result["transaction"]["nonce"], result["transaction"]["chainId"]), (3, 84532))

    @patch("wallets.services.transfers.prepare_erc20_transaction", return_value={"transaction": {}})
    @patch("wallets.models.Holding.objects")
    @patch("assets.models.Asset.get_by_chain_and_contract")
    def test_base_erc20_prepare_passes_the_chain_through(self, get_asset, holdings, prepare, get_client, _balance):
        get_asset.return_value = SimpleNamespace(symbol="USDC", decimals=6, is_verified=True)
        holdings.filter.return_value.first.return_value = None

        TransferService.prepare_transfer(_wallet("base"), to_address=TO, amount_token="1", token_contract=TO)

        self.assertEqual(prepare.call_args.kwargs["chain"], "base")
        get_client.assert_not_called()

    @patch.object(TransferService, "_schedule_confirmation_checks")
    def test_base_broadcast_uses_the_base_client(self, _schedule, get_client, _balance):
        get_client.return_value.broadcast_transaction.return_value = "0xhash"

        result = TransferService.broadcast_transfer(_wallet("BASE"), SIGNED)

        get_client.assert_called_once_with("base")
        self.assertEqual(result["txHash"], "0xhash")

    @patch("wallets.services.transfers.prepare_erc20_transaction")
    @patch("assets.models.Asset.get_by_chain_and_contract")
    def test_prepare_refuses_an_unknown_or_unverified_token_contract(self, get_asset, prepare, get_client, _balance):
        for asset in (None, UNVERIFIED):
            with self.subTest(asset=asset):
                get_asset.return_value = asset
                with self.assertRaises(InvalidTransactionException) as ctx:
                    TransferService.prepare_transfer(
                        _wallet("ethereum"), to_address=TO, amount_token="1", token_contract=QUARANTINED
                    )
                self.assertEqual(
                    str(ctx.exception.detail), f"Token contract {QUARANTINED} is not a verified asset on ethereum."
                )

        prepare.assert_not_called()
        get_client.assert_not_called()

    @patch.object(TransferService, "_schedule_confirmation_checks")
    @patch("wallets.services.transfers.broadcast_ethereum_transaction")
    @patch("assets.models.Asset.get_by_chain_and_contract")
    def test_broadcast_refuses_an_unverified_token_contract_before_the_chain_sees_it(
        self, get_asset, broadcast, schedule, get_client, _balance
    ):
        for asset in (None, UNVERIFIED):
            with self.subTest(asset=asset):
                get_asset.return_value = asset
                with self.assertRaises(InvalidTransactionException):
                    TransferService.broadcast_transfer(
                        _wallet("ethereum"), SIGNED, to_address=TO, amount="1", token_contract=QUARANTINED
                    )

        broadcast.assert_not_called()
        schedule.assert_not_called()
        get_client.assert_not_called()

    @patch("wallets.services.transfers.broadcast_bitcoin_transaction", return_value="btc-hash")
    @patch("wallets.services.transfers.prepare_bitcoin_transaction", return_value={"network": "BTC"})
    @patch.object(TransferService, "_schedule_confirmation_checks")
    def test_bitcoin_keeps_its_own_branch(self, _schedule, prepare, broadcast, get_client, _balance):
        wallet = _wallet("bitcoin")

        self.assertEqual(TransferService.prepare_transfer(wallet, to_address=TO, amount_btc="0.1"), {"network": "BTC"})
        self.assertEqual(TransferService.broadcast_transfer(wallet, SIGNED)["txHash"], "btc-hash")

        prepare.assert_called_once()
        broadcast.assert_called_once_with(SIGNED)
        get_client.assert_not_called()

    def test_unsupported_chain_is_rejected_by_name(self, get_client, _balance):
        for call in (
            lambda: TransferService.prepare_transfer(_wallet("solana"), to_address=TO, amount_eth="1"),
            lambda: TransferService.broadcast_transfer(_wallet("solana"), SIGNED),
        ):
            with self.assertRaises(UnsupportedChainException) as ctx:
                call()
            self.assertEqual(str(ctx.exception.detail), "SOLANA is not currently supported for transfers.")

        get_client.assert_not_called()


@patch.object(TransferService, "_schedule_confirmation_checks")
@patch("wallets.services.transfers.get_blockchain_client")
class QuarantinedContractTransferApiTest(APITestCase):
    """prepare-transfer and broadcast-transfer answer 400 for a quarantined contract and never reach the chain."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(email="routing@example.test", password="pw-12345678")
        profile = UserProfile.objects.create(user=self.user)
        account = UserAccount.objects.create(account_number="ROUTING")
        account.user_profiles.add(profile)
        self.wallet = Wallet.objects.create(
            user_account=account, address=FROM, chain="ethereum", verification_status="VERIFIED"
        )
        quarantined = Asset.objects.create(symbol="USDC-bad000", name="USDC", asset_type="erc20_token", decimals=6)
        AssetChainDeployment.objects.create(
            asset=quarantined, chain="ethereum", contract_address=QUARANTINED, decimals=6
        )
        self.client.force_authenticate(self.user)

    def test_prepare_transfer_returns_400_for_a_quarantined_contract(self, get_client, schedule):
        response = self.client.post(
            f"/api/wallets/{self.wallet.uuid}/prepare-transfer/",
            {"to_address": TO, "amount_token": "1", "token_contract": QUARANTINED},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"], f"Token contract {QUARANTINED} is not a verified asset on ethereum."
        )
        get_client.assert_not_called()

    def test_broadcast_transfer_returns_400_for_a_quarantined_contract_without_broadcasting(self, get_client, schedule):
        response = self.client.post(
            f"/api/wallets/{self.wallet.uuid}/broadcast-transfer/",
            {"signed_transaction": SIGNED, "to_address": TO, "amount": "1", "token_contract": QUARANTINED},
        )

        self.assertEqual(response.status_code, 400)
        get_client.assert_not_called()
        get_client.return_value.broadcast_transaction.assert_not_called()
        schedule.assert_not_called()
        self.assertFalse(Transaction.objects.filter(wallet=self.wallet).exists())
