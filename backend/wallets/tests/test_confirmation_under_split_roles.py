from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.conf import settings
from django.db import connections
from django.test import TransactionTestCase

from shared.db import (
    APP_ALIAS,
    OPERATOR_ALIAS,
    current_alias,
    principal_of,
    use_operator,
)
from shared.tests.scoped import RunsOnTheScopedConnection
from shared.tests.tenants import make_tenant
from wallets.constants import TRANSACTION_STATUS_CONFIRMED, TRANSACTION_STATUS_PENDING
from wallets.models import Transaction, Wallet
from wallets.tasks.confirmation import confirm_pending_transaction


class ConfirmationUsesSeparateRolesTest(RunsOnTheScopedConnection, TransactionTestCase):
    def setUp(self):
        with use_operator():
            self.owner = make_tenant("confirm-owner")
            self.other = make_tenant("confirm-other")
            Transaction.objects.all().update(status=TRANSACTION_STATUS_PENDING)
            for tenant in (self.owner, self.other):
                Transaction.objects.filter(pk=tenant.transaction.pk).update(
                    wallet=tenant.spare_wallet,
                    chain=tenant.spare_wallet.chain,
                    from_address=tenant.spare_wallet.address,
                    tx_hash="0x" + f"{tenant.user.pk:064x}",
                )
                tenant.transaction.refresh_from_db()
        self.observed = []
        client = SimpleNamespace(get_transaction_receipt=self.receipt, get_native_balance=lambda address: Decimal("1"))
        rpc = patch("wallets.tasks.confirmation.get_blockchain_client", return_value=client)
        self.addCleanup(rpc.stop)
        rpc.start()
        balances = patch("wallets.services.chain.get_blockchain_client", return_value=client)
        self.addCleanup(balances.stop)
        balances.start()
        delivery = patch("wallets.services.transaction_confirmation.send_transaction_notification.defer")
        self.addCleanup(delivery.stop)
        self.delivery = delivery.start()

    def receipt(self, tx_hash):
        alias = current_alias()
        with connections[alias].cursor() as cursor:
            cursor.execute("SELECT current_user, current_setting('app.user_id', true)")
            role, principal = cursor.fetchone()
        self.observed.append((alias, role, principal, Wallet.objects.filter(pk=self.other.spare_wallet.pk).exists()))
        return {"status": 1, "blockNumber": 12, "transactionHash": tx_hash}

    def run_task(self, tenant, principal_id):
        return confirm_pending_transaction.func(
            tx_hash=tenant.transaction.tx_hash, wallet_uuid=str(tenant.spare_wallet.uuid), principal_id=principal_id
        )

    def status_of(self, tenant):
        with use_operator():
            return Transaction.objects.get(pk=tenant.transaction.pk).status

    def test_user_task_switches_from_operator_to_app_and_commits_only_its_rows(self):
        with use_operator():
            result = self.run_task(self.owner, self.owner.user.pk)
            self.assertEqual(current_alias(), OPERATOR_ALIAS)

        self.assertEqual(result["status"], "confirmed")
        self.assertEqual(self.observed, [(APP_ALIAS, settings.RLS_ROLES[APP_ALIAS], str(self.owner.user.pk), False)])
        self.assertEqual(self.status_of(self.owner), TRANSACTION_STATUS_CONFIRMED)
        self.assertEqual(self.status_of(self.other), TRANSACTION_STATUS_PENDING)
        self.assertIn(principal_of(APP_ALIAS), (None, ""))
        self.delivery.assert_called_once()

    def test_a_foreign_wallet_is_invisible_before_any_chain_or_write_effect(self):
        with use_operator():
            result = self.run_task(self.other, self.owner.user.pk)

        self.assertEqual(result, {"status": "error", "error": "Wallet not found"})
        self.assertEqual(self.observed, [])
        self.assertEqual(self.status_of(self.other), TRANSACTION_STATUS_PENDING)
        self.delivery.assert_not_called()

    def test_system_task_switches_from_app_to_the_actual_operator_role(self):
        self.assertEqual(current_alias(), APP_ALIAS)
        result = self.run_task(self.other, None)

        self.assertEqual(result["status"], "confirmed")
        alias, role, principal, sees_other = self.observed[0]
        self.assertEqual((alias, role, sees_other), (OPERATOR_ALIAS, settings.RLS_ROLES[OPERATOR_ALIAS], True))
        self.assertIn(principal, (None, ""))
        self.assertEqual(current_alias(), APP_ALIAS)
        self.assertEqual(self.status_of(self.other), TRANSACTION_STATUS_CONFIRMED)

    def test_retry_failure_clears_the_app_principal_and_restores_the_worker_alias(self):
        with use_operator(), patch(
            "wallets.tasks.confirmation.get_blockchain_client", side_effect=RuntimeError("receipt unavailable")
        ):
            with self.assertRaisesRegex(RuntimeError, "receipt unavailable"):
                self.run_task(self.owner, self.owner.user.pk)
            self.assertEqual(current_alias(), OPERATOR_ALIAS)

        self.assertIn(principal_of(APP_ALIAS), (None, ""))
        self.assertEqual(self.status_of(self.owner), TRANSACTION_STATUS_PENDING)
