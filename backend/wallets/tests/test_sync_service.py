"""WalletSyncService.sync_wallet talks to the chain client directly; the chain key it stamps is load-bearing."""

from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils import timezone

from users.models import UserAccount
from wallets.constants import (
    SNAPSHOT_REASON_CHOICES,
    SNAPSHOT_REASON_DAILY,
    SNAPSHOT_REASON_TRANSACTION,
)
from wallets.models import HoldingSnapshot, Transaction, Wallet
from wallets.services import WalletSyncService


class WalletSyncServiceTest(TestCase):
    def setUp(self):
        account = UserAccount.objects.create(account_number="SYNC-ACC")
        self.wallet = Wallet.objects.create(
            user_account=account,
            address="0x" + "c" * 40,
            chain="ethereum",
            verification_status="VERIFIED",
        )

    def test_unverified_wallet_is_skipped_without_touching_the_chain(self):
        self.wallet.verification_status = "PENDING"
        self.wallet.save(update_fields=["verification_status"])
        with patch("wallets.services.sync.get_blockchain_client") as get_client:
            self.assertEqual(WalletSyncService.sync_wallet(self.wallet)["status"], "skipped")
        get_client.assert_not_called()

    def test_sync_stamps_the_wallet_chain_on_every_fetched_transaction(self):
        client = MagicMock()
        client.get_transaction_history.return_value = [
            {
                "tx_hash": "0xabc",
                "from_address": "0x" + "d" * 40,
                "to_address": self.wallet.address,
                "amount": "1.5",
                "asset_symbol": "ETH",
                "block_timestamp": timezone.now(),
            }
        ]
        with patch("wallets.services.sync.get_blockchain_client", return_value=client) as get_client:
            result = WalletSyncService.sync_wallet(self.wallet)

        get_client.assert_called_once_with("ethereum")
        client.get_transaction_history.assert_called_once_with(self.wallet.address)
        self.assertEqual(result, {"status": "success", "transactions": 1, "snapshots": 0, "holdings": 0})
        transaction = Transaction.objects.get(wallet=self.wallet, tx_hash="0xabc")
        self.assertEqual(transaction.chain, "ethereum")
        self.wallet.refresh_from_db()
        self.assertIsNotNone(self.wallet.last_synced_at)

    def test_chain_client_failure_is_reported_not_raised(self):
        with patch("wallets.services.sync.get_blockchain_client", side_effect=RuntimeError("boom")):
            result = WalletSyncService.sync_wallet(self.wallet)

        self.assertEqual(result, {"status": "error", "error": "RuntimeError: boom"})
        self.assertFalse(Transaction.objects.filter(wallet=self.wallet).exists())

    def test_holding_snapshot_reasons_are_the_two_the_code_writes(self):
        self.assertEqual(
            [value for value, _ in SNAPSHOT_REASON_CHOICES], [SNAPSHOT_REASON_TRANSACTION, SNAPSHOT_REASON_DAILY]
        )
        self.assertEqual(HoldingSnapshot._meta.get_field("snapshot_reason").choices, SNAPSHOT_REASON_CHOICES)
