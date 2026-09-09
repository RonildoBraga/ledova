from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from assets.services.identity import native_asset_for_chain
from shared.tests.tenants import make_tenant
from wallets.constants import (
    TRANSACTION_STATUS_CONFIRMED,
    TRANSACTION_STATUS_FAILED,
    TRANSACTION_STATUS_PENDING,
    TRANSACTION_STATUS_REORGED,
    TRANSACTION_STATUS_REPLACED,
    TRANSACTION_STATUSES_THAT_RETURN_THE_OPTIMISTIC_DEBIT,
)
from wallets.models import Holding, Transaction, Wallet
from wallets.services.transaction_confirmation import TransactionConfirmationService

TASK = "wallets.services.transaction_confirmation.send_transaction_notification"
ORIGINAL = "0x" + "11" * 32
REPLACEMENT = "0x" + "22" * 32
HELD = Decimal("100")
SENT = Decimal("10")


class AReplacedTransactionKeepsTheHoldingItSpentTest(TestCase):

    def setUp(self):
        patch(TASK).start()
        self.addCleanup(patch.stopall)
        self.tenant = make_tenant("sender")
        self.wallet = self.tenant.wallet
        self.asset = native_asset_for_chain(self.wallet.chain)
        Holding.objects.create(wallet=self.wallet, asset=self.asset, quantity=HELD)

    def a_transaction(self, tx_hash=ORIGINAL, status=TRANSACTION_STATUS_PENDING, wallet=None, nonce=7):
        holding, _ = Holding.objects.get_or_create(
            wallet=wallet or self.wallet, asset=self.asset, defaults={"quantity": HELD}
        )
        return Transaction.objects.create(
            tx_hash=tx_hash,
            chain=self.wallet.chain,
            from_address=self.wallet.address,
            to_address="0x" + "cc" * 20,
            asset=self.asset,
            amount=SENT,
            status=status,
            nonce=nonce,
            deducted_amount=SENT,
            deducted_amount_sync_version=holding.sync_version,
            wallet=wallet or self.wallet,
        )

    def held(self):
        return Holding.objects.get(wallet=self.wallet, asset=self.asset).quantity

    def test_a_replaced_transaction_never_returns_the_debit_the_replacement_settles(self):
        tx = self.a_transaction()

        result = TransactionConfirmationService.mark_replaced(ORIGINAL, self.wallet, REPLACEMENT)

        tx.refresh_from_db()
        self.assertEqual(result["status"], TRANSACTION_STATUS_REPLACED)
        self.assertEqual((tx.status, tx.replaced_by_tx_hash), (TRANSACTION_STATUS_REPLACED, REPLACEMENT))
        self.assertEqual(self.held(), HELD)

    def test_replacing_twice_changes_nothing_and_says_why(self):
        self.a_transaction()
        TransactionConfirmationService.mark_replaced(ORIGINAL, self.wallet, REPLACEMENT)

        again = TransactionConfirmationService.mark_replaced(ORIGINAL, self.wallet, "0x" + "33" * 32)

        self.assertEqual(again["status"], "not_pending")
        self.assertEqual(again["current_status"], TRANSACTION_STATUS_REPLACED)
        self.assertEqual(Transaction.objects.get(tx_hash=ORIGINAL).replaced_by_tx_hash, REPLACEMENT)
        self.assertEqual(self.held(), HELD)

    def test_a_reorged_transaction_returns_the_debit_exactly_once(self):
        self.a_transaction(status=TRANSACTION_STATUS_CONFIRMED)

        first = TransactionConfirmationService.mark_reorged(ORIGINAL, self.wallet)
        after_first = self.held()
        second = TransactionConfirmationService.mark_reorged(ORIGINAL, self.wallet)

        self.assertEqual(first["status"], TRANSACTION_STATUS_REORGED)
        self.assertEqual(after_first, HELD + SENT)
        self.assertEqual(second["status"], "not_confirmed")
        self.assertEqual(second["current_status"], TRANSACTION_STATUS_REORGED)
        self.assertEqual(self.held(), HELD + SENT)

    def test_a_transaction_that_never_confirmed_cannot_be_reorged_out(self):
        self.a_transaction()

        result = TransactionConfirmationService.mark_reorged(ORIGINAL, self.wallet)

        self.assertEqual((result["status"], result["current_status"]), ("not_confirmed", TRANSACTION_STATUS_PENDING))
        self.assertEqual(self.held(), HELD)

    def test_a_failed_transaction_is_not_reorged_over(self):
        self.a_transaction(status=TRANSACTION_STATUS_FAILED)

        result = TransactionConfirmationService.mark_reorged(ORIGINAL, self.wallet)

        self.assertEqual(result["current_status"], TRANSACTION_STATUS_FAILED)

    def test_the_same_hash_tracked_for_two_wallets_is_two_rows_each_moved_on_its_own(self):
        other = Wallet.objects.create(
            user_account=self.wallet.user_account, address="0x" + "ab" * 20, chain=self.wallet.chain
        )
        theirs_replacement = "0x" + "44" * 32
        mine = self.a_transaction()
        theirs = self.a_transaction(wallet=other)

        TransactionConfirmationService.mark_replaced(ORIGINAL, self.wallet, REPLACEMENT)
        TransactionConfirmationService.mark_replaced(ORIGINAL, other, theirs_replacement)

        mine.refresh_from_db()
        theirs.refresh_from_db()
        self.assertEqual((mine.status, mine.replaced_by_tx_hash), (TRANSACTION_STATUS_REPLACED, REPLACEMENT))
        self.assertEqual((theirs.status, theirs.replaced_by_tx_hash), (TRANSACTION_STATUS_REPLACED, theirs_replacement))

    def test_a_hash_this_wallet_never_sent_is_not_found_rather_than_an_exception(self):
        self.a_transaction()

        result = TransactionConfirmationService.mark_replaced("0x" + "99" * 32, self.wallet, REPLACEMENT)

        self.assertEqual(result["status"], "not_found")

    def test_the_nonce_the_broadcast_computed_is_on_the_row_for_the_replacement_lookup(self):
        self.a_transaction(nonce=41)

        row = Transaction.objects.get(tx_hash=ORIGINAL)

        self.assertEqual(row.nonce, 41)
        self.assertEqual(Transaction.objects.filter(from_address=self.wallet.address, nonce=41).count(), 1)


class TheTupleIsTheOnlyPlaceTheRuleIsWrittenTest(TestCase):

    def setUp(self):
        patch(TASK).start()
        patch.object(TransactionConfirmationService, "_verify_holding_balance").start()
        patch.object(TransactionConfirmationService, "_update_snapshot_on_confirmation").start()
        self.addCleanup(patch.stopall)
        self.tenant = make_tenant("ledger")
        self.wallet = self.tenant.wallet
        self.asset = native_asset_for_chain(self.wallet.chain)

    def a_pending_row(self, tx_hash):
        holding, _ = Holding.objects.update_or_create(wallet=self.wallet, asset=self.asset, defaults={"quantity": HELD})
        return Transaction.objects.create(
            tx_hash=tx_hash,
            chain=self.wallet.chain,
            from_address=self.wallet.address,
            to_address="0x" + "cc" * 20,
            asset=self.asset,
            amount=SENT,
            status=TRANSACTION_STATUS_PENDING,
            deducted_amount=SENT,
            deducted_amount_sync_version=holding.sync_version,
            wallet=self.wallet,
        )

    def held(self):
        return Holding.objects.get(wallet=self.wallet, asset=self.asset).quantity

    def returned_the_debit(self, tx_hash, act, confirmed_first=False):
        row = self.a_pending_row(tx_hash)
        if confirmed_first:
            Transaction.objects.filter(pk=row.pk).update(status=TRANSACTION_STATUS_CONFIRMED)
        act(tx_hash)
        return self.held() > HELD

    def test_the_statuses_that_return_the_debit_are_exactly_the_ones_the_tuple_names(self):
        returned = set()
        outcomes = (
            (
                TRANSACTION_STATUS_FAILED,
                "0xf",
                lambda h: TransactionConfirmationService.fail_transaction(h, wallet=self.wallet),
                False,
            ),
            (
                TRANSACTION_STATUS_REORGED,
                "0xr",
                lambda h: TransactionConfirmationService.mark_reorged(h, self.wallet),
                True,
            ),
            (
                TRANSACTION_STATUS_REPLACED,
                "0xp",
                lambda h: TransactionConfirmationService.mark_replaced(h, self.wallet, REPLACEMENT),
                False,
            ),
            (
                TRANSACTION_STATUS_CONFIRMED,
                "0xc",
                lambda h: TransactionConfirmationService.confirm_transaction(h, block_number=7, wallet=self.wallet),
                False,
            ),
        )
        for status, tx_hash, act, confirmed_first in outcomes:
            with self.subTest(status=status):
                if self.returned_the_debit(tx_hash, act, confirmed_first):
                    returned.add(status)

        self.assertEqual(returned, set(TRANSACTION_STATUSES_THAT_RETURN_THE_OPTIMISTIC_DEBIT))
