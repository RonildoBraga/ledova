from datetime import timedelta
from unittest.mock import Mock

from django.test import TestCase
from django.utils import timezone

from blockchain.models import BlockchainTransaction, TransactionStatus, TransactionType
from users.models import UserAccount
from wallets.models import Wallet
from whitelist.models import WhitelistEntry, WhitelistStatus
from whitelist.services import WhitelistService

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

    def test_an_add_older_than_any_node_would_hold_it_is_still_reconciled(self):
        entry = self.an_entry(age=timedelta(days=3))
        service = self.service(on_chain=True)

        result = service.reconcile_failed_adds()

        entry.refresh_from_db()
        self.assertEqual((entry.status, entry.add_tx_hash), (WhitelistStatus.ACTIVE, HASH))
        self.assertEqual((result["checked"], result["activated"]), (1, 1))
        service.is_whitelisted.assert_called_once()

    def test_a_failure_with_no_hash_is_left_alone_however_old_it_is(self):
        entry = self.an_entry(tx_hash=None, age=timedelta(days=30))
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

    def test_a_reconciled_removal_is_read_and_warned_about_only_once(self):
        entry = self.an_entry(last_attempt=TransactionType.WHITELIST_REMOVE)
        WhitelistEntry.objects.filter(pk=entry.pk).update(is_whitelisted=True, remove_tx_hash=REMOVE_HASH)
        service = self.service(on_chain=True)

        with self.assertLogs("whitelist.services.whitelist", level="WARNING") as logs:
            results = [service.reconcile_failed_adds() for _ in range(3)]

        self.assertEqual([result["checked"] for result in results], [1, 0, 0])
        self.assertEqual(len(logs.output), 1)
        service.is_whitelisted.assert_called_once_with(self.wallet.address)
        entry.refresh_from_db()
        self.assertEqual((entry.status, entry.is_whitelisted), (WhitelistStatus.FAILED, True))
        self.assertEqual((entry.add_tx_hash, entry.remove_tx_hash), (HASH, REMOVE_HASH))

    def test_a_new_failed_removal_is_reconciled_and_warned_about_again(self):
        entry = self.an_entry(last_attempt=TransactionType.WHITELIST_REMOVE)
        service = self.service(on_chain=True)
        service.reconcile_failed_adds()
        entry.refresh_from_db()
        entry.mark_remove_failed("retry reverted", "0x" + "33" * 32)
        self.an_attempt(entry, TransactionType.WHITELIST_REMOVE)

        with self.assertLogs("whitelist.services.whitelist", level="WARNING") as logs:
            results = [service.reconcile_failed_adds() for _ in range(2)]

        self.assertEqual([result["checked"] for result in results], [1, 0])
        self.assertEqual(len(logs.output), 1)
        self.assertEqual(service.is_whitelisted.call_count, 2)

    def test_overlapping_sweeps_warn_about_the_same_failure_only_once(self):
        self.an_entry(last_attempt=TransactionType.WHITELIST_REMOVE)
        first = self.service(on_chain=True)
        second = self.service(on_chain=True)

        def answer_after_another_sweep(address):
            second.reconcile_failed_adds()
            return True

        first.is_whitelisted.side_effect = answer_after_another_sweep

        with self.assertLogs("whitelist.services.whitelist", level="WARNING") as logs:
            result = first.reconcile_failed_adds()

        self.assertEqual(len(logs.output), 1)
        self.assertEqual(result["removals_the_chain_kept"], 0)

    def test_a_retry_during_the_chain_read_is_left_for_a_new_sweep(self):
        entry = self.an_entry(last_attempt=TransactionType.WHITELIST_REMOVE)
        service = self.service(on_chain=True)

        def answer_after_a_retry(address):
            entry.mark_remove_failed("new failure", REMOVE_HASH)
            self.an_attempt(entry, TransactionType.WHITELIST_REMOVE)
            return True

        service.is_whitelisted.side_effect = answer_after_a_retry

        with self.assertNoLogs("whitelist.services.whitelist", level="WARNING"):
            result = service.reconcile_failed_adds()

        self.assertEqual(result["removals_the_chain_kept"], 0)
        service.is_whitelisted.side_effect = None
        self.assertEqual(service.reconcile_failed_adds()["removals_the_chain_kept"], 1)

    def test_an_unconfirmed_add_stays_eligible_for_later_reconciliation(self):
        entry = self.an_entry()
        service = self.service(on_chain=False)

        results = [service.reconcile_failed_adds() for _ in range(2)]
        service.is_whitelisted.return_value = True
        result = service.reconcile_failed_adds()

        self.assertEqual([result["checked"] for result in results], [1, 1])
        self.assertEqual(result["activated"], 1)
        entry.refresh_from_db()
        self.assertEqual(entry.status, WhitelistStatus.ACTIVE)

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
