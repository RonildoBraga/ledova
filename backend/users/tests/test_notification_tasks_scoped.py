import json
from contextlib import ExitStack
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connections
from django.test import TransactionTestCase

from assets.models import Asset
from ledova_backend.procrastinate_app import app
from shared.db import (
    APP_ALIAS,
    OPERATOR_ALIAS,
    acting_for,
    current_alias,
    principal_of,
    use_operator,
)
from shared.tests.scoped import RunsOnTheScopedConnection
from users.models import (
    DeviceToken,
    Notification,
    NotificationPreferences,
    UserAccount,
    UserProfile,
)
from users.tasks.notifications import (
    send_push_notification,
    send_transaction_notification,
)
from wallets.models import Transaction, Wallet
from wallets.services.transaction_confirmation import _notify_wallet_users

User = get_user_model()


class NotificationTasksUseRecipientRolesTest(RunsOnTheScopedConnection, TransactionTestCase):
    def setUp(self):
        with use_operator():
            self.asset = Asset.objects.create(name="Synthetic token", symbol="NCTX", asset_type="cryptocurrency")
            self.recipient = self.make_recipient("recipient", "1")
            self.other = self.make_recipient("other", "2")
        client = patch("users.services.notifications.ExpoPushClient")
        self.addCleanup(client.stop)
        self.push = client.start().return_value.send_batch
        self.push.return_value = [{"status": "ok"}]

    def make_recipient(self, label, digit):
        user = User.objects.create_user(email=f"{label}@notification.example.test", password="synthetic-password")
        profile = UserProfile.objects.create(user=user)
        account = UserAccount.objects.create(account_number=f"NOTIF-{label}"[:20], director=profile)
        account.user_profiles.add(profile)
        wallet = Wallet.objects.create(user_account=account, address="0x" + digit * 40, chain="base")
        transaction = Transaction.objects.create(
            wallet=wallet,
            asset=self.asset,
            tx_hash="0x" + digit * 64,
            chain="base",
            from_address=wallet.address,
            to_address="0x" + "3" * 40,
            amount=Decimal("2.5"),
        )
        preferences = NotificationPreferences.objects.create(user_profile=profile)
        device = DeviceToken.objects.create(
            user=user, push_token=f"ExponentPushToken[{label}]", device_type=DeviceToken.DeviceType.IOS
        )
        return SimpleNamespace(
            user=user,
            profile=profile,
            account=account,
            wallet=wallet,
            transaction=transaction,
            preferences=preferences,
            device=device,
        )

    def run_task(self, task, **payload):
        with use_operator():
            result = task.func(**payload)
            self.assertEqual(current_alias(), OPERATOR_ALIAS)
        self.assertIn(principal_of(APP_ALIAS), (None, ""))
        return result

    def payload(self, recipient=None):
        recipient = recipient or self.recipient
        return {"user_id": str(recipient.user.pk), "title": "Synthetic title", "body": "Synthetic body"}

    def inbox(self, recipient=None):
        with use_operator():
            return list(Notification.objects.filter(user=(recipient or self.recipient).user))

    def assert_scoped_to(self, recipient):
        self.assertEqual(current_alias(), APP_ALIAS)
        with connections[current_alias()].cursor() as cursor:
            cursor.execute("SELECT current_user, current_setting('app.user_id', true)")
            self.assertEqual(cursor.fetchone(), (settings.RLS_ROLES[APP_ALIAS], str(recipient.user.pk)))

    def query_recorder(self, calls):
        tables = (
            "authentication_customuser",
            "users_userprofile",
            "users_notification_preferences",
            "users_device_token",
            "notifications",
            "transactions",
        )

        def execute(execute, sql, params, many, context):
            for table in tables:
                if f'"{table}"' in sql:
                    calls.append((context["connection"].alias, sql.split()[0], table))
            return execute(sql, params, many, context)

        return execute

    def test_push_lookups_inbox_and_invalid_device_write_use_the_recipient_role(self):
        observed = []

        def send(messages):
            self.assert_scoped_to(self.recipient)
            self.assertEqual(messages[0]["to"], self.recipient.device.push_token)
            self.assertEqual(set(DeviceToken.objects.values_list("pk", flat=True)), {self.recipient.device.pk})
            self.assertEqual(
                set(NotificationPreferences.objects.values_list("pk", flat=True)), {self.recipient.preferences.pk}
            )
            self.assertEqual(Notification.objects.count(), 1)
            self.assertEqual(DeviceToken.objects.filter(pk=self.other.device.pk).update(is_active=False), 0)
            return [{"status": "error", "details": {"error": "DeviceNotRegistered"}}]

        self.push.side_effect = send
        with ExitStack() as stack:
            for alias in (APP_ALIAS, OPERATOR_ALIAS):
                stack.enter_context(connections[alias].execute_wrapper(self.query_recorder(observed)))
            result = self.run_task(send_push_notification, **self.payload())

        self.assertEqual((result["status"], result["sent"], result["failed"]), ("sent", 0, 1))
        self.assertTrue(observed)
        self.assertEqual({alias for alias, _, _ in observed}, {APP_ALIAS})
        self.assertLessEqual(
            {
                ("SELECT", "authentication_customuser"),
                ("SELECT", "users_notification_preferences"),
                ("SELECT", "users_device_token"),
                ("INSERT", "notifications"),
                ("UPDATE", "users_device_token"),
            },
            {(operation, table) for _, operation, table in observed},
        )
        with use_operator():
            self.recipient.device.refresh_from_db()
            self.other.device.refresh_from_db()
        self.assertFalse(self.recipient.device.is_active)
        self.assertTrue(self.other.device.is_active)
        self.assertEqual(len(self.inbox()), 1)
        self.assertEqual(self.inbox(self.other), [])

    def test_invalid_result_cannot_deactivate_a_device_transferred_during_delivery(self):
        def send(messages):
            self.assertEqual(messages[0]["to"], self.recipient.device.push_token)
            with use_operator():
                DeviceToken.objects.filter(pk=self.recipient.device.pk).update(user=self.other.user)
            return [{"status": "error", "details": {"error": "DeviceNotRegistered"}}]

        self.push.side_effect = send
        result = self.run_task(send_push_notification, **self.payload())
        with use_operator():
            device = DeviceToken.objects.get(pk=self.recipient.device.pk)
        self.assertEqual((device.user_id, device.is_active), (self.other.user.pk, True))
        self.assertEqual(result["failed"], 1)
        self.assertEqual(len(self.inbox()), 1)

    def test_preferences_skip_push_but_preserve_the_recipients_inbox(self):
        with use_operator():
            NotificationPreferences.objects.filter(pk=self.recipient.preferences.pk).update(transaction_alerts=False)
        observed = []
        with ExitStack() as stack:
            for alias in (APP_ALIAS, OPERATOR_ALIAS):
                stack.enter_context(connections[alias].execute_wrapper(self.query_recorder(observed)))
            result = self.run_task(send_push_notification, **self.payload(), notification_type="transaction")
        self.assertEqual(result["status"], "skipped")
        self.assertEqual({alias for alias, _, _ in observed}, {APP_ALIAS})
        self.push.assert_not_called()
        self.assertEqual(len(self.inbox()), 1)
        self.assertEqual(self.inbox(self.other), [])

    def test_transaction_from_another_account_is_refused_before_notification_or_push(self):
        result = self.run_task(
            send_transaction_notification,
            user_id=str(self.recipient.user.pk),
            transaction_id=str(self.other.transaction.pk),
            event_type="confirmed",
        )
        self.assertEqual(result, {"status": "error", "error": "Transaction not found"})
        self.push.assert_not_called()
        self.assertEqual(self.inbox(), [])
        self.assertEqual(self.inbox(self.other), [])
        with use_operator():
            self.assertTrue(Transaction.objects.filter(pk=self.other.transaction.pk).exists())

    def queued_rows(self):
        with use_operator(), connections[OPERATOR_ALIAS].cursor() as cursor:
            cursor.execute("SELECT id, task_name, args FROM procrastinate_jobs ORDER BY id")
            rows = cursor.fetchall()
        return {row[0]: (row[1], row[2] if isinstance(row[2], dict) else json.loads(row[2])) for row in rows}

    def test_current_transaction_failure_notice_uses_recipient_reads_and_writes(self):
        with use_operator():
            Transaction.objects.filter(pk=self.recipient.transaction.pk).update(status="failed")
        observed = []

        def send(messages):
            self.assert_scoped_to(self.recipient)
            self.assertEqual(messages[0]["to"], self.recipient.device.push_token)
            return [{"status": "ok"}]

        self.push.side_effect = send
        with ExitStack() as stack:
            for alias in (APP_ALIAS, OPERATOR_ALIAS):
                stack.enter_context(connections[alias].execute_wrapper(self.query_recorder(observed)))
            result = self.run_task(
                send_transaction_notification,
                user_id=str(self.recipient.user.pk),
                transaction_id=str(self.recipient.transaction.pk),
                event_type="failed",
            )
        self.assertEqual(result["status"], "sent")
        self.assertEqual({alias for alias, _, _ in observed}, {APP_ALIAS})
        self.assertIn((APP_ALIAS, "SELECT", "transactions"), observed)
        (row,) = self.inbox()
        self.assertEqual(row.title, "Transaction Failed")
        self.assertEqual(row.data["event"], "failed")
        self.assertEqual(row.data["transaction_id"], str(self.recipient.transaction.pk))
        self.assertEqual(self.inbox(self.other), [])

    def delete_jobs(self, identifiers):
        with use_operator(), connections[OPERATOR_ALIAS].cursor() as cursor:
            for identifier in identifiers:
                cursor.execute("DELETE FROM procrastinate_jobs WHERE id = %s", [identifier])

    def test_actual_member_fanout_payload_rechecks_each_recipient_after_membership_removal(self):
        with use_operator():
            colleague = self.make_recipient("colleague", "4")
            self.recipient.account.user_profiles.add(colleague.profile)
        before = self.queued_rows()
        with acting_for(self.recipient.user.pk):
            transaction = Transaction.objects.select_related("wallet__user_account").get(
                pk=self.recipient.transaction.pk
            )
            self.assertFalse(UserProfile.objects.filter(pk=colleague.profile.pk).exists())
            _notify_wallet_users(transaction, "confirmed")
        jobs = {key: row for key, row in self.queued_rows().items() if key not in before}
        self.addCleanup(self.delete_jobs, list(jobs))
        self.assertEqual(len(jobs), 2)
        expected_ids = {str(self.recipient.user.pk), str(colleague.user.pk)}
        self.assertEqual({args["user_id"] for _, args in jobs.values()}, expected_ids)
        for name, args in jobs.values():
            self.assertEqual(name, send_transaction_notification.name)
            self.assertEqual(set(args), {"user_id", "transaction_id", "event_type"})
            self.assertEqual(args["transaction_id"], str(self.recipient.transaction.pk))
        with use_operator():
            self.recipient.account.user_profiles.remove(self.recipient.profile)
        delivered = []

        def send(messages):
            self.assert_scoped_to(colleague)
            delivered.extend(messages)
            return [{"status": "ok"}]

        self.push.side_effect = send
        by_recipient = {args["user_id"]: (name, args) for name, args in jobs.values()}
        removed_name, removed_args = by_recipient[str(self.recipient.user.pk)]
        removed = self.run_task(app.tasks[removed_name], **removed_args)
        self.assertEqual(removed, {"status": "error", "error": "Transaction not found"})
        self.push.assert_not_called()
        name, args = by_recipient[str(colleague.user.pk)]
        result = self.run_task(app.tasks[name], **args)
        self.assertEqual(result["status"], "sent")
        self.assertEqual([message["to"] for message in delivered], [colleague.device.push_token])
        self.assertEqual(self.inbox(), [])
        self.assertEqual(self.inbox(self.other), [])
        (row,) = self.inbox(colleague)
        self.assertEqual(row.title, "Transaction Confirmed")
        self.assertIn("2.5", row.body)
        self.assertIn(self.asset.symbol, row.body)
        self.assertEqual(
            row.data,
            {"type": "transaction", "event": "confirmed", "transaction_id": str(self.recipient.transaction.pk)},
        )

    def test_deferred_push_preserves_its_payload_and_refuses_a_deleted_recipient(self):
        with use_operator():
            user = User.objects.create_user(email="deleted@notification.example.test", password="synthetic-password")
            identifier = user.pk
            payload = {
                "user_id": str(identifier),
                "title": "Queued title",
                "body": "Queued body",
                "data": {"synthetic": True},
            }
            job_id = send_push_notification.configure(queue=f"n{uuid4().hex[:8]}").defer(**payload)
        self.addCleanup(self.delete_jobs, [job_id])
        name, args = self.queued_rows()[job_id]
        self.assertEqual((name, args), (send_push_notification.name, payload))
        with use_operator():
            User.objects.filter(pk=identifier).delete()
        result = self.run_task(app.tasks[name], **args)
        self.assertEqual(result, {"status": "error", "error": "User not found"})
        self.push.assert_not_called()
        self.assertEqual(self.inbox(), [])

    def test_a_missing_recipient_is_refused_instead_of_running_as_the_operator(self):
        payloads = (
            (send_push_notification, {"user_id": None, "title": "Synthetic title", "body": "Synthetic body"}),
            (
                send_transaction_notification,
                {
                    "user_id": None,
                    "transaction_id": str(self.recipient.transaction.pk),
                    "event_type": "confirmed",
                },
            ),
        )
        for task, payload in payloads:
            with self.subTest(task=task.name):
                observed = []
                with ExitStack() as stack:
                    for alias in (APP_ALIAS, OPERATOR_ALIAS):
                        stack.enter_context(connections[alias].execute_wrapper(self.query_recorder(observed)))
                    result = self.run_task(task, **payload)
                self.assertEqual(observed, [])
                self.assertEqual(result, {"status": "error", "error": "Recipient required"})
                self.push.assert_not_called()
        self.assertEqual(self.inbox(), [])
        self.assertEqual(self.inbox(self.other), [])

    def test_unexpected_delivery_failure_clears_principal_and_restores_the_worker_alias(self):
        def send(messages):
            self.assert_scoped_to(self.recipient)
            raise RuntimeError("synthetic delivery interruption")

        self.push.side_effect = send
        with use_operator():
            with self.assertRaisesRegex(RuntimeError, "synthetic delivery interruption"):
                send_push_notification.func(**self.payload())
            self.assertEqual(current_alias(), OPERATOR_ALIAS)
        self.assertIn(principal_of(APP_ALIAS), (None, ""))
        self.assertEqual(len(self.inbox()), 1)
