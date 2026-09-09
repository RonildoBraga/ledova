from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, TestCase

from integrations.base_chain.client import BaseChainClient
from integrations.base_chain.exceptions import GasEstimationError
from shared.api.exceptions import custom_exception_handler
from shared.tests.reverts import RPC_HOST, RPC_KEY, actionable_reverts, provider_revert
from shared.tests.tenants import make_tenant
from tokens.exceptions import TransferPreparationException
from tokens.services.token_transfer_service import TokenTransferService

RPC_URL = "https://base-sepolia.g.alchemy.com/v2/pR3t3nd1ngT0B3aReAlK3y"
RECIPIENT = "0x" + "d" * 40
SENDER = "0x" + "a" * 40


def client_whose_estimate(behaviour) -> BaseChainClient:
    client = BaseChainClient.__new__(BaseChainClient)
    client._web3 = SimpleNamespace(
        eth=SimpleNamespace(estimate_gas=behaviour),
        to_checksum_address=lambda address: address,
    )
    return client


class TheNodeIsAskedWhetherATransactionWorksTest(SimpleTestCase):

    def tearDown(self):
        BaseChainClient._web3 = None

    def test_an_estimate_the_node_refuses_is_not_replaced_with_a_guess(self):
        client = client_whose_estimate(Mock(side_effect=ValueError("execution reverted")))

        with self.assertRaises(GasEstimationError):
            client.estimate_gas({"to": RECIPIENT})

    def test_the_estimate_carries_headroom_over_what_the_node_said(self):
        client = client_whose_estimate(Mock(return_value=100_000))

        self.assertEqual(client.estimate_gas({"to": RECIPIENT}), 120_000)

    def test_a_caller_that_states_its_own_limit_does_not_ask_the_node(self):
        estimate = Mock(side_effect=AssertionError("the node must not be asked"))
        client = client_whose_estimate(estimate)
        client.get_nonce = Mock(return_value=1)
        function = Mock()
        function.build_transaction.return_value = {}

        with patch.object(BaseChainClient, "chain_id", 84532), patch.object(BaseChainClient, "gas_price", 1):
            built = client.build_transaction(function, from_address=SENDER, gas=250_000)

        self.assertEqual(built["gas"], 250_000)
        estimate.assert_not_called()


class PreparingATransferAsksBeforeItGuessesTest(TestCase):

    def setUp(self):
        self.tenant = make_tenant("sender")
        self.token = self.tenant.deployed_token

    def service(self, estimate):
        service = TokenTransferService.__new__(TokenTransferService)
        service.chain_client = Mock()
        service.chain_client.to_checksum_address.side_effect = lambda address: address
        service.chain_client.get_nonce.return_value = 1
        service.chain_client.gas_price = 1
        service.chain_client.chain_id = 84532
        service.chain_client.estimate_gas = estimate
        contract = Mock()
        contract.functions.transfer.return_value._encode_transaction_data.return_value = "0xdata"
        service.chain_client.load_contract.return_value = contract
        return service

    @patch.object(TokenTransferService, "validate_transfer")
    def test_a_transfer_the_node_will_not_estimate_is_refused_rather_than_prepared(self, _validate):
        service = self.service(Mock(side_effect=GasEstimationError("the node would not estimate gas")))

        with self.assertRaises(TransferPreparationException):
            service.prepare_transfer(self.token, SENDER, RECIPIENT, 5)

    @patch.object(TokenTransferService, "validate_transfer")
    def test_the_refusal_does_not_carry_the_node_credentials_to_the_caller(self, _validate):
        service = self.service(Mock(side_effect=ConnectionError(f"Max retries exceeded with url: {RPC_URL}")))

        with self.assertRaises(TransferPreparationException) as refusal:
            service.prepare_transfer(self.token, SENDER, RECIPIENT, 5)

        self.assertNotIn("pR3t3nd1ngT0B3aReAlK3y", str(refusal.exception.detail))
        self.assertNotIn("alchemy.com", str(refusal.exception.detail))

    @patch.object(TokenTransferService, "validate_transfer")
    def test_a_transfer_the_node_can_estimate_carries_that_estimate(self, _validate):
        service = self.service(Mock(return_value=96_000))

        prepared = service.prepare_transfer(self.token, SENDER, RECIPIENT, 5)

        self.assertEqual(prepared["gas"], 96_000)

    @patch.object(TokenTransferService, "validate_transfer")
    def test_each_estimate_refusal_survives_the_real_wrapper_and_served_error_without_credentials(self, _validate):
        for payload, expected in actionable_reverts():
            with self.subTest(expected=expected):
                client = client_whose_estimate(Mock(side_effect=provider_revert(payload)))
                service = self.service(client.estimate_gas)
                with self.assertRaises(TransferPreparationException) as refusal:
                    service.prepare_transfer(self.token, SENDER, RECIPIENT, 5)
                with self.assertLogs("shared.api.exceptions", level="ERROR"):
                    response = custom_exception_handler(refusal.exception, {})
                self.assertEqual(response.status_code, 500)
                self.assertEqual(response.data["detail"], expected)
                self.assertNotIn(RPC_HOST, str(response.data))
                self.assertNotIn(RPC_KEY, str(response.data))

    @patch.object(TokenTransferService, "validate_transfer")
    def test_an_unknown_estimate_refusal_still_has_a_fixed_default(self, _validate):
        client = client_whose_estimate(Mock(side_effect=provider_revert("0xdeadbeef")))
        service = self.service(client.estimate_gas)
        with self.assertRaises(TransferPreparationException) as refusal:
            service.prepare_transfer(self.token, SENDER, RECIPIENT, 5)
        self.assertEqual(str(refusal.exception.detail), "Transfer preparation failed.")
