from datetime import timedelta
from decimal import Decimal
from uuid import UUID

from django.test import TestCase
from hexbytes import HexBytes

from blockchain.models import BlockchainTransaction, TransactionStatus
from blockchain.tests.monitor_fixtures import (
    BLOCK_HASH,
    OTHER_HASH,
    RECEIPT,
    TX_HASH,
    stored,
    sweep,
    transaction,
)

RETAINED = {"checked": 1, "confirmed": 0, "failed": 0}


class MonitorObservationTest(TestCase):
    def setUp(self):
        self.tx = transaction()

    def terminal_during_receipt(self, receipt_status, terminal):
        saved = []

        def observe(requested):
            self.assertEqual(requested, TX_HASH)
            current = BlockchainTransaction.objects.get(pk=self.tx.pk)
            if terminal == TransactionStatus.CONFIRMED:
                current.mark_confirmed(99, OTHER_HASH, 12345)
            elif terminal == TransactionStatus.REVERTED:
                current.mark_reverted("Previously observed revert")
            else:
                current.mark_failed("Another writer recorded failure")
            saved.append(stored(current))
            return {**RECEIPT, "status": receipt_status}

        result = sweep(observe)

        self.assertEqual(stored(self.tx), saved[0])
        self.assertEqual(result, RETAINED)

    def test_stale_success_cannot_overwrite_a_committed_revert(self):
        self.terminal_during_receipt(1, TransactionStatus.REVERTED)

    def test_stale_revert_cannot_overwrite_a_committed_success(self):
        self.terminal_during_receipt(0, TransactionStatus.CONFIRMED)

    def test_stale_observations_do_not_reopen_the_failed_history(self):
        for status in (0, 1):
            with self.subTest(status=status):
                BlockchainTransaction.objects.filter(pk=self.tx.pk).update(status=TransactionStatus.SUBMITTED)
                self.terminal_during_receipt(status, TransactionStatus.FAILED)

    def test_duplicate_observations_keep_the_first_terminal_metadata_and_count_once(self):
        for status in (0, 1):
            with self.subTest(status=status):
                BlockchainTransaction.objects.filter(pk=self.tx.pk).update(status=TransactionStatus.SUBMITTED)
                saved = []
                first = []

                def observe(requested):
                    first.append(sweep({**RECEIPT, "status": status, "blockNumber": 99, "gasUsed": 12345}))
                    saved.append(stored(self.tx))
                    return {**RECEIPT, "status": status}

                duplicate = sweep(observe)

                self.assertEqual(stored(self.tx), saved[0])
                self.assertEqual(first, [{"checked": 1, "confirmed": status, "failed": 1 - status}])
                self.assertEqual(duplicate, RETAINED)

    def test_changed_submission_identity_is_retained_until_a_fresh_observation(self):
        changes = {
            "tx_hash": OTHER_HASH,
            "tx_type": "token_mint",
            "status": TransactionStatus.PENDING,
            "from_address": "0x" + "33" * 20,
            "to_address": "0x" + "44" * 20,
            "value": Decimal("2"),
            "gas_limit": 60000,
            "gas_price": Decimal("0.000000002"),
            "nonce": 8,
            "function_name": "differentCall",
            "function_args": {"amount": "2"},
            "related_model": "synthetic.OtherIntent",
            "related_uuid": UUID(int=2),
            "submitted_at": self.tx.submitted_at + timedelta(seconds=1),
        }
        original = stored(self.tx)
        for field, value in changes.items():
            for status in (0, 1):
                with self.subTest(field=field, status=status):
                    BlockchainTransaction.objects.filter(pk=self.tx.pk).update(**original)
                    saved = []

                    def observe(requested):
                        self.assertEqual(requested, TX_HASH)
                        BlockchainTransaction.objects.filter(pk=self.tx.pk).update(**{field: value})
                        saved.append(stored(self.tx))
                        return {**RECEIPT, "status": status}

                    result = sweep(observe)

                    self.assertEqual(stored(self.tx), saved[0])
                    self.assertEqual(result, RETAINED)
                    current_hash = saved[0]["tx_hash"]
                    self.assertEqual(
                        sweep({**RECEIPT, "transactionHash": current_hash, "status": status}),
                        {"checked": 1, "confirmed": status, "failed": 1 - status},
                    )

    def test_deleting_the_captured_uuid_does_not_apply_its_receipt_to_a_new_row_with_the_same_hash(self):
        replacements = []

        def observe(requested):
            BlockchainTransaction.objects.filter(pk=self.tx.pk).delete()
            replacement = transaction()
            replacements.append((replacement, stored(replacement)))
            return RECEIPT

        self.assertEqual(sweep(observe), RETAINED)
        replacement, before = replacements[0]
        self.assertNotEqual(replacement.pk, self.tx.pk)
        self.assertEqual(stored(replacement), before)
        self.assertFalse(BlockchainTransaction.objects.filter(pk=self.tx.pk).exists())
        self.assertEqual(sweep(RECEIPT), {"checked": 1, "confirmed": 1, "failed": 0})

    def test_an_error_note_change_does_not_block_an_unchanged_submission(self):
        def observe(requested):
            BlockchainTransaction.objects.get(pk=self.tx.pk).mark_outcome_unknown("Updated diagnostic")
            return RECEIPT

        self.assertEqual(sweep(observe), {"checked": 1, "confirmed": 1, "failed": 0})
        self.assertEqual(stored(self.tx)["error_message"], "Updated diagnostic")

    def test_a_boolean_call_argument_cannot_reuse_a_receipt_captured_for_a_numeric_argument(self):
        BlockchainTransaction.objects.filter(pk=self.tx.pk).update(function_args={"amount": 1})
        saved = []

        def observe(requested):
            BlockchainTransaction.objects.filter(pk=self.tx.pk).update(function_args={"amount": True})
            saved.append(stored(self.tx))
            return RECEIPT

        result = sweep(observe)
        self.assertEqual(stored(self.tx), saved[0])
        self.assertEqual(result, RETAINED)

    def test_present_conflicting_or_malformed_receipt_hashes_cannot_apply_either_outcome(self):
        original = stored(self.tx)
        for receipt_hash in (OTHER_HASH, HexBytes(OTHER_HASH), None, "", 7, True, [], {}):
            for status in (0, 1):
                with self.subTest(receipt_hash=receipt_hash, status=status):
                    BlockchainTransaction.objects.filter(pk=self.tx.pk).update(**original)
                    before = stored(self.tx)
                    result = sweep({**RECEIPT, "transactionHash": receipt_hash, "status": status})
                    self.assertEqual(stored(self.tx), before)
                    self.assertEqual(result, RETAINED)
        self.assertEqual(sweep(RECEIPT), {"checked": 1, "confirmed": 1, "failed": 0})

    def test_normal_outcomes_accept_matching_web3_hashes_and_the_missing_hash_provider_contract(self):
        original = stored(self.tx)
        for status in (0, 1):
            for row_status in (TransactionStatus.PENDING, TransactionStatus.SUBMITTED):
                for receipt_hash in (TX_HASH, TX_HASH.upper(), HexBytes(TX_HASH), None):
                    with self.subTest(status=status, row_status=row_status, receipt_hash=receipt_hash):
                        BlockchainTransaction.objects.filter(pk=self.tx.pk).update(**{**original, "status": row_status})
                        receipt = {**RECEIPT, "status": status, "transactionHash": receipt_hash}
                        if receipt_hash is None:
                            del receipt["transactionHash"]
                        self.assertEqual(sweep(receipt), {"checked": 1, "confirmed": status, "failed": 1 - status})
                        current = stored(self.tx)
                        self.assertEqual(current["status"], "confirmed" if status else "reverted")
                        if status:
                            self.assertEqual(
                                (current["block_number"], current["block_hash"], current["gas_used"]),
                                (77, BLOCK_HASH, 21000),
                            )
                            self.assertIsNotNone(current["confirmed_at"])
                        else:
                            self.assertEqual(current["error_message"], "Transaction reverted on-chain")
                        self.assertEqual(sweep(receipt), {"checked": 0, "confirmed": 0, "failed": 0})
                        self.assertEqual(stored(self.tx), current)
