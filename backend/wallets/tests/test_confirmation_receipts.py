from datetime import datetime
from datetime import timezone as datetime_timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import TestCase

from assets.services.identity import native_asset_for_chain
from shared.tests.tenants import make_tenant
from wallets.constants import TRANSACTION_STATUS_CONFIRMED
from wallets.models import Holding, HoldingSnapshot, Transaction
from wallets.services import transaction_confirmation
from wallets.tasks.confirmation import confirm_pending_transaction, get_receipt_reader

BITCOIN_HASH = "80" * 32
BITCOIN_BLOCK_HASH = "81" * 32

BITCOIN_RECEIPT = {
    "tx_hash": BITCOIN_HASH,
    "confirmed": True,
    "confirmations": 3,
    "block_height": 812345,
    "block_hash": BITCOIN_BLOCK_HASH,
}


class BitcoinReceiptReaderTest(TestCase):
    def test_bitcoin_reader_takes_the_block_height(self):
        reader = get_receipt_reader("bitcoin")
        self.assertEqual(reader.block_number(BITCOIN_RECEIPT), 812345)

    def test_bitcoin_reader_needs_a_confirmation_rather_than_a_status_default(self):
        reader = get_receipt_reader("bitcoin")
        self.assertTrue(reader.succeeded(BITCOIN_RECEIPT))
        self.assertIsNone(reader.succeeded({"confirmed": False, "confirmations": 0}))
        self.assertIsNone(reader.succeeded({}))

    def test_bitcoin_reader_reads_the_timestamp_from_the_block_hash(self):
        reader = get_receipt_reader("bitcoin")
        client = Mock(spec=["get_block_timestamp"])
        client.get_block_timestamp.return_value = 1700000000

        stamp = reader.block_timestamp(client, BITCOIN_RECEIPT, 812345)

        client.get_block_timestamp.assert_called_once_with(BITCOIN_BLOCK_HASH)
        self.assertEqual(stamp, datetime.fromtimestamp(1700000000, tz=datetime_timezone.utc))

    def test_bitcoin_reader_tolerates_a_missing_block_hash(self):
        reader = get_receipt_reader("bitcoin")
        client = Mock(spec=["get_block_timestamp"])
        self.assertIsNone(reader.block_timestamp(client, {"block_height": 1}, 1))
        client.get_block_timestamp.assert_not_called()

    def test_evm_reader_still_reads_the_evm_keys(self):
        reader = get_receipt_reader("base")
        self.assertEqual(reader.block_number({"blockNumber": 12}), 12)
        self.assertEqual(reader.block_number({"block_number": 13}), 13)
        self.assertTrue(reader.succeeded({"status": 1}))
        self.assertFalse(reader.succeeded({"status": 0}))

    def test_evm_reader_reads_the_timestamp_from_web3(self):
        reader = get_receipt_reader("ethereum")
        block_hash = "0x" + "82" * 32
        header = {"hash": block_hash, "number": 42, "timestamp": 1600000000}
        client = SimpleNamespace(w3=SimpleNamespace(eth=Mock(get_block=Mock(return_value=header))))

        stamp = reader.block_timestamp(client, {"blockNumber": 42, "blockHash": block_hash}, 42)

        self.assertEqual(stamp, datetime.fromtimestamp(1600000000, tz=datetime_timezone.utc))


class BitcoinConfirmationTaskTest(TestCase):
    def setUp(self):
        self.notification = patch(
            "wallets.services.transaction_confirmation.send_transaction_notification.defer"
        ).start()
        self.balance = patch("wallets.services.holdings.fetch_chain_balance", return_value=None).start()
        self.addCleanup(patch.stopall)
        self.tenant = make_tenant("btcreceipt")
        self.wallet = self.tenant.spare_wallet
        self.wallet.chain = "bitcoin"
        self.wallet.save(update_fields=["chain"])
        native = native_asset_for_chain("bitcoin")
        self.holding = Holding.objects.create(wallet=self.wallet, asset=native, quantity=Decimal("2"))
        transaction_confirmation.create_pending_transaction(
            wallet=self.wallet,
            tx_hash=BITCOIN_HASH,
            to_address="tb1qexample",
            amount=Decimal("1"),
            transaction_fee=Decimal("0.0001"),
        )
        self.tx = Transaction.objects.get(tx_hash=BITCOIN_HASH, wallet=self.wallet)

    def stored_accounting(self):
        return (
            Transaction.objects.filter(pk=self.tx.pk).values().get(),
            Holding.objects.filter(pk=self.holding.pk).values().get(),
            list(HoldingSnapshot.objects.filter(holding=self.holding).values()),
        )

    def test_a_bitcoin_receipt_records_the_block_and_its_timestamp(self):
        client = Mock(spec=["get_transaction_receipt", "get_block_timestamp"])
        client.get_transaction_receipt.return_value = BITCOIN_RECEIPT
        client.get_block_timestamp.return_value = 1700000000

        with patch("wallets.tasks.confirmation.get_blockchain_client", return_value=client):
            result = confirm_pending_transaction(
                tx_hash=BITCOIN_HASH, wallet_uuid=str(self.wallet.uuid), principal_id=None
            )

        self.assertEqual(result["status"], "confirmed")
        self.tx.refresh_from_db()
        self.assertEqual(self.tx.status, TRANSACTION_STATUS_CONFIRMED)
        self.assertEqual(self.tx.block_number, 812345)
        self.assertEqual(self.tx.block_hash, BITCOIN_BLOCK_HASH)
        self.assertEqual(self.tx.block_timestamp, datetime.fromtimestamp(1700000000, tz=datetime_timezone.utc))
        self.holding.refresh_from_db()
        self.assertEqual(self.holding.quantity, Decimal("0.9999"))
        self.assertEqual(self.tx.deducted_amount, Decimal("1.0001"))
        self.notification.assert_called_once()

    def test_an_unconfirmed_bitcoin_receipt_is_not_treated_as_success(self):
        client = Mock(spec=["get_transaction_receipt", "get_block_timestamp"])
        client.get_transaction_receipt.return_value = {"confirmed": False, "confirmations": 0, "tx_hash": BITCOIN_HASH}
        before = self.stored_accounting()

        with patch("wallets.tasks.confirmation.get_blockchain_client", return_value=client):
            with self.assertRaisesRegex(RuntimeError, "receipt outcome not yet available"):
                confirm_pending_transaction(tx_hash=BITCOIN_HASH, wallet_uuid=str(self.wallet.uuid), principal_id=None)

        self.assertEqual(self.stored_accounting(), before)
        client.get_block_timestamp.assert_not_called()
        self.balance.assert_not_called()
        self.notification.assert_not_called()

    def test_a_conflicting_bitcoin_receipt_cannot_confirm_until_the_matching_txid_arrives(self):
        client = Mock(spec=["get_transaction_receipt", "get_block_timestamp"])
        client.get_transaction_receipt.side_effect = [{**BITCOIN_RECEIPT, "tx_hash": "81" * 32}, BITCOIN_RECEIPT]
        client.get_block_timestamp.return_value = 1700000000
        before = self.stored_accounting()
        with patch("wallets.tasks.confirmation.get_blockchain_client", return_value=client):
            with self.assertRaisesRegex(RuntimeError, "receipt identity not yet available"):
                confirm_pending_transaction(BITCOIN_HASH, str(self.wallet.pk), principal_id=None)
            self.assertEqual(self.stored_accounting(), before)
            client.get_block_timestamp.assert_not_called()
            self.notification.assert_not_called()
            self.balance.assert_not_called()
            self.assertEqual(
                confirm_pending_transaction(BITCOIN_HASH, str(self.wallet.pk), principal_id=None)["status"], "confirmed"
            )
        self.notification.assert_called_once()

    def test_unsupported_bitcoin_confirmation_values_retain_the_debit_until_a_valid_receipt(self):
        unsupported = (
            {},
            {"confirmed": None, "confirmations": 3},
            {"confirmed": "true", "confirmations": 3},
            {"confirmed": 1, "confirmations": 3},
            {"confirmed": True},
            {"confirmed": True, "confirmations": None},
            {"confirmed": True, "confirmations": -1},
            {"confirmed": True, "confirmations": True},
            {"confirmed": True, "confirmations": 1.0},
            {"confirmed": True, "confirmations": "3"},
            {"confirmed": True, "confirmations": []},
            {"confirmed": True, "confirmations": {}},
        )
        before = self.stored_accounting()
        client = Mock(spec=["get_transaction_receipt", "get_block_timestamp"])
        client.get_block_timestamp.return_value = 1700000000
        with patch("wallets.tasks.confirmation.get_blockchain_client", return_value=client):
            for fields in unsupported:
                with self.subTest(fields=fields):
                    client.get_transaction_receipt.return_value = {
                        "block_hash": "0000block",
                        "tx_hash": BITCOIN_HASH,
                        **fields,
                    }
                    with self.assertRaisesRegex(RuntimeError, "receipt outcome not yet available"):
                        confirm_pending_transaction(
                            tx_hash=BITCOIN_HASH, wallet_uuid=str(self.wallet.uuid), principal_id=None
                        )
                    self.assertEqual(self.stored_accounting(), before)
                    client.get_block_timestamp.assert_not_called()
                    self.balance.assert_not_called()
                    self.notification.assert_not_called()
            client.get_transaction_receipt.return_value = BITCOIN_RECEIPT
            client.get_block_timestamp.return_value = 1700000000
            result = confirm_pending_transaction(
                tx_hash=BITCOIN_HASH, wallet_uuid=str(self.wallet.uuid), principal_id=None
            )

        self.assertEqual(result["status"], "confirmed")
        self.tx.refresh_from_db()
        self.assertEqual(self.tx.status, TRANSACTION_STATUS_CONFIRMED)
        self.assertEqual(self.tx.deducted_amount, Decimal("1.0001"))
        self.holding.refresh_from_db()
        self.assertEqual(self.holding.quantity, Decimal("0.9999"))
        self.notification.assert_called_once()
