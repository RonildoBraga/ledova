from decimal import Decimal
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from requests.exceptions import ConnectionError as RequestsConnectionError

from shared.api.exceptions import custom_exception_handler
from wallets.exceptions import BlockchainAPIError
from wallets.services.transfers import (
    broadcast_bitcoin_transaction,
    broadcast_ethereum_transaction,
    prepare_bitcoin_transaction,
    prepare_erc20_transaction,
    prepare_ethereum_transaction,
)

KEY = "pR3t3nd1ngT0B3aReAlK3y"
RPC_URL = f"https://base-sepolia.g.alchemy.com/v2/{KEY}"
PROVIDER_TEXT = f"Max retries exceeded with url: {RPC_URL}"

ADDRESS = "0x" + "a" * 40
CONTRACT = "0x" + "c" * 40

SEND_PATHS = (
    (
        "prepare_ethereum_transaction",
        lambda: prepare_ethereum_transaction("base", ADDRESS, ADDRESS, Decimal("1"), Decimal("10")),
        "Failed to prepare the transaction.",
    ),
    (
        "prepare_bitcoin_transaction",
        lambda: prepare_bitcoin_transaction("bc1qsender", "bc1qrecipient", Decimal("1"), Decimal("10")),
        "Failed to prepare the Bitcoin transaction.",
    ),
    (
        "prepare_erc20_transaction",
        lambda: prepare_erc20_transaction(
            "base", ADDRESS, ADDRESS, Decimal("1"), Decimal("10"), Decimal("10"), CONTRACT, "USDC", 6
        ),
        "Failed to prepare the ERC-20 transaction.",
    ),
    (
        "broadcast_ethereum_transaction",
        lambda: broadcast_ethereum_transaction("base", "0xdeadbeef"),
        "Failed to broadcast the Ethereum transaction.",
    ),
    (
        "broadcast_bitcoin_transaction",
        lambda: broadcast_bitcoin_transaction("0xdeadbeef"),
        "Failed to broadcast the Bitcoin transaction.",
    ),
)


def _rendered(exception):
    return str(custom_exception_handler(exception, {}).data)


@override_settings(BLOCKCHAIN_RPC_URL=RPC_URL)
class TheNodeKeyNeverReachesASendResponseTest(SimpleTestCase):

    def _prepare_against_an_unreachable_node(self):
        with patch("wallets.services.transfers.get_blockchain_client") as client:
            client.side_effect = RequestsConnectionError(PROVIDER_TEXT)
            with self.assertRaises(Exception) as caught:
                prepare_ethereum_transaction("base", ADDRESS, "0x" + "b" * 40, Decimal("1"), Decimal("10"))
        return caught.exception

    def test_a_failed_preparation_does_not_serve_the_key(self):
        self.assertNotIn(KEY, _rendered(self._prepare_against_an_unreachable_node()))

    def test_a_failed_preparation_does_not_serve_the_provider_url(self):
        self.assertNotIn("alchemy.com", _rendered(self._prepare_against_an_unreachable_node()))

    def test_the_caller_still_learns_the_preparation_failed(self):
        self.assertIn("Failed to prepare the transaction", _rendered(self._prepare_against_an_unreachable_node()))

    @patch("wallets.services.transfers.get_blockchain_client")
    def test_a_failed_broadcast_does_not_serve_the_key(self, chain_client):
        chain_client.return_value.broadcast_transaction.side_effect = RequestsConnectionError(PROVIDER_TEXT)

        with self.assertRaises(Exception) as caught:
            broadcast_ethereum_transaction("base", "0xdeadbeef")

        rendered = _rendered(caught.exception)
        self.assertNotIn(KEY, rendered)
        self.assertIn("Failed to broadcast the Ethereum transaction", rendered)

    @patch("wallets.services.transfers.logger")
    @patch("wallets.services.transfers.get_blockchain_client")
    def test_the_operator_still_gets_the_diagnostic(self, chain_client, logger):
        chain_client.return_value.broadcast_transaction.side_effect = RequestsConnectionError(PROVIDER_TEXT)

        with self.assertRaises(Exception):
            broadcast_ethereum_transaction("base", "0xdeadbeef")

        self.assertIn(KEY, " ".join(str(call) for call in logger.error.call_args_list))

    def test_every_send_path_answers_with_its_own_fixed_message(self):
        for name, call_the_path, message in SEND_PATHS:
            with self.subTest(path=name):
                with patch("wallets.services.transfers.get_blockchain_client") as client:
                    client.side_effect = RequestsConnectionError(PROVIDER_TEXT)
                    with self.assertRaises(BlockchainAPIError) as caught:
                        call_the_path()

                rendered = _rendered(caught.exception)
                self.assertNotIn(KEY, rendered)
                self.assertNotIn("alchemy.com", rendered)
                self.assertIn(message, rendered)
