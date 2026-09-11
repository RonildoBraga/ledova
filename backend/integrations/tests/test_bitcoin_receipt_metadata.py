from decimal import Decimal, localcontext
from unittest.mock import Mock, call

from django.test import SimpleTestCase

from integrations.blockchain.bitcoin import BitcoinClient

TX_HASH = "31" * 32
BLOCK_HASH = "41" * 32


class BitcoinReceiptMetadataTest(SimpleTestCase):
    def setUp(self):
        self.client = object.__new__(BitcoinClient)
        self.transaction = {
            "txid": TX_HASH,
            "confirmations": 2,
            "blockhash": BLOCK_HASH,
            "fee": Decimal("0.00012345"),
        }
        self.header = {"hash": BLOCK_HASH, "height": 203, "time": 1700000000}
        self.client._rpc_call = Mock(side_effect=self.rpc)

    def rpc(self, method, params):
        if method == "getrawtransaction":
            result = dict(self.transaction)
            if params[1] != 2:
                result.pop("fee", None)
            return result
        if method == "getblockheader":
            if isinstance(self.header, Exception):
                raise self.header
            return self.header
        raise AssertionError(method)

    def test_receipt_uses_verbose_fee_and_the_identified_headers_height(self):
        self.transaction["height"] = 999
        receipt = self.client.get_transaction_receipt(TX_HASH)
        self.assertEqual(
            receipt,
            {
                "tx_hash": TX_HASH,
                "confirmed": True,
                "confirmations": 2,
                "block_hash": BLOCK_HASH,
                "block_height": 203,
                "fee": 12345,
            },
        )
        self.assertEqual(
            self.client._rpc_call.call_args_list,
            [call("getrawtransaction", [TX_HASH, 2]), call("getblockheader", [BLOCK_HASH])],
        )

    def test_fee_units_are_exact_including_zero_and_one_satoshi(self):
        for value, expected in (
            (0, 0),
            (Decimal("0.00000001"), 1),
            (Decimal("0.00012345"), 12345),
            (Decimal("0.0001234500"), 12345),
            (Decimal("21000000"), 2100000000000000),
        ):
            with self.subTest(value=value), localcontext() as context:
                context.prec = 4
                self.transaction["fee"] = value
                receipt = self.client.get_transaction_receipt(TX_HASH)
                self.assertEqual(receipt.get("fee"), expected)

    def test_missing_or_invalid_fee_remains_unknown_without_losing_inclusion(self):
        for value in (
            None,
            True,
            False,
            "0.0001",
            0.0001,
            [],
            {},
            Decimal("NaN"),
            Decimal("sNaN"),
            Decimal("Infinity"),
            Decimal("-Infinity"),
            Decimal("-0.0001"),
            Decimal("0.000000001"),
            Decimal("21000000.00000001"),
            Decimal("1e999999"),
            Decimal("1e-999999"),
            Decimal("0.1234567800000000000000000000000000000000000000"),
        ):
            with self.subTest(value=value):
                self.transaction["fee"] = value
                receipt = self.client.get_transaction_receipt(TX_HASH)
                self.assertIsNone(receipt.get("fee"))
                self.assertIs(receipt["confirmed"], True)
        del self.transaction["fee"]
        self.assertIsNone(self.client.get_transaction_receipt(TX_HASH).get("fee"))

    def test_missing_malformed_or_unavailable_headers_cannot_supply_height(self):
        self.transaction["height"] = 999
        for header in (
            None,
            [],
            {},
            {"height": 203},
            {"hash": "51" * 32, "height": 203},
            ConnectionError("Synthetic unavailable header"),
        ):
            with self.subTest(header=header):
                self.header = header
                receipt = self.client.get_transaction_receipt(TX_HASH)
                self.assertIsNone(receipt["block_height"])
                self.assertEqual(receipt.get("fee"), 12345)
                self.assertIs(receipt["confirmed"], True)

    def test_header_heights_are_bounded_integers_and_allow_genesis(self):
        for height in (None, True, -1, 1.5, "203", [], 2**63):
            with self.subTest(height=height):
                self.header["height"] = height
                self.assertIsNone(self.client.get_transaction_receipt(TX_HASH)["block_height"])
        self.header["height"] = 0
        self.assertEqual(self.client.get_transaction_receipt(TX_HASH)["block_height"], 0)

    def test_invalid_block_identity_is_not_used_to_request_a_header(self):
        for block_hash in (None, "", "not-a-hash", "41" * 31, True, []):
            with self.subTest(block_hash=block_hash):
                self.transaction["blockhash"] = block_hash
                self.client._rpc_call.reset_mock()
                receipt = self.client.get_transaction_receipt(TX_HASH)
                self.assertIsNone(receipt["block_hash"])
                self.assertIsNone(receipt["block_height"])
                self.assertEqual(receipt.get("fee"), 12345)
                self.client._rpc_call.assert_called_once_with("getrawtransaction", [TX_HASH, 2])

    def test_unknown_outcome_or_other_transaction_cannot_supply_metadata(self):
        for changes in (
            {"txid": "51" * 32},
            {"txid": None},
            {"confirmations": 0},
            {"confirmations": -1},
            {"confirmations": True},
            {"confirmations": "2"},
        ):
            with self.subTest(changes=changes):
                original = self.transaction
                self.transaction = {**original, **changes}
                self.client._rpc_call.reset_mock()
                self.assertIsNone(self.client.get_transaction_receipt(TX_HASH))
                self.assertEqual(self.client._rpc_call.call_count, 1)
                self.transaction = original

    def test_ordinary_transaction_details_keep_the_default_verbosity(self):
        self.assertEqual(self.client.get_transaction(TX_HASH)["txid"], TX_HASH)
        self.client._rpc_call.assert_called_once_with("getrawtransaction", [TX_HASH, 1])
