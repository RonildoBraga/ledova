from unittest import skipUnless
from unittest.mock import patch

from django.db import connection
from django.test import TestCase
from procrastinate.contrib.django.models import ProcrastinateJob

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
            task.defer.side_effect = run_task
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


@skipUnless(connection.vendor == "postgresql", "procrastinate job rows live in PostgreSQL only")
class TransactionNotificationJobRowTest(TestCase):

    def setUp(self):
        self.tenant = make_tenant("jobrow")
        second = make_tenant("jobrow-second")
        self.tenant.account.user_profiles.add(second.profile)
        self.tx = self.tenant.transaction

    def job_rows(self):
        return ProcrastinateJob.objects.filter(task_name=run_task.name)

    def test_confirmation_writes_one_todo_job_per_account_member(self):
        self.assertEqual(TransactionConfirmationService.confirm_transaction(self.tx.tx_hash)["status"], "confirmed")

        rows = list(self.job_rows())
        members = self.tenant.account.user_profiles.values_list("user_id", flat=True)
        self.assertEqual(sorted(row.args["user_id"] for row in rows), sorted(str(pk) for pk in members))
        self.assertEqual({row.status for row in rows}, {"todo"})
        self.assertEqual({row.args["transaction_id"] for row in rows}, {str(self.tx.uuid)})
        self.assertEqual({row.args["event_type"] for row in rows}, {"confirmed"})

    def test_a_failure_after_the_defer_rolls_the_job_rows_back_with_the_status(self):
        notify = TransactionConfirmationService._notify_wallet_users

        def notify_then_fail(tx, event):
            notify(tx, event)
            raise RuntimeError("after the defer")

        with patch.object(TransactionConfirmationService, "_notify_wallet_users", side_effect=notify_then_fail):
            with self.assertRaises(RuntimeError):
                TransactionConfirmationService.confirm_transaction(self.tx.tx_hash, block_number=9)

        self.assertEqual(self.job_rows().count(), 0)
        self.tx.refresh_from_db()
        self.assertNotEqual(self.tx.status, TRANSACTION_STATUS_CONFIRMED)
        self.assertIsNone(self.tx.block_number)
