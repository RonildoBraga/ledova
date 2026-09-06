import threading
from unittest import skipUnless
from unittest.mock import patch

from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from web3 import Web3

from offerings.exceptions import SubscriptionRefusedException
from offerings.models import SettlementRail, Subscription, SubscriptionStatus
from offerings.services import payments as payment_service
from offerings.services.subscription import accept, allot, issue_instruction, submit
from offerings.tests.factories import (
    configure_operator,
    draft_subscription,
    eligible_subscriber,
    extra_wallet,
    open_offering,
    paid_subscription,
)
from shared.tests.tenants import make_tenant
from tokens.models import ShareIssuanceRequest

CHAIN_CLIENT = "tokens.services.share_token_service.get_base_chain_client"
DEFER = "offerings.tasks.subscription.allot_subscription_task.defer"
SIGNER = "0x" + "e" * 40
RENDEZVOUS_TIMEOUT = 2.0
JOIN_TIMEOUT = 30.0
SMALL_CODE_POOL = ("AAAAAAAA", "BBBBBBBB", "CCCCCCCC", "DDDDDDDD", "EEEEEEEE", "FFFFFFFF")


@skipUnless(connection.vendor == "postgresql", "select_for_update is a no-op on SQLite")
class SubscriptionConcurrencyTest(TransactionTestCase):
    def setUp(self):
        chain = patch(CHAIN_CLIENT).start().return_value
        chain.is_valid_address.return_value = True
        chain.to_checksum_address.side_effect = Web3.to_checksum_address
        chain.get_address_from_private_key.return_value = SIGNER
        self.defer = patch(DEFER).start()
        self.addCleanup(patch.stopall)

        self.tenant = make_tenant("racer")
        configure_operator()
        self.offering = open_offering(self.tenant, target_shares=200, cap_shares=500)
        eligible_subscriber(self.tenant)
        self.operator_user = make_tenant("racer-staff", staff=True).user

    def _run(self, targets):
        outcomes = {}
        threads = []
        for name, work in targets:
            threads.append(threading.Thread(target=self._wrap, args=(name, work, outcomes), name=name))
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=JOIN_TIMEOUT)
        self.assertFalse(any(thread.is_alive() for thread in threads), outcomes)
        return outcomes

    @staticmethod
    def _wrap(name, work, outcomes):
        close_old_connections()
        try:
            outcomes[name] = work()
        except BaseException as exc:
            outcomes[name] = exc
        finally:
            connection.close()

    def test_two_concurrent_allotments_of_one_subscription_create_exactly_one_request(self):
        subscription = paid_subscription(self.tenant, quantity=10)
        barrier = threading.Barrier(2)

        def race():
            try:
                barrier.wait(timeout=RENDEZVOUS_TIMEOUT)
            except threading.BrokenBarrierError:
                pass
            return allot(Subscription.objects.get(pk=subscription.pk), self.operator_user)

        outcomes = self._run([("first", race), ("second", race)])

        refusals = [value for value in outcomes.values() if isinstance(value, BaseException)]
        self.assertEqual(len(refusals), 1, outcomes)
        self.assertIsInstance(refusals[0], SubscriptionRefusedException)
        self.assertIn("cannot be allotted twice", str(refusals[0].detail))
        self.assertEqual(ShareIssuanceRequest.objects.count(), 1)
        subscription.refresh_from_db()
        self.assertEqual(subscription.issuance_request, ShareIssuanceRequest.objects.get())
        self.assertEqual(subscription.status, SubscriptionStatus.PAID)
        self.assertEqual(self.defer.call_count, 1)

    def test_concurrent_instructions_never_share_a_reference(self):
        accepted = []
        for index in range(len(SMALL_CODE_POOL)):
            subscription = draft_subscription(self.tenant, wallet=extra_wallet(self.tenant, f"{index}"))
            submit(subscription, submitted_by=self.tenant.user)
            accept(subscription)
            accepted.append(subscription)

        pool = iter(SMALL_CODE_POOL * 40)
        lock = threading.Lock()

        def next_code():
            with lock:
                return next(pool)

        patcher = patch.object(payment_service, "_code", next_code)
        patcher.start()
        self.addCleanup(patcher.stop)

        barrier = threading.Barrier(len(accepted))

        def issue(subscription):
            def work():
                try:
                    barrier.wait(timeout=RENDEZVOUS_TIMEOUT)
                except threading.BrokenBarrierError:
                    pass
                return issue_instruction(subscription, rail=SettlementRail.BANK_TRANSFER)

            return work

        outcomes = self._run([(str(row.pk), issue(row)) for row in accepted])

        self.assertEqual([type(value) for value in outcomes.values()], [Subscription] * len(accepted))
        references = list(Subscription.objects.exclude(reference="").values_list("reference", flat=True))
        self.assertEqual(len(references), len(accepted))
        self.assertEqual(len(set(references)), len(accepted))
        self.assertEqual(Subscription.objects.filter(status=SubscriptionStatus.AWAITING_PAYMENT).count(), len(accepted))
