from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from web3 import Web3
from web3.providers.base import BaseProvider

from integrations.base_chain.client import (
    BROADCAST_ROUND_TRIPS,
    GAS_HEADROOM,
    BaseChainClient,
)
from integrations.base_chain.exceptions import BaseChainConnectionError

CHAIN_ID = 31337
OPERATOR_KEY = "0x" + "11" * 32
CONTRACT = "0x" + "9d" * 20
RECIPIENT = "0x" + "ab" * 20
MINT_ABI = [
    {
        "inputs": [{"name": "to", "type": "address"}, {"name": "amount", "type": "uint256"}],
        "name": "mint",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    }
]
ANSWERS = {
    "eth_chainId": hex(CHAIN_ID),
    "eth_getTransactionCount": hex(3),
    "eth_gasPrice": hex(10**9),
    "eth_estimateGas": hex(60000),
    "eth_sendRawTransaction": "0x" + "cd" * 32,
}


class CountingProvider(BaseProvider):

    endpoint_uri = "http://counted"

    def __init__(self):
        super().__init__()
        self.calls = []

    def is_connected(self, show_traceback: bool = False) -> bool:
        return True

    def make_request(self, method, params):
        self.calls.append(method)
        return {"jsonrpc": "2.0", "id": 1, "result": ANSWERS.get(method, "0x1")}


@override_settings(BLOCKCHAIN_CHAIN_ID=CHAIN_ID)
class ABroadcastCostsTheRoundTripsTheGraceIsDerivedFromTest(SimpleTestCase):

    def send_and_count(self):
        provider = CountingProvider()
        w3 = Web3(provider)
        contract = w3.eth.contract(address=Web3.to_checksum_address(CONTRACT), abi=MINT_ABI)
        mint = contract.functions.mint(Web3.to_checksum_address(RECIPIENT), 5)

        client = BaseChainClient.__new__(BaseChainClient)
        self.addCleanup(setattr, BaseChainClient, "_answered_chain_id", BaseChainClient._answered_chain_id)
        BaseChainClient._answered_chain_id = None

        with patch.object(BaseChainClient, "w3", w3):
            client.send_transaction(mint, OPERATOR_KEY, wait_for_receipt=False)

        return provider.calls

    def test_the_constant_is_the_number_of_calls_a_send_actually_makes(self):
        calls = self.send_and_count()

        self.assertEqual(len(calls), BROADCAST_ROUND_TRIPS, calls)

    def test_the_client_asks_the_chain_once_and_the_rest_are_web3s_own(self):
        calls = self.send_and_count()

        self.assertEqual(calls.count("eth_chainId"), 3, calls)

    def test_the_gas_is_estimated_once_rather_than_by_both_web3_and_the_client(self):
        calls = self.send_and_count()

        self.assertEqual(calls.count("eth_estimateGas"), 1, calls)


INTRINSIC_GAS = 23228


class ANodeRefusingToEstimateBelowIntrinsicGasTest(SimpleTestCase):

    class Node(CountingProvider):

        def make_request(self, method, params):
            if method == "eth_estimateGas":
                stated = params[0].get("gas")
                if stated is not None and int(stated, 16) < INTRINSIC_GAS:
                    return {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "error": {
                            "code": -32000,
                            "message": (
                                f"execution reverted: Transaction requires at least {INTRINSIC_GAS} gas "
                                f"but got {int(stated, 16)}"
                            ),
                        },
                    }
            return super().make_request(method, params)

    @override_settings(BLOCKCHAIN_CHAIN_ID=CHAIN_ID)
    def test_the_estimate_is_asked_for_without_a_gas_the_node_would_reject(self):
        provider = self.Node()
        w3 = Web3(provider)
        contract = w3.eth.contract(address=Web3.to_checksum_address(CONTRACT), abi=MINT_ABI)
        mint = contract.functions.mint(Web3.to_checksum_address(RECIPIENT), 5)

        client = BaseChainClient.__new__(BaseChainClient)
        self.addCleanup(setattr, BaseChainClient, "_answered_chain_id", BaseChainClient._answered_chain_id)
        BaseChainClient._answered_chain_id = None

        with patch.object(BaseChainClient, "w3", w3):
            built = client.build_transaction(mint, from_address=RECIPIENT)

        self.assertEqual(built["gas"], int(60000 * GAS_HEADROOM))


class TheCachedChainIdIsStillComparedTest(SimpleTestCase):

    def a_client(self):
        provider = CountingProvider()
        w3 = Web3(provider)
        client = BaseChainClient.__new__(BaseChainClient)
        self.addCleanup(setattr, BaseChainClient, "_answered_chain_id", BaseChainClient._answered_chain_id)
        BaseChainClient._answered_chain_id = None
        return client, w3, provider

    def test_a_second_call_expecting_another_chain_is_still_refused(self):
        client, w3, provider = self.a_client()

        with patch.object(BaseChainClient, "w3", w3):
            with override_settings(BLOCKCHAIN_CHAIN_ID=CHAIN_ID):
                self.assertEqual(client.assert_expected_chain(), CHAIN_ID)
            with override_settings(BLOCKCHAIN_CHAIN_ID=1):
                with self.assertRaises(BaseChainConnectionError):
                    client.assert_expected_chain()

        self.assertEqual(provider.calls.count("eth_chainId"), 1)
