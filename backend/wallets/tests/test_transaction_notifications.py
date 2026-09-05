"""The two transaction status writers notify the wallet account's members and nobody else."""

from unittest.mock import patch

from django.test import TestCase

from shared.tests.tenants import make_tenant
from users.models import Notification
from users.tasks.notifications import send_transaction_notification as run_task
from wallets.constants import TRANSACTION_STATUS_CONFIRMED
from wallets.services.transaction_confirmation import TransactionConfirmationService

TASK = "wallets.services.transaction_confirmation.send_transaction_notification"


class TransactionNotificationProducerTest(TestCase):
    def setUp(self):
        self.tenant = make_tenant("notified")
        self.bystander = make_tenant("bystander")
        self.tx = self.tenant.transaction

    def transaction_rows(self, user):
        return Notification.objects.filter(user=user, notification_type="transaction")

    def test_confirmation_creates_the_row_and_defers_one_job_per_member(self):
        with patch(TASK) as task:
            task.defer.side_effect = run_task  # run the deferred job inline so the row it writes is visible
            result = TransactionConfirmationService.confirm_transaction(self.tx.tx_hash, block_number=7)

        self.assertEqual(result["status"], "confirmed")
        task.defer.assert_called_once_with(
            user_id=str(self.tenant.user.pk), transaction_id=str(self.tx.uuid), event_type="confirmed"
        )
        row = self.transaction_rows(self.tenant.user).get()
        self.assertEqual(row.title, "Transaction Confirmed")
        self.assertEqual(row.data, {"type": "transaction", "event": "confirmed", "transaction_id": str(self.tx.uuid)})
        self.assertFalse(self.transaction_rows(self.bystander.user).exists())

        with patch(TASK) as task:
            self.assertEqual(
                TransactionConfirmationService.confirm_transaction(self.tx.tx_hash)["status"], "already_confirmed"
            )
        task.defer.assert_not_called()

    def test_failure_creates_the_row_and_defers_one_job_per_member(self):
        with patch(TASK) as task:
            task.defer.side_effect = run_task
            result = TransactionConfirmationService.fail_transaction(self.tx.tx_hash, reason="reverted")

        self.assertEqual(result["status"], "failed")
        task.defer.assert_called_once_with(
            user_id=str(self.tenant.user.pk), transaction_id=str(self.tx.uuid), event_type="failed"
        )
        self.assertEqual(self.transaction_rows(self.tenant.user).get().title, "Transaction Failed")
        self.assertFalse(self.transaction_rows(self.bystander.user).exists())

    def test_a_job_that_cannot_be_deferred_rolls_the_status_change_back(self):
        with patch(TASK) as task:
            task.defer.side_effect = RuntimeError("queue down")
            with self.assertRaises(RuntimeError):
                TransactionConfirmationService.confirm_transaction(self.tx.tx_hash)

        self.tx.refresh_from_db()
        self.assertNotEqual(self.tx.status, TRANSACTION_STATUS_CONFIRMED)
