from types import SimpleNamespace
from unittest.mock import Mock

from django.test import SimpleTestCase, override_settings

from integrations.base_chain.client import BaseChainClient
from integrations.base_chain.exceptions import BaseChainConnectionError
from integrations.blockchain.bitcoin import BitcoinClient, is_bitcoin_address_valid
from integrations.blockchain.ethereum import EthereumClient


class RuntimeChainBoundaryTests(SimpleTestCase):
    def test_bitcoin_address_policy_rejects_mainnet(self):
        self.assertTrue(is_bitcoin_address_valid("mipcBbFg9gMiCh81Kj8tqqdgoZub1ZJRfn", "test"))
        self.assertFalse(is_bitcoin_address_valid("1BoatSLRHtKNngkdXEeobR76b53LETtpyT", "test"))
        self.assertFalse(is_bitcoin_address_valid("mipcBbFg9gMiCh81Kj8tqqdgoZub1ZJRfn", "regtest"))

    @override_settings(BLOCKCHAIN_CHAIN_ID=84532)
    def test_base_client_rejects_an_endpoint_on_the_wrong_chain(self):
        client = BaseChainClient.__new__(BaseChainClient)
        client._web3 = SimpleNamespace(eth=SimpleNamespace(chain_id=8453))

        with self.assertRaisesRegex(BaseChainConnectionError, "expected chain 84532"):
            client.assert_expected_chain()

    def test_ethereum_client_rejects_an_endpoint_on_the_wrong_chain(self):
        client = EthereumClient.__new__(EthereumClient)
        client.expected_chain_id = 84532
        client.w3 = SimpleNamespace(eth=SimpleNamespace(chain_id=8453))

        with self.assertRaisesRegex(ConnectionError, "expected chain 84532"):
            client.assert_expected_chain()

    def test_ethereum_broadcast_rechecks_chain_before_send(self):
        client = EthereumClient.__new__(EthereumClient)
        client.expected_chain_id = 84532
        send = Mock()
        client.w3 = SimpleNamespace(eth=SimpleNamespace(chain_id=8453, send_raw_transaction=send))

        with self.assertRaises(ConnectionError):
            client.broadcast_transaction("0xdeadbeef")
        send.assert_not_called()

    def test_bitcoin_client_rejects_an_endpoint_on_the_wrong_network(self):
        client = BitcoinClient.__new__(BitcoinClient)
        client.expected_network = "test"
        client._rpc_call = Mock(return_value={"chain": "main"})

        with self.assertRaisesRegex(ConnectionError, "expected 'test'"):
            client.assert_expected_network()

    def test_bitcoin_broadcast_rechecks_network_before_send(self):
        client = BitcoinClient.__new__(BitcoinClient)
        client.expected_network = "test"
        client._rpc_call = Mock(return_value={"chain": "main"})

        with self.assertRaises(ConnectionError):
            client.broadcast_transaction("deadbeef")
        self.assertEqual(client._rpc_call.call_count, 1)
