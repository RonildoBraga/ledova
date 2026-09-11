from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier, Lock
from unittest import skipUnless

from django.db import connections
from rest_framework.test import APIClient, APITransactionTestCase

from shared.db import APP_ALIAS, configured, use_operator
from shared.tests.scoped import RunsOnTheScopedConnection
from wallets.models import WalletSubmission, WalletSubmissionFamily
from wallets.tests.test_submission_families import SubmissionFamilyFixture

POSTGRES = connections[configured(APP_ALIAS)].vendor == "postgresql"


@skipUnless(POSTGRES, "Concurrent wallet admission requires PostgreSQL")
class SubmissionFamilyConcurrencyChecks(SubmissionFamilyFixture):
    def concurrent_requests(self, signed):
        gate = Barrier(2)
        lock = Lock()
        calls = 0

        def read(address):
            nonlocal calls
            with lock:
                calls += 1
                index = calls
            if index <= 2:
                gate.wait(timeout=10)
            return dict(self.state)

        self.provider_client.get_mined_nonce.side_effect = read

        def submit(attempt):
            try:
                client = APIClient()
                client.force_authenticate(self.tenant.user)
                return client.post(
                    f"/api/wallets/{self.wallet.pk}/broadcast-transfer/",
                    {"signed_transaction": attempt.raw_transaction.to_0x_hex()},
                    format="json",
                ).status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(submit, attempt) for attempt in signed]
            return [future.result(timeout=20) for future in futures]

    def test_competing_replacements_cannot_both_use_the_same_generation(self):
        self.assertEqual(self.broadcast(self.signed()).status_code, 200)
        statuses = self.concurrent_requests([self.signed(gasPrice=4 * 10**9), self.signed(gasPrice=6 * 10**9)])
        self.assertEqual(sorted(statuses), [200, 400])
        with use_operator():
            family = WalletSubmissionFamily.objects.get(wallet=self.wallet)
            self.assertEqual(family.attempts.count(), 2)
            self.assertEqual(family.generation, 2)
            self.assertEqual(family.selected.parent.tx_hash, family.original_tx_hash)
            self.assertEqual(self.quantity(), Decimal("10") - family.native_exposure)

    def test_simultaneous_distinct_nonces_do_not_each_commit_the_same_available_balance(self):
        signed = [self.signed(value=6 * 10**18), self.signed(nonce=4, value=6 * 10**18)]
        statuses = self.concurrent_requests(signed)
        self.assertEqual(sorted(statuses), [200, 400])
        self.provider_client.get_mined_nonce.side_effect = lambda address: dict(self.state)
        loser = signed[statuses.index(400)]
        self.assertEqual(self.broadcast(loser).status_code, 400)
        with use_operator():
            self.assertEqual(WalletSubmission.objects.filter(wallet=self.wallet).count(), 1)
            self.assertEqual(WalletSubmissionFamily.objects.filter(wallet=self.wallet).count(), 1)
        self.assertEqual(self.quantity(), Decimal("3.999958"))


class SubmissionFamilyConcurrencyTest(SubmissionFamilyConcurrencyChecks, APITransactionTestCase):
    pass


class ScopedSubmissionFamilyConcurrencyTest(
    RunsOnTheScopedConnection, SubmissionFamilyConcurrencyChecks, APITransactionTestCase
):
    pass
