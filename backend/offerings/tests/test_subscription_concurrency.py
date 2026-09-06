import threading
from datetime import date
from decimal import Decimal
from unittest import skipUnless
from unittest.mock import patch

from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from web3 import Web3

from offerings.exceptions import (
    InvalidSubscriptionTransitionException,
    SubscriptionRefusedException,
)
from offerings.models import SettlementRail, Subscription, SubscriptionStatus
from offerings.services import payments as payment_service
from offerings.services.subscription import (
    MONEY_ALREADY_IN,
    TX_HASH_ALREADY_USED,
    accept,
    allot,
    confirm_payment,
    issue_instruction,
    reject,
    submit,
    withdraw,
)
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
SUPPLY = "tokens.services.share_token_service.ShareTokenService.share_supply"
SIGNER = "0x" + "e" * 40
RENDEZVOUS_TIMEOUT = 2.0
JOIN_TIMEOUT = 30.0
SMALL_CODE_POOL = ("AAAAAAAA", "BBBBBBBB", "CCCCCCCC", "DDDDDDDD", "EEEEEEEE", "FFFFFFFF")
ONE_TRANSFER = "0x" + "9" * 64


@skipUnless(connection.vendor == "postgresql", "select_for_update is a no-op on SQLite")
class SubscriptionConcurrencyTest(TransactionTestCase):
    def setUp(self):
        chain = patch(CHAIN_CLIENT).start().return_value
        chain.is_valid_address.return_value = True
        chain.to_checksum_address.side_effect = Web3.to_checksum_address
        chain.get_address_from_private_key.return_value = SIGNER
        self.defer = patch(DEFER).start()
        patch(SUPPLY, return_value=(1000000, 0)).start()
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

    def _awaiting(self, suffix, reference):
        subscription = draft_subscription(self.tenant, wallet=extra_wallet(self.tenant, suffix))
        Subscription.objects.filter(pk=subscription.pk).update(
            status=SubscriptionStatus.AWAITING_PAYMENT, reference=reference
        )
        subscription.refresh_from_db()
        return subscription

    def _race_closing_against_a_payment(self, close, subscription):
        payer_ready = threading.Event()
        real_close = getattr(Subscription, close.__name__)

        def wait_then_write(row, notes):
            payer_ready.wait(timeout=JOIN_TIMEOUT)
            return real_close(row, notes)

        def closing():
            with patch.object(Subscription, close.__name__, wait_then_write):
                return close(Subscription.objects.get(pk=subscription.pk), "Changed our mind")

        def paying():
            payer_ready.set()
            return confirm_payment(
                Subscription.objects.get(pk=subscription.pk),
                confirmed_by=self.operator_user,
                amount_received=Decimal("25.00"),
                received_on=date(2026, 9, 1),
            )

        return self._run([("close", closing), ("pay", paying)])

    def test_a_reject_beside_a_payment_never_closes_the_row_over_the_money(self):
        subscription = self._awaiting("a", "PAYRACE01")

        outcomes = self._race_closing_against_a_payment(reject, subscription)

        subscription.refresh_from_db()
        self.assertFalse(subscription.has_money_in and subscription.status == SubscriptionStatus.REJECTED, outcomes)
        if subscription.status == SubscriptionStatus.REJECTED:
            self.assertIsInstance(outcomes["pay"], InvalidSubscriptionTransitionException)
            self.assertIsNone(subscription.amount_received)
        else:
            self.assertEqual(subscription.status, SubscriptionStatus.PAID)
            self.assertEqual(subscription.money_held, Decimal("25.00"))
            self.assertIsInstance(outcomes["close"], SubscriptionRefusedException, outcomes)
            self.assertEqual(
                str(outcomes["close"].detail),
                MONEY_ALREADY_IN.format(amount=Decimal("25.00"), reference="PAYRACE01"),
            )

    def test_a_withdrawal_beside_a_payment_never_closes_the_row_over_the_money(self):
        subscription = self._awaiting("b", "PAYRACE02")

        outcomes = self._race_closing_against_a_payment(withdraw, subscription)

        subscription.refresh_from_db()
        self.assertFalse(subscription.has_money_in and subscription.status == SubscriptionStatus.WITHDRAWN, outcomes)
        if subscription.status == SubscriptionStatus.WITHDRAWN:
            self.assertIsInstance(outcomes["pay"], InvalidSubscriptionTransitionException)
            self.assertIsNone(subscription.amount_received)
        else:
            self.assertEqual(subscription.status, SubscriptionStatus.PAID)
            self.assertEqual(subscription.money_held, Decimal("25.00"))
            self.assertIsInstance(outcomes["close"], SubscriptionRefusedException, outcomes)
            self.assertEqual(
                str(outcomes["close"].detail),
                MONEY_ALREADY_IN.format(amount=Decimal("25.00"), reference="PAYRACE02"),
            )

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

    def test_one_transfer_confirmed_twice_at_once_ends_in_a_refusal_not_a_server_error(self):
        rows = []
        for suffix in ("1", "2"):
            subscription = draft_subscription(self.tenant, wallet=extra_wallet(self.tenant, suffix))
            Subscription.objects.filter(pk=subscription.pk).update(
                status=SubscriptionStatus.AWAITING_PAYMENT,
                settlement_rail=SettlementRail.STABLECOIN,
                settlement_asset=self.tenant.refs.stablecoin,
                reference=f"PAY{suffix * 6}",
            )
            rows.append(subscription)

        barrier = threading.Barrier(2)

        def confirm(pk):
            def work():
                try:
                    barrier.wait(timeout=RENDEZVOUS_TIMEOUT)
                except threading.BrokenBarrierError:
                    pass
                return confirm_payment(
                    Subscription.objects.get(pk=pk),
                    confirmed_by=self.operator_user,
                    amount_received=Decimal("25.00"),
                    received_on=date(2026, 9, 1),
                    tx_hash=ONE_TRANSFER,
                )

            return work

        outcomes = self._run([(str(row.pk), confirm(row.pk)) for row in rows])

        refusals = [value for value in outcomes.values() if isinstance(value, BaseException)]
        self.assertEqual(len(refusals), 1, outcomes)
        self.assertIsInstance(refusals[0], SubscriptionRefusedException)
        self.assertEqual(str(refusals[0].detail), TX_HASH_ALREADY_USED.format(tx_hash=ONE_TRANSFER))
        self.assertEqual(Subscription.objects.filter(payment_tx_hash=ONE_TRANSFER).count(), 1)
