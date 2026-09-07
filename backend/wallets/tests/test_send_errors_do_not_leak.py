from decimal import Decimal
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from requests.exceptions import ConnectionError as RequestsConnectionError

from shared.api.exceptions import custom_exception_handler
from wallets.services.transfers import (
    broadcast_ethereum_transaction,
    prepare_ethereum_transaction,
)

KEY = "pR3t3nd1ngT0B3aReAlK3y"
RPC_URL = f"https://base-sepolia.g.alchemy.com/v2/{KEY}"
PROVIDER_TEXT = f"Max retries exceeded with url: {RPC_URL}"


def _rendered(exception):
    return str(custom_exception_handler(exception, {}).data)


@override_settings(BLOCKCHAIN_RPC_URL=RPC_URL)
class TheNodeKeyNeverReachesASendResponseTest(SimpleTestCase):

    def _prepare_against_an_unreachable_node(self):
        with patch("wallets.services.transfers.get_blockchain_client") as client:
            client.side_effect = RequestsConnectionError(PROVIDER_TEXT)
            with self.assertRaises(Exception) as caught:
                prepare_ethereum_transaction("base", "0x" + "a" * 40, "0x" + "b" * 40, Decimal("1"), Decimal("10"))
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
