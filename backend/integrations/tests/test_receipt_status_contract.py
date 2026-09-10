from unittest.mock import patch

from django.test import SimpleTestCase
from web3 import Web3
from web3.providers.base import BaseProvider

from integrations.base_chain.client import BaseChainClient
from integrations.blockchain.bitcoin import BitcoinClient
from integrations.blockchain.ethereum import EthereumClient

TX_HASH = "0x" + "75" * 32


class ReceiptProvider(BaseProvider):
    def __init__(self, receipt):
        super().__init__()
        self.receipt = receipt
        self.calls = []

    def make_request(self, method, params):
        self.calls.append((method, params))
        if method != "eth_getTransactionReceipt":
            raise AssertionError(f"Unexpected provider method: {method}")
        return {"jsonrpc": "2.0", "id": 1, "result": self.receipt}


class ReceiptStatusContractTest(SimpleTestCase):
    def test_both_evm_adapters_normalize_rpc_hex_status_to_integer_outcomes(self):
        for client_type in (EthereumClient, BaseChainClient):
            for status in (0, 1):
                with self.subTest(adapter=client_type.__name__, status=status):
                    provider = ReceiptProvider({"status": hex(status), "transactionHash": TX_HASH})
                    client = client_type.__new__(client_type)
                    with patch.object(client_type, "w3", Web3(provider), create=True):
                        receipt = client.get_transaction_receipt(TX_HASH)
                    self.assertIs(type(receipt["status"]), int)
                    self.assertEqual(receipt["status"], status)
                    self.assertEqual(provider.calls, [("eth_getTransactionReceipt", [TX_HASH])])

    def test_both_evm_adapters_leave_missing_status_missing(self):
        for client_type in (EthereumClient, BaseChainClient):
            with self.subTest(adapter=client_type.__name__):
                provider = ReceiptProvider({"transactionHash": TX_HASH})
                client = client_type.__new__(client_type)
                with patch.object(client_type, "w3", Web3(provider), create=True):
                    receipt = client.get_transaction_receipt(TX_HASH)
                self.assertNotIn("status", receipt)
                self.assertEqual(provider.calls, [("eth_getTransactionReceipt", [TX_HASH])])

    def test_bitcoin_returns_only_a_positive_confirmation_receipt(self):
        client = BitcoinClient.__new__(BitcoinClient)
        with patch.object(client, "get_transaction", return_value={"confirmations": 3, "height": 812345}):
            receipt = client.get_transaction_receipt("synthetic-bitcoin-hash")
        self.assertIs(receipt["confirmed"], True)
        self.assertIs(type(receipt["confirmations"]), int)
        self.assertEqual(receipt["confirmations"], 3)
        self.assertEqual(receipt["block_height"], 812345)
        self.assertNotIn("status", receipt)
        for transaction in ({}, {"confirmations": 0}, {"confirmations": -1}):
            with self.subTest(transaction=transaction):
                with patch.object(client, "get_transaction", return_value=transaction):
                    self.assertIsNone(client.get_transaction_receipt("synthetic-bitcoin-hash"))
