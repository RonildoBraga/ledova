from datetime import timedelta
from unittest.mock import Mock

from django.test import TestCase
from django.utils import timezone

from users.models import UserAccount
from wallets.models import Wallet
from whitelist.models import WhitelistEntry, WhitelistStatus
from whitelist.services import WhitelistService
from whitelist.services.whitelist import GETH_TXPOOL_LIFETIME

HASH = "0x" + "7a" * 32


class AFailedAddTheChainContradictsIsReconciledTest(TestCase):

    def setUp(self):
        self.account = UserAccount.objects.create()
        self.wallet = Wallet.objects.create(user_account=self.account, address="0x" + "a" * 40, chain="base")

    def an_entry(self, *, tx_hash=HASH, age=timedelta(minutes=5), status=WhitelistStatus.FAILED):
        entry = WhitelistEntry.objects.create(wallet=self.wallet, status=status, add_tx_hash=tx_hash)
        WhitelistEntry.objects.filter(pk=entry.pk).update(updated_at=timezone.now() - age)
        entry.refresh_from_db()
        return entry

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

    def test_a_chain_that_will_not_answer_leaves_the_entry_where_it_was(self):
        entry = self.an_entry()
        service = self.service(on_chain=True)
        service.is_whitelisted.side_effect = RuntimeError("node down")

        result = service.reconcile_failed_adds()

        entry.refresh_from_db()
        self.assertEqual(entry.status, WhitelistStatus.FAILED)
        self.assertEqual((result["checked"], result["activated"]), (1, 0))
        self.assertIn("node down", result["errors"][0])
