from decimal import Decimal
from unittest.mock import Mock

from django.test import SimpleTestCase, override_settings

from integrations.blockchain.bitcoin import BitcoinClient
from wallets.services.bitcoin_intent import GENESIS_HASHES
from wallets.services.chain_evidence import collect_chain_evidence

TX_HASH = "0x" + "11" * 32
BLOCK_HASH = "0x" + "22" * 32
OLD_HASH = "0x" + "33" * 32
HEAD_HASH = "0x" + "44" * 32
FINALIZED_HASH = "0x" + "55" * 32
BLOCK_TIME = 1700000000


class ChainEvidenceTest(SimpleTestCase):
    def setUp(self):
        self.client = Mock(spec=["assert_expected_chain", "get_transaction_receipt", "w3"])
        self.client.assert_expected_chain.return_value = 84532
        self.client.get_transaction_receipt.return_value = {
            "transactionHash": TX_HASH,
            "blockHash": BLOCK_HASH,
            "blockNumber": 103,
            "status": 1,
            "gasUsed": 21000,
            "effectiveGasPrice": 2000000000,
        }
        self.head = {"hash": HEAD_HASH, "number": 109, "timestamp": BLOCK_TIME}
        self.finalized = {"hash": FINALIZED_HASH, "number": 102, "timestamp": BLOCK_TIME}
        self.block = {"hash": BLOCK_HASH, "number": 103, "timestamp": BLOCK_TIME}
        self.client.w3.eth.get_block.side_effect = self.get_block

    def get_block(self, identifier):
        if identifier == "latest":
            return self.head
        if identifier == "finalized":
            return self.finalized
        if identifier in (103, BLOCK_HASH):
            return self.block
        if identifier == 102:
            return {"hash": FINALIZED_HASH, "number": 102, "timestamp": BLOCK_TIME}
        raise AssertionError(f"Unexpected block {identifier}")

    def observe(self, policy=None, previous=None):
        return collect_chain_evidence(
            self.client,
            chain="base",
            network="evm:84532",
            tx_hash=TX_HASH,
            previous_block=previous,
            policy=policy or {"mode": "unconfigured"},
        )

    def test_inclusion_retains_validated_evidence_without_inventing_a_finality_policy(self):
        result = self.observe()
        self.assertEqual(
            (result["result"], result["finality"], result["reason"]), ("included", "unknown", "policy_unconfigured")
        )
        self.assertEqual(result["evidence"]["depth"], 7)
        self.assertEqual(result["evidence"]["canonical_receipt"], {"hash": BLOCK_HASH, "height": 103})
        receipt = result["evidence"]["receipt"]
        self.assertIs(receipt["succeeded"], True)
        self.assertEqual(receipt["timestamp"], "2023-11-14T22:13:20+00:00")
        self.assertEqual(Decimal(receipt["actual_fee"]), Decimal("0.000042"))

    def test_finality_requires_the_canonical_finalized_head_to_reach_the_receipt(self):
        self.assertEqual(self.observe({"mode": "finalized"})["finality"], "waiting")
        self.finalized = dict(self.block)
        self.assertEqual(self.observe({"mode": "finalized"})["finality"], "satisfied")
        for header in (None, {}, {**self.block, "hash": OLD_HASH}, {**self.block, "number": True}):
            with self.subTest(header=header):
                self.finalized = header
                result = self.observe({"mode": "finalized"})
                self.assertEqual((result["result"], result["finality"]), ("included", "unknown"))

    def test_a_changing_tip_or_network_cannot_produce_a_final_observation(self):
        count = 0

        def moved(identifier):
            nonlocal count
            if identifier == "latest":
                count += 1
                return self.head if count == 1 else {**self.head, "hash": OLD_HASH}
            return self.get_block(identifier)

        self.client.w3.eth.get_block.side_effect = moved
        result = self.observe({"mode": "depth", "depth": 1})
        self.assertEqual((result["result"], result["reason"]), ("unknown", "head_changed"))
        self.client.w3.eth.get_block.side_effect = self.get_block
        self.client.assert_expected_chain.side_effect = [84532, 11155111]
        result = self.observe({"mode": "depth", "depth": 1})
        self.assertEqual((result["result"], result["reason"]), ("unknown", "network_changed"))

    def test_finality_rpc_failures_preserve_verified_inclusion_but_still_require_a_stable_head(self):
        for unavailable in ("finalized", 102):
            with self.subTest(unavailable=unavailable):
                heads = []
                move_head = False

                def unavailable_finality(identifier):
                    if identifier == unavailable:
                        raise ConnectionError("Synthetic finality-only RPC failure")
                    if identifier == "latest":
                        heads.append(identifier)
                        if move_head and len(heads) == 2:
                            return {**self.head, "hash": OLD_HASH}
                    return self.get_block(identifier)

                self.client.w3.eth.get_block.side_effect = unavailable_finality
                result = self.observe({"mode": "finalized"})
                self.assertEqual(
                    (result["result"], result["finality"], result["reason"]),
                    ("included", "unknown", "finality_unavailable"),
                )
                self.assertTrue(result["evidence"]["finality_read_failed"])
                self.assertEqual(result["evidence"]["receipt"]["hash"], BLOCK_HASH)
                self.assertEqual(result["evidence"]["canonical_receipt"], {"hash": BLOCK_HASH, "height": 103})
                heads.clear()
                move_head = True
                result = self.observe({"mode": "finalized"})
                self.assertEqual((result["result"], result["reason"]), ("unknown", "head_changed"))

    def test_missing_receipt_is_not_orphan_proof_but_a_different_canonical_block_is(self):
        self.client.get_transaction_receipt.return_value = None
        result = self.observe(previous={"hash": BLOCK_HASH, "height": 103})
        self.assertEqual(result["result"], "unknown")
        result = self.observe(previous={"hash": OLD_HASH, "height": 103})
        self.assertEqual((result["result"], result["finality"]), ("orphaned", "unknown"))
        self.assertEqual(result["reason"], "previous_block_replaced")
        self.assertEqual(result["evidence"]["previous_block"]["hash"], OLD_HASH)
        self.assertEqual(result["evidence"]["canonical_previous"]["hash"], BLOCK_HASH)

    def test_new_inclusion_keeps_the_previous_blocks_orphan_evidence(self):
        result = self.observe(previous={"hash": OLD_HASH, "height": 103})
        self.assertEqual(result["result"], "included")
        self.assertTrue(result["evidence"]["previous_orphaned"])
        self.assertEqual(result["evidence"]["receipt"]["hash"], BLOCK_HASH)
        self.assertEqual(result["evidence"]["previous_block"]["hash"], OLD_HASH)

    def test_new_inclusion_requires_proof_that_the_previous_block_left_the_canonical_chain(self):
        previous = {"hash": FINALIZED_HASH, "height": 102}
        for canonical, reason in (
            ({"hash": FINALIZED_HASH, "number": 102}, "previous_inclusion_still_canonical"),
            (None, "previous_canonicality_unavailable"),
        ):
            with self.subTest(canonical=canonical):
                self.client.w3.eth.get_block.side_effect = lambda identifier: (
                    canonical if identifier == 102 else self.get_block(identifier)
                )
                result = self.observe({"mode": "depth", "depth": 1}, previous=previous)
                self.assertEqual(
                    (result["result"], result["finality"], result["reason"]), ("unknown", "unknown", reason)
                )
                self.assertEqual(result["evidence"]["previous_block"], previous)
                self.assertEqual(result["evidence"]["canonical_receipt"], {"hash": BLOCK_HASH, "height": 103})

    @override_settings(BITCOIN_NETWORK="regtest")
    def test_bitcoin_cannot_claim_two_canonical_inclusions_for_the_same_spend(self):
        client = object.__new__(BitcoinClient)
        client.expected_network = "regtest"
        heights = {OLD_HASH[2:]: 103, BLOCK_HASH[2:]: 104, HEAD_HASH[2:]: 109}

        def rpc(method, params=None):
            if method == "getblockchaininfo":
                return {"chain": "regtest"}
            if method == "getblockhash":
                if params == [0]:
                    return GENESIS_HASHES["regtest"]
                return OLD_HASH[2:] if params == [103] else BLOCK_HASH[2:]
            if method == "getbestblockhash":
                return HEAD_HASH[2:]
            if method == "getblockheader":
                return {"hash": params[0], "height": heights[params[0]], "time": BLOCK_TIME}
            if method == "getrawtransaction":
                return {"txid": TX_HASH[2:], "blockhash": BLOCK_HASH[2:], "confirmations": 6}
            raise AssertionError(method)

        client._rpc_call = Mock(side_effect=rpc)
        result = collect_chain_evidence(
            client,
            chain="bitcoin",
            network="bitcoin:" + GENESIS_HASHES["regtest"],
            tx_hash=TX_HASH[2:],
            previous_block={"hash": OLD_HASH[2:], "height": 103},
            policy={"mode": "depth", "depth": 6},
        )
        self.assertEqual(
            (result["result"], result["finality"], result["reason"]),
            ("unknown", "unknown", "previous_inclusion_still_canonical"),
        )

    def test_foreign_identity_unknown_outcome_and_invalid_height_remain_unknown(self):
        original = self.client.get_transaction_receipt.return_value
        for changes in (
            {"transactionHash": OLD_HASH},
            {"status": True},
            {"status": "1"},
            {"blockNumber": True},
            {"blockNumber": 2**63},
            {"blockHash": "invalid"},
        ):
            with self.subTest(changes=changes):
                self.client.get_transaction_receipt.return_value = {**original, **changes}
                self.assertEqual(self.observe()["result"], "unknown")
        self.client.get_transaction_receipt.return_value = original
        self.block["number"] = 104
        self.assertEqual(self.observe()["result"], "unknown")

    @override_settings(BITCOIN_NETWORK="regtest")
    def test_bitcoin_depth_uses_a_stable_tip_and_exact_inclusive_height_difference(self):
        client = object.__new__(BitcoinClient)
        client.expected_network = "regtest"
        head_height = 108

        def rpc(method, params=None):
            if method == "getblockchaininfo":
                return {"chain": "regtest"}
            if method == "getblockhash":
                return GENESIS_HASHES["regtest"] if params == [0] else BLOCK_HASH[2:]
            if method == "getbestblockhash":
                return HEAD_HASH[2:]
            if method == "getblockheader":
                return {
                    "hash": params[0],
                    "height": head_height if params[0] == HEAD_HASH[2:] else 104,
                    "time": BLOCK_TIME,
                }
            if method == "getrawtransaction":
                return {
                    "txid": TX_HASH[2:],
                    "blockhash": BLOCK_HASH[2:],
                    "confirmations": 999,
                    "fee": Decimal("0.0001"),
                }
            raise AssertionError(method)

        client._rpc_call = Mock(side_effect=rpc)

        def observe():
            return collect_chain_evidence(
                client,
                chain="bitcoin",
                network="bitcoin:" + GENESIS_HASHES["regtest"],
                tx_hash=TX_HASH[2:],
                previous_block=None,
                policy={"mode": "depth", "depth": 6},
            )

        result = observe()
        self.assertEqual(
            (result["result"], result["finality"], result["evidence"]["depth"]), ("included", "waiting", 5)
        )
        head_height = 109
        result = observe()
        self.assertEqual((result["finality"], result["evidence"]["depth"]), ("satisfied", 6))
