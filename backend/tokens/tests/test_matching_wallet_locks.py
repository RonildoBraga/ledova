from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier, Event
from time import monotonic, sleep
from unittest.mock import patch
from uuid import uuid4

from django.conf import settings
from django.db import connections
from rest_framework.test import APIClient, APITransactionTestCase

from operators.models import Operator
from shared.db import current_alias, use_operator
from shared.tests.scoped import RunsOnTheScopedConnection
from shared.tests.tenants import make_tenant
from tokens.models import OrderSubmission, SigningChallenge, SwapOrder, TransferOrder
from tokens.services.token_transfer_service import TokenTransferService
from tokens.tests.order_submission_fixtures import (
    BASE,
    COUNTERPARTY,
    SubmissionFixtures,
)
from wallets.models import Wallet


class ScopedMatchingWalletLockTest(RunsOnTheScopedConnection, SubmissionFixtures, APITransactionTestCase):
    def test_two_members_can_match_against_each_others_wallet_without_deadlocking(self):
        with use_operator():
            Operator.get()
            second = make_tenant("matching-member")
            self.tenant.account.user_profiles.add(second.profile)
            seller = self.counter_order()
            TransferOrder.objects.create(
                token=self.tenant.deployed_token,
                payment_asset=self.tenant.refs.stablecoin,
                wallet=self.wallet,
                owner_account=self.tenant.account,
                wallet_address=self.wallet.address,
                order_type="sell",
                quantity=10,
                price_per_share=Decimal("2.50"),
            )
        first_body = self.signed_body()
        self.client.force_authenticate(second.user)
        second_body = self.signed_body(
            self.body(
                submission_id=str(uuid4()),
                wallet_uuid=str(seller.wallet_id),
                wallet_address=seller.wallet_address,
            ),
            signer=COUNTERPARTY,
        )
        rendezvous = Barrier(2, timeout=10)
        observations = []
        find_matching = TokenTransferService.find_matching_order

        def together(service, order):
            connection = connections[current_alias()]
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL lock_timeout = '10s'")
                cursor.execute("SELECT pg_backend_pid(), current_user, current_setting('app.user_id')")
                observations.append(cursor.fetchone())
            rendezvous.wait()
            return find_matching(service, order)

        def create(user, body):
            try:
                client = APIClient()
                client.force_authenticate(user)
                client.raise_request_exception = False
                response = client.post(f"{BASE}create/", body, format="json")
                return response.status_code, response.content.decode()
            finally:
                connections.close_all()

        with patch.object(TokenTransferService, "find_matching_order", together), ThreadPoolExecutor(2) as pool:
            first = pool.submit(create, self.tenant.user, first_body)
            other = pool.submit(create, second.user, second_body)
            results = [first.result(timeout=25), other.result(timeout=25)]
        self.assertEqual([status for status, _ in results], [201, 201], results)
        self.assertEqual(len({pid for pid, _, _ in observations}), 2)
        self.assertEqual({role for _, role, _ in observations}, {settings.RLS_ROLES["app"]})
        self.assertEqual(
            {principal for _, _, principal in observations}, {str(self.tenant.user.pk), str(second.user.pk)}
        )
        with use_operator():
            submissions = OrderSubmission.objects.filter(
                owner_account=self.tenant.account,
                submission_id__in=[first_body["submission_id"], second_body["submission_id"]],
            )
            self.assertEqual(list(submissions.values_list("status", flat=True)), ["created", "created"])
            self.assertEqual(
                SigningChallenge.objects.filter(
                    digest__in=[first_body["digest"], second_body["digest"]], consumed_at__isnull=False
                ).count(),
                2,
            )
            swaps = SwapOrder.objects.filter(buy_order__in=submissions.values("order_id"))
            self.assertEqual(swaps.count(), 2)
            self.assertEqual(set(swaps.values_list("share_amount", flat=True)), {10})
            for swap in swaps:
                self.assertNotEqual(swap.buyer_wallet_id, swap.seller_wallet_id)
                self.assertEqual(swap.buy_order.status, "pending_signature")
                self.assertEqual(swap.sell_order.status, "pending_signature")
        self.chain.send_raw_transaction.assert_not_called()

    def assert_authorization_change_waits_for_submission(self, change):
        body = self.signed_body()
        paused = Event()
        release = Event()
        writer_ready = Event()
        pids = {}
        find_matching = TokenTransferService.find_matching_order

        def before_matching(service, order):
            with connections[current_alias()].cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                pids["submission"] = cursor.fetchone()[0]
            paused.set()
            if not release.wait(10):
                raise AssertionError("The test did not release the admitted submission")
            return find_matching(service, order)

        def create():
            try:
                client = APIClient()
                client.force_authenticate(self.tenant.user)
                return client.post(f"{BASE}create/", body, format="json").status_code
            finally:
                connections.close_all()

        def update_authorization():
            try:
                with use_operator():
                    with connections[current_alias()].cursor() as cursor:
                        cursor.execute("SET lock_timeout = '10s'")
                        cursor.execute("SELECT pg_backend_pid()")
                        pids["writer"] = cursor.fetchone()[0]
                    writer_ready.set()
                    return change()
            finally:
                connections.close_all()

        with patch.object(TokenTransferService, "find_matching_order", before_matching), ThreadPoolExecutor(2) as pool:
            submitting = pool.submit(create)
            try:
                self.assertTrue(paused.wait(5), "The submission never reached matching")
                writing = pool.submit(update_authorization)
                self.assertTrue(writer_ready.wait(5), "The authorization writer did not connect")
                self.assertNotEqual(pids["submission"], pids["writer"])
                deadline = monotonic() + 5
                observed = None
                while monotonic() < deadline:
                    with connections["default"].cursor() as cursor:
                        cursor.execute(
                            "SELECT %s = ANY(pg_blocking_pids(pid)), wait_event_type "
                            "FROM pg_stat_activity WHERE pid = %s",
                            [pids["submission"], pids["writer"]],
                        )
                        observed = cursor.fetchone()
                    if observed == (True, "Lock"):
                        break
                    if writing.done():
                        self.fail(f"Authorization changed before the submission committed: {writing.result()}")
                    sleep(0.01)
                self.assertEqual(observed, (True, "Lock"))
            finally:
                release.set()
            self.assertEqual(submitting.result(timeout=10), 201)
            writing.result(timeout=10)
        denied = self.message(self.body(submission_id=str(uuid4())))
        self.assertIn(denied.status_code, (400, 403, 404), denied.content)

    def test_wallet_verification_change_waits_then_prevents_a_fresh_submission(self):
        self.assert_authorization_change_waits_for_submission(
            lambda: Wallet.objects.filter(pk=self.wallet.pk).update(verification_status="PENDING")
        )

    def test_membership_removal_waits_then_prevents_a_fresh_submission(self):
        membership = self.tenant.account.user_profiles.through
        self.assert_authorization_change_waits_for_submission(
            lambda: membership.objects.filter(
                useraccount_id=self.tenant.account.pk, userprofile_id=self.tenant.profile.pk
            ).delete()
        )
