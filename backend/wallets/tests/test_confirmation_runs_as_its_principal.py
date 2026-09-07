import inspect
from unittest import skipUnless
from unittest.mock import patch

from django.conf import settings
from django.db import connection
from django.test import TestCase

from shared.db import OPERATOR_ALIAS, configured, current_alias
from shared.db.principal import PRINCIPAL_SETTING, principal_of
from shared.tests.tenants import make_tenant
from wallets.tasks.confirmation import confirm_pending_transaction

POSTGRES = connection.vendor == "postgresql"
REASON = "the principal is a PostgreSQL setting, and set_config does not exist anywhere else"


class ThePrincipalIsRequiredRatherThanDefaultedTest(TestCase):

    def test_the_task_takes_a_principal_with_no_default(self):
        parameter = inspect.signature(confirm_pending_transaction.func).parameters["principal_id"]

        self.assertIs(parameter.default, inspect.Parameter.empty)

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

    def test_a_run_nobody_caused_takes_the_operator_connection_and_no_principal(self):
        seen = self._run_and_report(None)

        self.assertEqual(seen["alias"], configured(OPERATOR_ALIAS))
        self.assertIn(seen["principal"], (None, ""))

    def test_the_principal_does_not_survive_the_task(self):
        self._run_and_report(self.tenant.user.pk)

        self.assertIn(principal_of(), (None, ""))

    def test_the_reads_the_task_makes_survive_the_policies_as_that_principal(self):
        with connection.cursor() as cursor:
            cursor.execute(f"SET ROLE {settings.RLS_ROLES['app']}")
            cursor.execute("SELECT set_config(%s, %s, false)", [PRINCIPAL_SETTING, str(self.tenant.user.pk)])
        self.addCleanup(self._back_to_the_owner)

        from wallets.models import Transaction, Wallet

        self.assertEqual(Wallet.objects.filter(uuid=self.tenant.wallet.uuid).count(), 1)
        self.assertEqual(Transaction.objects.filter(wallet=self.tenant.wallet).count(), 1)

    def _back_to_the_owner(self):
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")
            cursor.execute(f"RESET {PRINCIPAL_SETTING}")
