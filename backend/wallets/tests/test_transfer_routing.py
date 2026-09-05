"""Wallet transfers reach the client for the wallet's own chain; Bitcoin keeps its branch."""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from django.test import SimpleTestCase

from wallets.exceptions import UnsupportedChainException
from wallets.services.transfers import TransferService

FROM = "0x" + "a" * 40
TO = "0x" + "b" * 40
SIGNED = "0x02f8" + "0" * 60


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
        get_asset.return_value = SimpleNamespace(symbol="USDC", decimals=6)
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
