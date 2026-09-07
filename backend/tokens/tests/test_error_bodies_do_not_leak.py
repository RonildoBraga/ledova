from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings
from requests.exceptions import ConnectionError as RequestsConnectionError

from shared.api.exceptions import custom_exception_handler
from tokens.services.token_transfer_service import TokenTransferService

KEY = "pR3t3nd1ngT0B3aReAlK3y"
RPC_URL = f"https://base-sepolia.g.alchemy.com/v2/{KEY}"
PROVIDER_TEXT = f"Max retries exceeded with url: {RPC_URL}"


def _rendered(exception):
    response = custom_exception_handler(exception, {})
    return str(response.data)


@override_settings(BLOCKCHAIN_RPC_URL=RPC_URL)
class TheNodeKeyNeverReachesAResponseBodyTest(SimpleTestCase):

    def _prepare_against_an_unreachable_node(self):
        service = TokenTransferService.__new__(TokenTransferService)
        service.chain_client = Mock()
        service.whitelist_service = Mock()
        service.validate_transfer = Mock()
        service.contract_address = Mock(return_value="0x" + "c" * 40)
        service.chain_client.get_nonce.side_effect = RequestsConnectionError(PROVIDER_TEXT)
        return service

    def test_the_probe_reaches_the_call_it_is_about(self):
        service = self._prepare_against_an_unreachable_node()

        with self.assertRaises(Exception):
            service.prepare_transfer(Mock(), "0x" + "a" * 40, "0x" + "b" * 40, 1)

        service.chain_client.get_nonce.assert_called_once()

    def test_the_key_is_absent_from_what_the_caller_receives(self):
        service = self._prepare_against_an_unreachable_node()

        with self.assertRaises(Exception) as caught:
            service.prepare_transfer(Mock(), "0x" + "a" * 40, "0x" + "b" * 40, 1)

        self.assertNotIn(KEY, _rendered(caught.exception))

    def test_the_provider_url_is_absent_too(self):
        service = self._prepare_against_an_unreachable_node()

        with self.assertRaises(Exception) as caught:
            service.prepare_transfer(Mock(), "0x" + "a" * 40, "0x" + "b" * 40, 1)

        self.assertNotIn("alchemy.com", _rendered(caught.exception))

    def test_the_caller_still_learns_that_preparation_failed(self):
        service = self._prepare_against_an_unreachable_node()

        with self.assertRaises(Exception) as caught:
            service.prepare_transfer(Mock(), "0x" + "a" * 40, "0x" + "b" * 40, 1)

        self.assertIn("Transfer preparation failed", _rendered(caught.exception))

    @patch("tokens.services.token_transfer_service.logger")
    def test_the_operator_still_gets_the_diagnostic(self, logger):
        service = self._prepare_against_an_unreachable_node()

        with self.assertRaises(Exception):
            service.prepare_transfer(Mock(), "0x" + "a" * 40, "0x" + "b" * 40, 1)

        self.assertIn(KEY, " ".join(str(call) for call in logger.error.call_args_list))
