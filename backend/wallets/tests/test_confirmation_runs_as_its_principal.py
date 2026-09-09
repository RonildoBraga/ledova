import inspect
from datetime import timedelta
from decimal import Decimal
from unittest import skipUnless
from unittest.mock import patch

from django.conf import settings
from django.db import connection
from django.test import TestCase
from django.utils import timezone

from integrations.alchemy.webhook import AlchemyWebhookView
from shared.db import current_alias
from shared.db.principal import PRINCIPAL_SETTING, principal_of
from shared.tests.tenants import make_tenant
from wallets.constants import TRANSACTION_STATUS_PENDING
from wallets.models import Transaction
from wallets.tasks.confirmation import (
    _confirm_pending_transaction,
    check_all_pending_transactions,
    confirm_pending_transaction,
)

POSTGRES = connection.vendor == "postgresql"
REASON = "the principal is a PostgreSQL setting, and set_config does not exist anywhere else"


class ThePrincipalIsRequiredRatherThanDefaultedTest(TestCase):

    def test_the_task_takes_a_principal_with_no_default(self):
        parameter = inspect.signature(confirm_pending_transaction.func).parameters["principal_id"]

        self.assertIs(parameter.default, inspect.Parameter.empty)
        self.assertIs(parameter.kind, inspect.Parameter.KEYWORD_ONLY)

    def test_the_transfer_service_takes_it_keyword_only_with_no_default(self):
        from wallets.services.transfers import TransferService

        parameter = inspect.signature(TransferService.broadcast_transfer).parameters["principal_id"]

        self.assertIs(parameter.default, inspect.Parameter.empty)
        self.assertIs(parameter.kind, inspect.Parameter.KEYWORD_ONLY)


@skipUnless(POSTGRES, REASON)
class TheTaskRunsAsWhoeverCausedItTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.tenant = make_tenant("confirming")

    def _run_and_report(self, principal_id):
        seen = {}

        def spy(tx_hash, wallet_uuid):
            seen["alias"] = current_alias()
            seen["principal"] = principal_of()
            return {"status": "spied"}

        with patch("wallets.tasks.confirmation._confirm_pending_transaction", spy):
            confirm_pending_transaction.func(
                tx_hash="0xdeadbeef", wallet_uuid=str(self.tenant.wallet.uuid), principal_id=principal_id
            )
        return seen

    def test_a_user_caused_run_carries_that_user_as_the_principal(self):
        seen = self._run_and_report(self.tenant.user.pk)

        self.assertEqual(seen["principal"], str(self.tenant.user.pk))

    def test_a_run_nobody_caused_chooses_the_operator_connection_and_no_principal(self):
        import shared.db.tasks as task_context

        with (
            patch.object(task_context, "use_operator", wraps=task_context.use_operator) as operator,
            patch.object(task_context, "use_app", wraps=task_context.use_app) as scoped,
        ):
            seen = self._run_and_report(None)

        self.assertEqual(operator.call_count, 1)
        self.assertEqual(scoped.call_count, 0)
        self.assertIn(seen["principal"], (None, ""))

    def test_a_user_caused_run_chooses_the_scoped_connection(self):
        import shared.db.tasks as task_context

        with (
            patch.object(task_context, "use_operator", wraps=task_context.use_operator) as operator,
            patch.object(task_context, "use_app", wraps=task_context.use_app) as scoped,
        ):
            self._run_and_report(self.tenant.user.pk)

        self.assertEqual(scoped.call_count, 1)
        self.assertEqual(operator.call_count, 0)

    def test_the_principal_does_not_survive_the_task(self):
        self._run_and_report(self.tenant.user.pk)

        self.assertIn(principal_of(), (None, ""))

    def test_the_task_itself_completes_under_the_policies_as_that_principal(self):
        transaction = Transaction.objects.filter(wallet=self.tenant.wallet).first()
        Transaction.objects.filter(pk=transaction.pk).update(status=TRANSACTION_STATUS_PENDING)

        with connection.cursor() as cursor:
            cursor.execute(f"SET ROLE {settings.RLS_ROLES['app']}")
            cursor.execute("SELECT set_config(%s, %s, false)", [PRINCIPAL_SETTING, str(self.tenant.user.pk)])
        self.addCleanup(self._back_to_the_owner)

        with patch("wallets.tasks.confirmation.get_blockchain_client") as client:
            client.return_value.get_transaction_receipt.return_value = {"status": 1, "blockNumber": 12}
            client.return_value.get_block.return_value = {"timestamp": 1700000000}
            result = _confirm_pending_transaction(transaction.tx_hash, str(self.tenant.wallet.uuid))

        self.assertEqual(result["status"], "confirmed")

    def _back_to_the_owner(self):
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")
            cursor.execute(f"RESET {PRINCIPAL_SETTING}")


class TheSitesThatCauseNoUserSayNoUserTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.tenant = make_tenant("noprincipal")

    def _pending_transaction(self, tx_hash):
        transaction = Transaction.objects.create(
            tx_hash=tx_hash,
            chain=self.tenant.wallet.chain,
            from_address=self.tenant.wallet.address,
            to_address="0x" + "f" * 40,
            amount=Decimal("1"),
            status=TRANSACTION_STATUS_PENDING,
            wallet=self.tenant.wallet,
            user_account=self.tenant.account,
            asset=self.tenant.refs.asset,
        )
        Transaction.objects.filter(pk=transaction.pk).update(created_at=timezone.now() - timedelta(hours=1))
        return transaction

    def test_the_sweep_enqueues_with_no_principal(self):
        self._pending_transaction("0xsweep")

        with patch("wallets.tasks.confirmation.confirm_pending_transaction.defer") as deferred:
            check_all_pending_transactions.func(timestamp=0)

        self.assertEqual([call.kwargs["principal_id"] for call in deferred.call_args_list], [None])

    def test_the_webhook_enqueues_with_no_principal(self):
        self._pending_transaction("0xwebhook")

        with patch("integrations.alchemy.webhook.confirm_pending_transaction.defer") as deferred:
            AlchemyWebhookView()._process_transaction_confirmation(tx_hash="0xwebhook", wallet=self.tenant.wallet)

        self.assertEqual([call.kwargs["principal_id"] for call in deferred.call_args_list], [None])

    def test_both_probes_reach_a_defer_at_all(self):
        self._pending_transaction("0xreached")

        with patch("wallets.tasks.confirmation.confirm_pending_transaction.defer") as swept:
            check_all_pending_transactions.func(timestamp=0)
        with patch("integrations.alchemy.webhook.confirm_pending_transaction.defer") as hooked:
            AlchemyWebhookView()._process_transaction_confirmation(tx_hash="0xreached", wallet=self.tenant.wallet)

        self.assertEqual(swept.call_count, 1)
        self.assertEqual(hooked.call_count, 1)
