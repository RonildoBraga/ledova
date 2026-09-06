import threading
from datetime import timedelta
from decimal import Decimal
from queue import Queue
from time import monotonic, sleep
from unittest import skipUnless
from unittest.mock import patch

from django.db import close_old_connections, connection, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from companies.models import Company, CompanyStatus
from offerings.exceptions import OfferingRefusedException
from offerings.models import Offering, OfferingExemption, OfferingStatus
from offerings.services import offering as offering_service
from offerings.services.offering import ALREADY_LIVE, submit_offering
from shared.tests.tenants import make_tenant
from tokens.models import ShareToken

RENDEZVOUS_TIMEOUT = 1.0
BLOCKED_TIMEOUT = 5.0
JOIN_TIMEOUT = 30.0


@skipUnless(connection.vendor == "postgresql", "select_for_update is a no-op on SQLite")
class SubmitOfferingConcurrencyTest(TransactionTestCase):

    def setUp(self):
        patch("offerings.services.offering.send_push_notification").start()
        self.addCleanup(patch.stopall)
        self.tenant = make_tenant("issuer")
        Company.objects.filter(pk=self.tenant.company.pk).update(status=CompanyStatus.ACTIVE)
        self.tenant.company.refresh_from_db()
        self.token = self.tenant.deployed_token
        self.first = self.tenant.offering
        self.first.refresh_from_db()
        self.second = Offering.objects.create(
            token=self.token,
            exemption=OfferingExemption.PROFESSIONAL,
            price_per_share=Decimal("2.50"),
            minimum_shares=10,
            target_shares=50,
            cap_shares=100,
            opens_at=timezone.now() + timedelta(days=2),
            closes_at=timezone.now() + timedelta(days=40),
        )

    def _hold_both_at_the_liveness_check(self):
        barrier = threading.Barrier(2)
        checked = offering_service._check_not_already_live

        def rendezvous(offering):
            try:
                barrier.wait(timeout=RENDEZVOUS_TIMEOUT)
            except threading.BrokenBarrierError:
                pass
            return checked(offering)

        patcher = patch.object(offering_service, "_check_not_already_live", rendezvous)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _submit(self, offering, outcomes):
        close_old_connections()
        try:
            outcomes[offering.pk] = submit_offering(offering, submitted_by=self.tenant.user)
        except BaseException as exc:
            outcomes[offering.pk] = exc
        finally:
            connection.close()

    def _wait_until_blocked(self, backend_pid):
        deadline = monotonic() + BLOCKED_TIMEOUT
        while monotonic() < deadline:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_blocking_pids(%s)", [backend_pid])
                if cursor.fetchone()[0]:
                    return True
            sleep(0.01)
        return False

    def test_two_simultaneous_submissions_leave_one_live_offering_and_one_named_refusal(self):
        self._hold_both_at_the_liveness_check()
        outcomes = {}
        workers = [
            threading.Thread(target=self._submit, args=(offering, outcomes), name=f"submit-{offering.pk}")
            for offering in (self.first, self.second)
        ]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=JOIN_TIMEOUT)
        self.assertFalse(any(worker.is_alive() for worker in workers), outcomes)

        self.assertEqual(len(outcomes), 2, outcomes)
        refusals = [value for value in outcomes.values() if isinstance(value, BaseException)]
        self.assertEqual(len(refusals), 1, outcomes)
        live = Offering.objects.for_token(self.token).live().get()
        self.assertEqual(live.status, OfferingStatus.SUBMITTED)
        self.assertIsInstance(refusals[0], OfferingRefusedException)
        self.assertEqual(refusals[0].status_code, 400)
        self.assertEqual(
            str(refusals[0].detail),
            ALREADY_LIVE.format(
                symbol=self.token.symbol,
                status="submitted for review",
                opens=live.opens_at.date().isoformat(),
            ),
        )

    def test_a_submission_waits_on_the_token_row_lock_before_it_reads_the_live_offerings(self):
        started = Queue()
        outcomes = Queue()

        def worker():
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_backend_pid()")
                    started.put(cursor.fetchone()[0])
                outcomes.put(submit_offering(self.second, submitted_by=self.tenant.user))
            except BaseException as exc:
                outcomes.put(exc)
            finally:
                connection.close()

        thread = threading.Thread(target=worker, name="submit-under-lock")
        with transaction.atomic():
            ShareToken.objects.select_for_update().get(pk=self.token.pk)
            thread.start()
            blocked = self._wait_until_blocked(started.get(timeout=BLOCKED_TIMEOUT))
        thread.join(timeout=JOIN_TIMEOUT)

        self.assertTrue(blocked)
        self.assertFalse(thread.is_alive())
        outcome = outcomes.get(timeout=BLOCKED_TIMEOUT)
        self.assertIsInstance(outcome, Offering)
        self.second.refresh_from_db()
        self.assertEqual(self.second.status, OfferingStatus.SUBMITTED)
