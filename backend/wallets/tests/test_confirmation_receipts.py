from datetime import datetime
from datetime import timezone as datetime_timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import TestCase

from shared.tests.tenants import make_tenant
from wallets.constants import TRANSACTION_STATUS_CONFIRMED
from wallets.models import Transaction
from wallets.tasks.confirmation import confirm_pending_transaction, get_receipt_reader

BITCOIN_RECEIPT = {
    "tx_hash": "btc-hash",
    "confirmed": True,
    "confirmations": 3,
    "block_height": 812345,
    "block_hash": "0000block",
}


class BitcoinReceiptReaderTest(TestCase):
    def test_bitcoin_reader_takes_the_block_height(self):
        reader = get_receipt_reader("bitcoin")
        self.assertEqual(reader.block_number(BITCOIN_RECEIPT), 812345)

    def test_bitcoin_reader_needs_a_confirmation_rather_than_a_status_default(self):
        reader = get_receipt_reader("bitcoin")
        self.assertTrue(reader.succeeded(BITCOIN_RECEIPT))
        self.assertFalse(reader.succeeded({"confirmed": False, "confirmations": 0}))
        self.assertFalse(reader.succeeded({}))

    def test_bitcoin_reader_reads_the_timestamp_from_the_block_hash(self):
        reader = get_receipt_reader("bitcoin")
        client = Mock(spec=["get_block_timestamp"])
        client.get_block_timestamp.return_value = 1700000000

        stamp = reader.block_timestamp(client, BITCOIN_RECEIPT, 812345)

        client.get_block_timestamp.assert_called_once_with("0000block")
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
        client = SimpleNamespace(w3=SimpleNamespace(eth=Mock(get_block=Mock(return_value={"timestamp": 1600000000}))))

        stamp = reader.block_timestamp(client, {"blockNumber": 42}, 42)

        self.assertEqual(stamp, datetime.fromtimestamp(1600000000, tz=datetime_timezone.utc))


class BitcoinConfirmationTaskTest(TestCase):
    def setUp(self):
        patch("wallets.services.transaction_confirmation.send_transaction_notification").start()
        self.addCleanup(patch.stopall)
        self.tenant = make_tenant("btcreceipt")
        self.wallet = self.tenant.spare_wallet
        self.wallet.chain = "bitcoin"
        self.wallet.save(update_fields=["chain"])
        self.tx = Transaction.objects.create(
            tx_hash="btc-hash",
            chain="bitcoin",
            from_address=self.wallet.address,
            to_address="tb1qexample",
            asset=self.tenant.refs.asset,
            amount=Decimal("1"),
            wallet=self.wallet,
        )

    def test_a_bitcoin_receipt_records_the_block_and_its_timestamp(self):
        client = Mock(spec=["get_transaction_receipt", "get_block_timestamp"])
        client.get_transaction_receipt.return_value = BITCOIN_RECEIPT
        client.get_block_timestamp.return_value = 1700000000

        with patch("wallets.tasks.confirmation.get_blockchain_client", return_value=client):
            result = confirm_pending_transaction(tx_hash="btc-hash", wallet_uuid=str(self.wallet.uuid))

        self.assertEqual(result["status"], "confirmed")
        self.tx.refresh_from_db()
        self.assertEqual(self.tx.status, TRANSACTION_STATUS_CONFIRMED)
        self.assertEqual(self.tx.block_number, 812345)
        self.assertEqual(self.tx.block_timestamp, datetime.fromtimestamp(1700000000, tz=datetime_timezone.utc))

    def test_an_unconfirmed_bitcoin_receipt_is_not_treated_as_success(self):
        client = Mock(spec=["get_transaction_receipt", "get_block_timestamp"])
        client.get_transaction_receipt.return_value = {"confirmed": False, "confirmations": 0}

        with patch("wallets.tasks.confirmation.get_blockchain_client", return_value=client):
            result = confirm_pending_transaction(tx_hash="btc-hash", wallet_uuid=str(self.wallet.uuid))

        self.assertEqual(result["status"], "failed")
        self.tx.refresh_from_db()
        self.assertNotEqual(self.tx.status, TRANSACTION_STATUS_CONFIRMED)
