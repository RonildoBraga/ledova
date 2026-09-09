from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from integrations.blockchain.ethereum import EthereumClient

ADDRESS = "0x" + "31" * 20
CONTRACT = "0x" + "32" * 20


def transfer(number, contract=None):
    return {
        "hash": "0x" + format(number, "064x"),
        "blockNum": hex(number),
        "from": ADDRESS,
        "to": "0x" + "33" * 20,
        "value": 1,
        "asset": "LATE" if contract else "ETH",
        "rawContract": {"address": contract, "decimal": "0x12"},
        "metadata": {"blockTimestamp": "2026-09-01T00:00:00Z"},
    }


def history_client():
    client = EthereumClient.__new__(EthereumClient)
    client.rpc_url = "https://provider.example.test/synthetic"
    client.asset_transfer_history_enabled = True
    return client


class TransferHistoryPaginationTest(SimpleTestCase):
    def setUp(self):
        self.client = history_client()
        self.requests = []
        self.pages = []
        post = patch("integrations.blockchain.ethereum.requests.post", side_effect=self.respond)
        self.addCleanup(post.stop)
        post.start()
        receipts = patch.object(self.client, "get_transaction_receipt", return_value=None)
        self.addCleanup(receipts.stop)
        self.receipts = receipts.start()

    def respond(self, url, *, json, headers, timeout):
        self.requests.append(deepcopy(json["params"][0]))
        page = self.pages.pop(0)
        if isinstance(page, Exception):
            raise page
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: page)

    def test_both_directions_follow_their_own_pages_and_keep_the_newest_transfer(self):
        self.pages = [
            {"result": {"transfers": [transfer(i) for i in range(1, 1001)], "pageKey": "out-next"}},
            {"result": {"transfers": [transfer(1001, CONTRACT)]}},
            {"result": {"transfers": [transfer(1001, CONTRACT)], "pageKey": "in-next"}},
            {"result": {"transfers": [transfer(1002)]}},
        ]
        rows = self.client.get_transaction_history(ADDRESS, from_block=0, to_block=1200)
        self.assertEqual(len(rows), 1002)
        self.assertEqual(rows[0]["block_number"], 1002)
        self.assertEqual(rows[1]["contract_address"], CONTRACT)
        self.assertEqual([p.get("pageKey") for p in self.requests], [None, "out-next", None, "in-next"])
        for index, params in enumerate(self.requests):
            self.assertEqual(params["fromBlock"], "0x0")
            self.assertEqual(params["toBlock"], "0x4b0")
            self.assertEqual(params["maxCount"], "0x3e8")
            self.assertEqual(params["order"], "desc")
            self.assertEqual(params["fromAddress" if index < 2 else "toAddress"].lower(), ADDRESS)

    def test_a_later_page_failure_does_not_return_the_partial_first_page_as_history(self):
        self.pages = [
            {"result": {"transfers": [transfer(1)], "pageKey": "next"}},
            {"error": {"message": "synthetic private provider failure"}},
        ]
        with self.assertRaises(RuntimeError):
            self.client.get_transaction_history(ADDRESS)
        self.receipts.assert_not_called()

    def test_a_repeated_cursor_fails_instead_of_looping_or_claiming_completeness(self):
        self.pages = [{"result": {"transfers": [], "pageKey": "again"}}] * 2
        with self.assertRaises(RuntimeError):
            self.client.get_transaction_history(ADDRESS)
        self.assertEqual(len(self.requests), 2)

    def test_a_malformed_result_is_not_an_empty_history(self):
        self.pages = [{"result": {}}]
        with self.assertRaises(RuntimeError):
            self.client.get_transaction_history(ADDRESS)

    def test_pagination_finishes_before_slow_receipt_reads_can_expire_the_cursor(self):
        self.pages = [
            {"result": {"transfers": [transfer(1)], "pageKey": "next"}},
            {"result": {"transfers": [transfer(2)]}},
        ]
        observed = []
        self.receipts.side_effect = lambda tx_hash: observed.append(len(self.requests))
        rows = self.client._fetch_asset_transfers(from_address=ADDRESS)
        self.assertEqual(len(rows), 2)
        self.assertEqual(observed, [2, 2])

    def test_exceeding_the_page_limit_refuses_to_report_a_truncated_history(self):
        self.client.HISTORY_PAGE_LIMIT = 2
        self.pages = [
            {"result": {"transfers": [transfer(1)], "pageKey": "second"}},
            {"result": {"transfers": [transfer(2)], "pageKey": "third"}},
        ]
        with self.assertRaises(RuntimeError):
            self.client.get_transaction_history(ADDRESS)
        self.assertEqual(len(self.requests), 2)

    def test_an_explicit_genesis_upper_bound_is_not_replaced_with_latest(self):
        self.pages = [{"result": {"transfers": []}}] * 2
        self.assertEqual(self.client.get_transaction_history(ADDRESS, to_block=0), [])
        self.assertEqual([params["toBlock"] for params in self.requests], ["0x0", "0x0"])
