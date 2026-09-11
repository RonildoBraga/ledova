from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase
from rest_framework.test import APITransactionTestCase

from integrations.blockchain.bitcoin import BitcoinClient
from shared.db import acting_for, use_operator
from shared.tests.scoped import RunsOnTheScopedConnection
from wallets.models import Transaction
from wallets.services import transaction_confirmation
from wallets.tasks.confirmation import (
    _extract_actual_fee,
    confirm_pending_transaction,
    get_receipt_reader,
)
from wallets.tests.test_submission_durability import SubmissionFixture

BLOCK_HASH = "0x" + "ab" * 32
OTHER_BLOCK_HASH = "0x" + "cd" * 32
BLOCK_SECONDS = 1700000000
BLOCK_TIME = datetime.fromtimestamp(BLOCK_SECONDS, tz=timezone.utc)


class ReceiptMetadataChecks(SubmissionFixture):
    def setUp(self):
        super().setUp()
        self.sequence = 1200

    def pending(self, *, imported=False, **metadata):
        self.sequence += 1
        with acting_for(self.tenant.user.pk):
            result = transaction_confirmation.create_pending_transaction(
                self.wallet, "0x" + f"{self.sequence:064x}", self.recipient, Decimal("0.1")
            )
            tx = Transaction.objects.get(pk=result["transaction_id"])
        with use_operator():
            Transaction.objects.filter(pk=tx.pk).update(imported_from_history=imported, **metadata)
            tx.refresh_from_db()
        return tx

    def observe(self, tx, *, succeeded=True, header=None, fields=None):
        provider = Mock(spec=["get_transaction_receipt", "w3"])
        provider.get_transaction_receipt.return_value = {
            "transactionHash": tx.tx_hash,
            "status": int(succeeded),
            "blockNumber": 17,
            "blockHash": BLOCK_HASH,
            "gasUsed": 21000,
            "effectiveGasPrice": 2000000000,
            **(fields or {}),
        }
        provider.w3.eth.get_block.return_value = header
        with patch("wallets.tasks.confirmation.get_blockchain_client", return_value=provider):
            result = confirm_pending_transaction(tx.tx_hash, str(self.wallet.pk), principal_id=self.tenant.user.pk)
        with use_operator():
            tx.refresh_from_db()
        self.assertEqual(result["status"], "confirmed" if succeeded else "failed")
        return provider

    def test_success_and_revert_retain_the_same_observed_block_and_actual_fee(self):
        for imported in (False, True):
            for succeeded in (True, False):
                with self.subTest(imported=imported, succeeded=succeeded):
                    tx = self.pending(imported=imported)
                    holdings = self.financial_state()[1:]
                    provider = self.observe(
                        tx,
                        succeeded=succeeded,
                        header={"hash": BLOCK_HASH, "number": 17, "timestamp": BLOCK_SECONDS},
                    )
                    self.assertEqual(
                        (tx.block_hash, tx.block_number, tx.block_timestamp, tx.transaction_fee),
                        (BLOCK_HASH, 17, BLOCK_TIME, Decimal("0.000042")),
                    )
                    provider.w3.eth.get_block.assert_called_once_with(BLOCK_HASH)
                    if imported:
                        self.assertEqual(self.financial_state()[1:], holdings)

    def test_missing_or_conflicting_headers_leave_the_time_unknown(self):
        for header in (
            None,
            {"hash": OTHER_BLOCK_HASH, "number": 17, "timestamp": BLOCK_SECONDS},
            {"hash": BLOCK_HASH, "number": 18, "timestamp": BLOCK_SECONDS},
        ):
            with self.subTest(header=header):
                tx = self.pending()
                snapshots = self.financial_state()[2]
                self.observe(tx, header=header)
                self.assertIsNone(tx.block_timestamp)
                self.assertEqual((tx.block_number, tx.block_hash), (17, BLOCK_HASH))
                self.assertEqual(self.financial_state()[2], snapshots)

    def test_missing_metadata_preserves_existing_evidence(self):
        for imported in (False, True):
            for succeeded in (True, False):
                with self.subTest(imported=imported, succeeded=succeeded):
                    tx = self.pending(
                        imported=imported,
                        block_hash=BLOCK_HASH,
                        block_number=17,
                        block_timestamp=BLOCK_TIME,
                        transaction_fee=Decimal("0.000042"),
                    )
                    self.observe(
                        tx,
                        succeeded=succeeded,
                        fields={"blockHash": None, "blockNumber": None, "gasUsed": None},
                    )
                    self.assertEqual(
                        (tx.block_hash, tx.block_number, tx.block_timestamp, tx.transaction_fee),
                        (BLOCK_HASH, 17, BLOCK_TIME, Decimal("0.000042")),
                    )

    def test_a_new_block_context_cannot_inherit_a_previous_blocks_time_or_fee(self):
        for imported in (False, True):
            for succeeded in (True, False):
                with self.subTest(imported=imported, succeeded=succeeded):
                    tx = self.pending(
                        imported=imported,
                        block_hash=OTHER_BLOCK_HASH,
                        block_number=16,
                        block_timestamp=BLOCK_TIME,
                        transaction_fee=Decimal("0.00003"),
                    )
                    self.observe(tx, succeeded=succeeded, fields={"gasUsed": None})
                    self.assertEqual((tx.block_hash, tx.block_number), (BLOCK_HASH, 17))
                    self.assertIsNone(tx.block_timestamp)
                    self.assertIsNone(tx.transaction_fee)

    def test_a_first_block_hash_cannot_validate_earlier_height_only_metadata(self):
        for imported in (False, True):
            for succeeded in (True, False):
                with self.subTest(imported=imported, succeeded=succeeded):
                    tx = self.pending(
                        imported=imported,
                        block_number=17,
                        block_timestamp=BLOCK_TIME,
                        transaction_fee=Decimal("0.00003"),
                    )
                    self.observe(tx, succeeded=succeeded, fields={"gasUsed": None})
                    self.assertEqual((tx.block_hash, tx.block_number), (BLOCK_HASH, 17))
                    self.assertIsNone(tx.block_timestamp)
                    self.assertIsNone(tx.transaction_fee)

    def test_malformed_metadata_does_not_block_an_identified_receipts_outcome(self):
        for succeeded in (True, False):
            with self.subTest(succeeded=succeeded):
                tx = self.pending()
                provider = self.observe(
                    tx,
                    succeeded=succeeded,
                    fields={"blockHash": "bad", "blockNumber": True, "gasUsed": -1},
                )
                self.assertEqual((tx.block_hash, tx.block_number, tx.block_timestamp, tx.transaction_fee), (None,) * 4)
                provider.w3.eth.get_block.assert_not_called()


class ReceiptMetadataTest(ReceiptMetadataChecks, APITransactionTestCase):
    pass


class ScopedReceiptMetadataTest(RunsOnTheScopedConnection, ReceiptMetadataChecks, APITransactionTestCase):
    pass


class ReceiptMetadataReaderTest(SimpleTestCase):
    def test_evm_heights_and_fees_reject_invalid_quantities_without_losing_zero(self):
        reader = get_receipt_reader("base")
        for value in (True, -1, 1.5, "-1", "NaN", "Infinity", [], {}, 2**256):
            with self.subTest(value=value):
                self.assertIsNone(reader.block_number({"blockNumber": value}))
                self.assertIsNone(_extract_actual_fee({"gasUsed": value, "effectiveGasPrice": 1}, "base"))
                self.assertIsNone(_extract_actual_fee({"gasUsed": 1, "effectiveGasPrice": value}, "base"))
        self.assertIsNone(reader.block_number({"blockNumber": 2**63}))
        self.assertIsNone(_extract_actual_fee({"gasUsed": 2**255, "effectiveGasPrice": 1}, "base"))
        self.assertEqual(reader.block_number({"blockNumber": 0}), 0)
        self.assertEqual(reader.block_number({"blockNumber": "0x11"}), 17)
        self.assertEqual(_extract_actual_fee({"gasUsed": 0, "effectiveGasPrice": 0}, "base"), Decimal("0"))
        self.assertEqual(
            _extract_actual_fee({"gas_used": "0x5208", "effective_gas_price": "2000000000"}, "base"),
            Decimal("0.000042"),
        )
        self.assertEqual(
            _extract_actual_fee({"gasUsed": 1, "effectiveGasPrice": 10**30 - 1}, "base"),
            Decimal("999999999999.999999999999999999"),
        )

    def test_only_matching_evm_header_context_can_supply_a_valid_timestamp(self):
        reader = get_receipt_reader("base")
        receipt = {"blockHash": BLOCK_HASH, "blockNumber": 0}
        client = SimpleNamespace(w3=SimpleNamespace(eth=Mock()))
        for value in (True, -1, 1.5, None, [], 2**256):
            with self.subTest(value=value):
                client.w3.eth.get_block.return_value = {"hash": BLOCK_HASH, "number": 0, "timestamp": value}
                self.assertIsNone(reader.block_timestamp(client, receipt, 0))
        client.w3.eth.get_block.return_value = {"hash": bytes.fromhex(BLOCK_HASH[2:]), "number": 0, "timestamp": 0}
        self.assertEqual(reader.block_timestamp(client, receipt, 0), datetime(1970, 1, 1, tzinfo=timezone.utc))
        client.w3.eth.get_block.assert_called_with(BLOCK_HASH)

    def test_bitcoin_headers_must_return_the_requested_identity_and_integer_time(self):
        client = object.__new__(BitcoinClient)
        client._rpc_call = Mock()
        block_hash = BLOCK_HASH[2:]
        for header in (
            None,
            {"hash": OTHER_BLOCK_HASH[2:], "time": BLOCK_SECONDS},
            {"time": BLOCK_SECONDS},
            {"hash": block_hash, "time": True},
            {"hash": block_hash, "time": -1},
            {"hash": block_hash, "time": 1.5},
            {"hash": block_hash, "time": "1700000000"},
        ):
            with self.subTest(header=header):
                client._rpc_call.return_value = header
                self.assertIsNone(client.get_block_timestamp(block_hash))
        client._rpc_call.return_value = {"hash": block_hash, "time": BLOCK_SECONDS}
        self.assertEqual(client.get_block_timestamp(block_hash), BLOCK_SECONDS)
        client._rpc_call.assert_called_with("getblockheader", [block_hash])

    def test_bitcoin_receipt_metadata_requires_integral_recordable_values(self):
        reader = get_receipt_reader("bitcoin")
        client = Mock(spec=["get_block_timestamp"])
        for value in (True, -1, 1.5, "2", [], 2**256):
            with self.subTest(value=value):
                self.assertIsNone(reader.block_number({"block_height": value}))
                self.assertIsNone(_extract_actual_fee({"fee": value}, "bitcoin"))
                client.get_block_timestamp.return_value = value
                self.assertIsNone(reader.block_timestamp(client, {"block_hash": BLOCK_HASH[2:]}, 17))
        client.get_block_timestamp.return_value = 0
        self.assertEqual(reader.block_number({"block_height": 0}), 0)
        self.assertEqual(_extract_actual_fee({"fee": 1000}, "bitcoin"), Decimal("0.00001"))
        self.assertEqual(
            reader.block_timestamp(client, {"block_hash": BLOCK_HASH[2:]}, 0), datetime(1970, 1, 1, tzinfo=timezone.utc)
        )
