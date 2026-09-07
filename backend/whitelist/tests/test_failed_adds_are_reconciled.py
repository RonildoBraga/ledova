from datetime import timedelta
from unittest.mock import Mock

from django.test import TestCase
from django.utils import timezone

from blockchain.models import BlockchainTransaction, TransactionStatus, TransactionType
from users.models import UserAccount
from wallets.models import Wallet
from whitelist.models import WhitelistEntry, WhitelistStatus
from whitelist.services import WhitelistService
from whitelist.services.whitelist import GETH_TXPOOL_LIFETIME

HASH = "0x" + "7a" * 32
REMOVE_HASH = "0x" + "22" * 32


class AFailedAddTheChainContradictsIsReconciledTest(TestCase):

    def setUp(self):
        self.account = UserAccount.objects.create()
        self.wallet = Wallet.objects.create(user_account=self.account, address="0x" + "a" * 40, chain="base")

    def an_entry(
        self,
        *,
        tx_hash=HASH,
        age=timedelta(minutes=5),
        status=WhitelistStatus.FAILED,
        last_attempt=TransactionType.WHITELIST_ADD,
    ):
        entry = WhitelistEntry.objects.create(wallet=self.wallet, status=status, add_tx_hash=tx_hash)
        if last_attempt is not None:
            self.an_attempt(entry, last_attempt)
        WhitelistEntry.objects.filter(pk=entry.pk).update(updated_at=timezone.now() - age)
        entry.refresh_from_db()
        return entry

    @staticmethod
    def an_attempt(entry, tx_type):
        return BlockchainTransaction.objects.create(
            tx_type=tx_type,
            status=TransactionStatus.REVERTED,
            related_model="whitelist.WhitelistEntry",
            related_uuid=entry.uuid,
        )

    @staticmethod
    def service(on_chain):
        service = WhitelistService.__new__(WhitelistService)
        service.is_whitelisted = Mock(return_value=on_chain)
        return service

    def test_an_add_the_chain_says_landed_becomes_active_on_its_own_hash(self):
        entry = self.an_entry()

        result = self.service(on_chain=True).reconcile_failed_adds()

        entry.refresh_from_db()
        self.assertEqual((entry.status, entry.add_tx_hash, entry.is_whitelisted), (WhitelistStatus.ACTIVE, HASH, True))
        self.assertEqual((result["checked"], result["activated"], result["left_failed"]), (1, 1, 0))

    def test_an_add_the_chain_does_not_know_stays_failed_rather_than_removed(self):
        entry = self.an_entry()

        result = self.service(on_chain=False).reconcile_failed_adds()

        entry.refresh_from_db()
        self.assertEqual(entry.status, WhitelistStatus.FAILED)
        self.assertEqual((result["checked"], result["activated"], result["left_failed"]), (1, 0, 1))

    def test_an_add_that_was_never_sent_is_not_asked_about(self):
        entry = self.an_entry(tx_hash=None)
        service = self.service(on_chain=True)

        result = service.reconcile_failed_adds()

        entry.refresh_from_db()
        self.assertEqual(entry.status, WhitelistStatus.FAILED)
        self.assertEqual(result["checked"], 0)
        service.is_whitelisted.assert_not_called()

    def test_an_add_older_than_the_node_would_hold_it_is_left_alone(self):
        entry = self.an_entry(age=GETH_TXPOOL_LIFETIME + timedelta(minutes=1))
        service = self.service(on_chain=True)

        result = service.reconcile_failed_adds()

        entry.refresh_from_db()
        self.assertEqual(entry.status, WhitelistStatus.FAILED)
        self.assertEqual(result["checked"], 0)
        service.is_whitelisted.assert_not_called()

    def test_an_entry_that_never_failed_is_not_touched(self):
        self.an_entry(status=WhitelistStatus.PENDING)
        service = self.service(on_chain=True)

        self.assertEqual(service.reconcile_failed_adds()["checked"], 0)
        service.is_whitelisted.assert_not_called()

    def test_a_reverted_remove_stays_failed_so_the_operator_sees_it_did_not_take(self):
        entry = self.an_entry(last_attempt=TransactionType.WHITELIST_REMOVE)
        WhitelistEntry.objects.filter(pk=entry.pk).update(remove_tx_hash=REMOVE_HASH)

        result = self.service(on_chain=True).reconcile_failed_adds()

        entry.refresh_from_db()
        self.assertEqual((entry.status, entry.add_tx_hash), (WhitelistStatus.FAILED, HASH))
        self.assertEqual((entry.remove_tx_hash, entry.is_whitelisted), (REMOVE_HASH, True))
        self.assertEqual((result["activated"], result["removals_the_chain_kept"]), (0, 1))

    def test_a_failed_add_after_an_earlier_successful_removal_is_still_reconciled(self):
        entry = self.an_entry(last_attempt=None)
        self.an_attempt(entry, TransactionType.WHITELIST_REMOVE)
        self.an_attempt(entry, TransactionType.WHITELIST_ADD)
        WhitelistEntry.objects.filter(pk=entry.pk).update(remove_tx_hash=REMOVE_HASH)

        result = self.service(on_chain=True).reconcile_failed_adds()

        entry.refresh_from_db()
        self.assertEqual((entry.status, entry.add_tx_hash), (WhitelistStatus.ACTIVE, HASH))
        self.assertEqual((result["activated"], result["removals_the_chain_kept"]), (1, 0))

    def test_an_entry_with_no_recorded_attempt_is_not_activated_on_a_guess(self):
        self.an_entry(last_attempt=None)

        result = self.service(on_chain=True).reconcile_failed_adds()

        self.assertEqual((result["checked"], result["activated"]), (1, 0))

    def test_a_chain_that_will_not_answer_leaves_the_entry_where_it_was(self):
        entry = self.an_entry()
        service = self.service(on_chain=True)
        service.is_whitelisted.side_effect = RuntimeError("node down")

        result = service.reconcile_failed_adds()

        entry.refresh_from_db()
        self.assertEqual(entry.status, WhitelistStatus.FAILED)
        self.assertEqual((result["checked"], result["activated"]), (1, 0))
        self.assertIn("node down", result["errors"][0])
