from copy import deepcopy
from unittest.mock import Mock

from django.test import SimpleTestCase
from eth_account import Account
from eth_account._utils.legacy_transactions import Transaction as LegacyTransaction
from eth_account.typed_transactions import TypedTransaction
from web3 import Web3

from wallets.services.nonce_evidence import MAX_PROBES, collect_nonce_evidence

BLOCK_HASH = "0x" + "ab" * 32
HEAD_HASH = "0x" + "cd" * 32
ANCHOR_HASH = "0x" + "ef" * 32


class NonceEvidenceTest(SimpleTestCase):
    def setUp(self):
        self.signer = Account.create()
        self.recipient = Account.create().address
        self.original = self.signed()
        self.height = 901234
        self.head = {"number": 1000000, "hash": HEAD_HASH}
        self.provider = Mock(spec=["assert_expected_chain", "get_transaction_receipt", "w3"])
        self.provider.assert_expected_chain.return_value = 84532
        self.provider.w3.eth.get_transaction_count.side_effect = lambda address, height: (
            0 if height == 0 else 3 if height < self.height else 4
        )
        self.provider.w3.eth.get_block.side_effect = self.block
        self.set_candidate(self.signed(gasPrice=4 * 10**9))

    def signed(self, **overrides):
        fields = {
            "chainId": 84532,
            "nonce": 3,
            "to": self.recipient,
            "value": 10**18,
            "gas": 90000,
            "gasPrice": 2 * 10**9,
            **overrides,
        }
        if fields.get("type") == 2:
            fields.pop("gasPrice")
        return self.signer.sign_transaction(fields)

    def set_candidate(self, signed):
        raw = signed.raw_transaction
        fields = (
            TypedTransaction.from_bytes(raw).as_dict() if raw[0] < 128 else LegacyTransaction.from_bytes(raw).as_dict()
        )
        self.tx = {
            **fields,
            "type": fields.get("type", 0),
            "chainId": 84532,
            "hash": signed.hash,
            "from": self.signer.address,
            "to": Web3.to_checksum_address(fields["to"]),
            "input": fields["data"],
            "blockHash": BLOCK_HASH,
            "blockNumber": self.height,
            "transactionIndex": 0,
            "r": fields["r"].to_bytes(32, "big"),
            "s": fields["s"].to_bytes(32, "big"),
        }
        self.tx.pop("data")
        if "accessList" in fields:
            self.tx["accessList"] = [
                {
                    "address": Web3.to_checksum_address(item["address"]),
                    "storageKeys": ["0x" + key.to_bytes(32, "big").hex() for key in item["storageKeys"]],
                }
                for item in fields["accessList"]
            ]
        self.transactions = [self.tx]
        self.provider.get_transaction_receipt.return_value = {
            "transactionHash": signed.hash,
            "blockHash": BLOCK_HASH,
            "blockNumber": self.height,
            "transactionIndex": 0,
            "from": self.signer.address,
            "to": self.tx["to"],
            "status": 1,
            "gasUsed": 33400 if fields.get("accessList") else 21000,
            "effectiveGasPrice": fields.get("gasPrice", 4 * 10**9),
        }

    def block(self, height, full_transactions=False):
        if height == "latest":
            return self.head
        return {
            "number": height,
            "hash": BLOCK_HASH if height == self.height else ANCHOR_HASH,
            **({"transactions": self.transactions} if full_transactions else {}),
        }

    def observe(self, **kwargs):
        return collect_nonce_evidence(self.provider, self.original.raw_transaction, **kwargs)

    def test_each_supported_signature_is_bound_to_its_canonical_candidate_hash(self):
        entries = [{"address": self.recipient, "storageKeys": ["0x" + "00" * 32] * 2}] * 2
        for fields in (
            {"gasPrice": 4 * 10**9},
            {"type": 1, "gasPrice": 4 * 10**9, "accessList": entries},
            {"type": 2, "maxFeePerGas": 5 * 10**9, "maxPriorityFeePerGas": 3 * 10**9, "accessList": entries},
        ):
            with self.subTest(fields=fields):
                signed = self.signed(**fields)
                self.set_candidate(signed)
                result = self.observe()
                self.assertEqual(result["result"], "candidate", result)
                self.assertEqual(result["candidate"]["tx_hash"], signed.hash.to_0x_hex())
                self.assertEqual(result["candidate"]["intent_kind"], "fee_bump")
                self.assertEqual(result["candidate"]["block"], {"height": self.height, "hash": BLOCK_HASH})
                self.assertTrue(result["evidence"]["complete"])
                self.assertLessEqual(len(result["evidence"]["nonce_probes"]), MAX_PROBES)

    def test_self_call_other_intent_and_revert_remain_separate_from_original_inclusion(self):
        for signed, kind in (
            (self.original, "original"),
            (self.signed(gasPrice=4 * 10**9, to=self.signer.address, value=0), "zero_value_self_call"),
            (self.signed(gasPrice=4 * 10**9, value=2 * 10**18), "other"),
        ):
            with self.subTest(kind=kind):
                self.set_candidate(signed)
                self.provider.get_transaction_receipt.return_value["status"] = 0
                result = self.observe()
                self.assertEqual(result["result"], "candidate", result)
                self.assertEqual(result["candidate"]["intent_kind"], kind)
                self.assertFalse(result["candidate"]["succeeded"])

    def test_no_mined_nonce_increase_does_not_search_blocks_or_infer_a_replacement(self):
        self.provider.w3.eth.get_transaction_count.return_value = 3
        self.provider.w3.eth.get_transaction_count.side_effect = None
        result = self.observe()
        self.assertEqual(result["result"], "unconsumed")
        self.provider.get_transaction_receipt.assert_not_called()
        self.provider.w3.eth.get_transaction_count.assert_called_once_with(self.signer.address, self.head["number"])

    def test_an_increased_nonce_without_a_matching_sender_transaction_stays_unknown(self):
        for transactions in ([], [{**self.tx, "from": self.recipient}], [self.tx, self.tx]):
            with self.subTest(transactions=transactions):
                self.transactions = transactions
                result = self.observe()
                self.assertEqual(result["result"], "unknown")
                self.assertEqual(result["reason"], "consumed_nonce_not_attributed_to_a_sender_transaction")
                self.assertNotIn("candidate", result)

    def test_a_canonical_admission_anchor_bounds_the_search_and_a_replaced_anchor_is_not_reused(self):
        anchor = {"chain_id": 84532, "nonce": 3, "block_number": self.height - 10, "block_hash": ANCHOR_HASH}
        result = self.observe(admission=anchor)
        self.assertEqual(result["result"], "candidate", result)
        self.assertGreaterEqual(min(x["height"] for x in result["evidence"]["nonce_probes"]), anchor["block_number"])
        result = self.observe(admission={**anchor, "block_hash": "0x" + "01" * 32})
        self.assertEqual(result["result"], "candidate", result)
        self.assertTrue(result["evidence"]["admission_orphaned"])
        self.assertIn({"height": 0, "nonce": 0}, result["evidence"]["nonce_probes"])

    def test_altered_signed_fields_signatures_or_receipts_cannot_attribute_a_spend(self):
        original = deepcopy(self.tx)
        for changes in (
            {"value": 9},
            {"input": b"forged"},
            {"r": b"\x01" * 32},
            {"gasPrice": 9},
            {"hash": "0x" + "01" * 32},
            {"blockHash": "0x" + "01" * 32},
            {"transactionIndex": True},
            {"chainId": 1},
        ):
            with self.subTest(changes=changes):
                self.tx.clear()
                self.tx.update({**original, **changes})
                self.assertEqual(self.observe()["result"], "unknown")
        self.tx.clear()
        self.tx.update(original)
        receipt = dict(self.provider.get_transaction_receipt.return_value)
        for changes in (
            {"transactionHash": "0x" + "01" * 32},
            {"status": True},
            {"from": self.recipient},
            {"transactionIndex": 1},
            {"blockNumber": self.height + 1},
            {"gasUsed": 100000},
            {"effectiveGasPrice": 8 * 10**9},
        ):
            with self.subTest(changes=changes):
                self.provider.get_transaction_receipt.return_value = {**receipt, **changes}
                self.assertEqual(self.observe()["result"], "unknown")

    def test_unavailable_historical_state_or_a_changed_network_head_preserves_unknown(self):
        self.provider.w3.eth.get_transaction_count.side_effect = TimeoutError("Synthetic pruned-state outage")
        self.assertEqual(self.observe()["result"], "unknown")
        self.provider.w3.eth.get_transaction_count.side_effect = lambda address, height: (
            3 if height < self.height else 4
        )
        reads = []

        def moving_head(height, full_transactions=False):
            if height == "latest":
                reads.append(height)
                return self.head if len(reads) == 1 else {**self.head, "hash": "0x" + "02" * 32}
            return self.block(height, full_transactions)

        self.provider.w3.eth.get_block.side_effect = moving_head
        result = self.observe()
        self.assertEqual((result["result"], result["reason"]), ("unknown", "head_changed"))
        self.assertFalse(result["evidence"]["complete"])
        self.provider.w3.eth.get_block.side_effect = self.block
        self.provider.assert_expected_chain.side_effect = [84532, 1]
        result = self.observe()
        self.assertEqual((result["result"], result["reason"]), ("unknown", "network_changed"))

    def test_correlated_rpc_hash_labels_cannot_replace_the_hash_of_the_signed_bytes(self):
        forged = "0x" + "99" * 32
        self.tx["hash"] = forged
        self.provider.get_transaction_receipt.return_value["transactionHash"] = forged
        self.assertEqual(self.observe()["result"], "unknown")

    def test_correlated_rpc_sender_labels_cannot_replace_the_recovered_signer(self):
        other = Account.create().sign_transaction(
            {
                "chainId": 84532,
                "nonce": 3,
                "to": self.recipient,
                "value": 10**18,
                "gas": 90000,
                "gasPrice": 4 * 10**9,
            }
        )
        self.set_candidate(other)
        self.assertEqual(self.tx["from"], self.signer.address)
        self.assertEqual(self.provider.get_transaction_receipt.return_value["from"], self.signer.address)
        self.assertEqual(self.observe()["result"], "unknown")

    def test_the_largest_supported_height_keeps_a_bounded_search_and_compact_payload_evidence(self):
        self.head["number"] = 2**63 - 1
        result = self.observe()
        self.assertEqual(result["result"], "candidate", result)
        self.assertLessEqual(len(result["evidence"]["nonce_probes"]), MAX_PROBES)
        self.assertNotIn("input", result["candidate"])
        self.assertEqual(result["candidate"]["input_size"], 0)
        self.assertEqual(result["candidate"]["input_hash"], Web3.keccak(b"").to_0x_hex())
        self.assertEqual(result["candidate"]["fee_cap"], "4000000000")
