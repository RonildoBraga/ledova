from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from unittest.mock import patch

from django.db import connections
from django.db.models import QuerySet
from rest_framework.test import APIClient, APITransactionTestCase

from shared.db import use_operator
from shared.tests.scoped import RunsOnTheScopedConnection
from wallets.models import WalletSubmissionFamily
from wallets.services.holdings import sync_holding
from wallets.tests.test_submission_families import SubmissionFamilyFixture


class FirstFamilySyncChecks(SubmissionFamilyFixture):
    def test_first_family_admitted_before_legacy_version_capture_cannot_lose_its_reservation(self):
        exists = QuerySet.exists
        admitted = False

        def submit_first_family():
            try:
                client = APIClient()
                client.force_authenticate(self.tenant.user)
                return client.post(
                    f"/api/wallets/{self.wallet.pk}/broadcast-transfer/",
                    {"signed_transaction": self.signed().raw_transaction.to_0x_hex()},
                    format="json",
                ).status_code
            finally:
                connections.close_all()

        def admit_after_absence_was_read(query):
            nonlocal admitted
            present = exists(query)
            if query.model is WalletSubmissionFamily and not admitted:
                self.assertFalse(present)
                admitted = True
                with ThreadPoolExecutor(max_workers=1) as pool:
                    self.assertEqual(pool.submit(submit_first_family).result(timeout=10), 200)
            return present

        with use_operator(), patch.object(QuerySet, "exists", admit_after_absence_was_read), patch(
            "wallets.services.holdings.fetch_chain_balance", return_value=Decimal("10")
        ):
            result = sync_holding(self.wallet, self.native)

        self.assertTrue(admitted)
        self.assertIsNone(result)
        self.assertEqual(self.quantity(), Decimal("7.999958"))
        with use_operator():
            self.assertIsNotNone(sync_holding(self.wallet, self.native))
        self.assertEqual(self.quantity(), Decimal("7.999958"))


class FirstFamilySyncTest(FirstFamilySyncChecks, APITransactionTestCase):
    pass


class ScopedFirstFamilySyncTest(RunsOnTheScopedConnection, FirstFamilySyncChecks, APITransactionTestCase):
    pass
