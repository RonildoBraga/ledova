from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from offerings.exceptions import (
    InvalidSubscriptionTransitionException,
    SubscriptionRefusedException,
)
from offerings.models import SettlementRail, SubscriptionStatus
from offerings.services.payments import TX_HASH_MALFORMED
from offerings.services.subscription import (
    ABOVE_CAP,
    ABOVE_MAXIMUM,
    BELOW_MINIMUM,
    MONEY_ALREADY_IN,
    NOTHING_COVERED,
    OFFERING_NOT_OPEN,
    RECEIVED_NOT_POSITIVE,
    REFUND_ABOVE_HELD,
    REFUND_NOT_POSITIVE,
    TX_HASH_ALREADY_USED,
    TX_HASH_REQUIRED,
    WALLET_NOT_ON_ACCOUNT,
    accept,
    confirm_payment,
    create_draft,
    issue_instruction,
    record_refund,
    reject,
    submit,
    withdraw,
)
from offerings.tests.factories import (
    configure_operator,
    draft_subscription,
    eligible_subscriber,
    open_offering,
)
from shared.tests.tenants import make_tenant
from users.exceptions import InvestorNotEligibleException
from users.models import InvestorClassification, InvestorClassificationStatus


class SubscriptionServiceTestCase(TestCase):
    def setUp(self):
        self.tenant = make_tenant("investor")
        self.stablecoin = self.tenant.refs.stablecoin
        configure_operator(stablecoin=self.stablecoin)
        self.offering = open_offering(self.tenant, stablecoin=self.stablecoin)
        eligible_subscriber(self.tenant)

    def _refusal(self, call, *args, **kwargs):
        with self.assertRaises(SubscriptionRefusedException) as raised:
            call(*args, **kwargs)
        return str(raised.exception.detail)

    def _to_awaiting(self, subscription=None, rail=SettlementRail.BANK_TRANSFER, asset=None):
        subscription = subscription or draft_subscription(self.tenant)
        submit(subscription, submitted_by=self.tenant.user)
        accept(subscription)
        issue_instruction(subscription, rail=rail, settlement_asset=asset)
        return subscription


class SubscriptionServiceTest(SubscriptionServiceTestCase):
    def test_a_draft_snapshots_the_price_and_the_amount_due(self):
        subscription = draft_subscription(self.tenant, quantity=12)
        self.assertEqual(subscription.status, SubscriptionStatus.DRAFT)
        self.assertEqual(subscription.price_per_share, Decimal("2.50"))
        self.assertEqual(subscription.amount_due, Decimal("30.00"))
        self.assertIsNone(subscription.allotted_quantity)
        self.assertEqual(subscription.allotment_quantity, 12)

    def test_a_later_price_edit_cannot_move_a_live_subscription(self):
        subscription = draft_subscription(self.tenant, quantity=10)
        self.offering.price_per_share = Decimal("9.99")
        self.offering.save(update_fields=["price_per_share"])
        subscription.refresh_from_db()
        self.assertEqual((subscription.price_per_share, subscription.amount_due), (Decimal("2.50"), Decimal("25.00")))

    def test_a_closed_offering_takes_no_subscription(self):
        self.offering.closes_at = timezone.now() - timedelta(hours=1)
        self.offering.save(update_fields=["closes_at"])
        self.assertEqual(
            self._refusal(draft_subscription, self.tenant),
            OFFERING_NOT_OPEN.format(symbol=self.offering.token.symbol),
        )

    def test_the_bounds_are_enforced_on_the_draft(self):
        symbol = self.offering.token.symbol
        self.assertEqual(
            self._refusal(draft_subscription, self.tenant, quantity=9),
            BELOW_MINIMUM.format(symbol=symbol, minimum=10, quantity=9),
        )
        self.assertEqual(
            self._refusal(draft_subscription, self.tenant, quantity=101),
            ABOVE_CAP.format(symbol=symbol, cap=100, quantity=101),
        )
        self.offering.maximum_shares = 20
        self.offering.save(update_fields=["maximum_shares"])
        self.assertEqual(
            self._refusal(draft_subscription, self.tenant, quantity=21),
            ABOVE_MAXIMUM.format(symbol=symbol, maximum=20, quantity=21),
        )

    def test_a_wallet_from_another_account_is_refused(self):
        stranger = make_tenant("stranger")
        self.assertEqual(
            self._refusal(create_draft, self.offering, self.tenant.account, stranger.wallet, 10, self.tenant.user),
            WALLET_NOT_ON_ACCOUNT,
        )

    def test_submit_accept_and_instruction_walk_the_legal_path(self):
        subscription = self._to_awaiting()
        self.assertEqual(subscription.status, SubscriptionStatus.AWAITING_PAYMENT)
        self.assertTrue(subscription.reference.startswith("PAY"), subscription.reference)
        self.assertIsNotNone(subscription.payment_instruction_issued_at)
        self.assertIsNotNone(subscription.payment_due_at)
        self.assertEqual(subscription.settlement_rail, SettlementRail.BANK_TRANSFER)
        self.assertIsNone(subscription.settlement_asset)

    def test_the_due_date_is_clamped_to_the_offering_close(self):
        self.offering.closes_at = timezone.now() + timedelta(hours=2)
        self.offering.save(update_fields=["closes_at"])
        subscription = self._to_awaiting()
        self.assertEqual(subscription.payment_due_at, self.offering.closes_at)

    def test_a_stablecoin_instruction_freezes_the_raw_amount(self):
        subscription = self._to_awaiting(rail=SettlementRail.STABLECOIN, asset=self.stablecoin)
        self.assertEqual(subscription.settlement_asset, self.stablecoin)
        self.assertEqual(subscription.settlement_amount, 2500)

    def test_every_transition_refuses_from_the_wrong_status(self):
        subscription = draft_subscription(self.tenant)
        with self.assertRaises(InvalidSubscriptionTransitionException):
            accept(subscription)
        submit(subscription, submitted_by=self.tenant.user)
        with self.assertRaises(InvalidSubscriptionTransitionException):
            submit(subscription, submitted_by=self.tenant.user)
        with self.assertRaises(InvalidSubscriptionTransitionException):
            issue_instruction(subscription, rail=SettlementRail.BANK_TRANSFER)
        accept(subscription)
        with self.assertRaises(InvalidSubscriptionTransitionException):
            accept(subscription)

    def test_eligibility_is_rechecked_at_accept_because_a_certificate_can_lapse(self):
        subscription = draft_subscription(self.tenant)
        submit(subscription, submitted_by=self.tenant.user)

        InvestorClassification.objects.filter(user_account=self.tenant.account).update(
            expires_at=timezone.now() - timedelta(days=1)
        )
        with self.assertRaises(InvestorNotEligibleException) as raised:
            accept(subscription)

        self.assertIn("no_live_classification", raised.exception.reasons)
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, SubscriptionStatus.SUBMITTED)

    def test_a_revoked_classification_also_stops_acceptance(self):
        subscription = draft_subscription(self.tenant)
        submit(subscription, submitted_by=self.tenant.user)
        InvestorClassification.objects.filter(user_account=self.tenant.account).update(
            status=InvestorClassificationStatus.REVOKED
        )
        with self.assertRaises(InvestorNotEligibleException):
            accept(subscription)

    def test_an_exact_payment_moves_the_row_to_paid(self):
        subscription = self._to_awaiting()
        confirm_payment(
            subscription,
            confirmed_by=self.tenant.user,
            amount_received=Decimal("25.00"),
            received_on=timezone.now().date(),
            reference_seen=subscription.reference,
        )
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, SubscriptionStatus.PAID)
        self.assertEqual(subscription.amount_received, Decimal("25.00"))
        self.assertIsNone(subscription.refund_amount)
        self.assertEqual(subscription.payment_confirmed_by, self.tenant.user)
        self.assertEqual(subscription.allotment_quantity, 10)

    def test_an_overpayment_is_paid_with_a_refund_owed(self):
        subscription = self._to_awaiting()
        confirm_payment(
            subscription,
            confirmed_by=self.tenant.user,
            amount_received=Decimal("30.00"),
            received_on=timezone.now().date(),
        )
        subscription.refresh_from_db()
        self.assertEqual((subscription.status, subscription.refund_amount), (SubscriptionStatus.PAID, Decimal("5.00")))
        self.assertEqual(subscription.allotment_quantity, 10)

    def test_an_underpayment_waits_for_the_balance(self):
        subscription = self._to_awaiting()
        confirm_payment(
            subscription,
            confirmed_by=self.tenant.user,
            amount_received=Decimal("12.00"),
            received_on=timezone.now().date(),
        )
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, SubscriptionStatus.AWAITING_PAYMENT)
        self.assertEqual(subscription.amount_outstanding, Decimal("13.00"))
        self.assertIsNone(subscription.allotted_quantity)

    def test_a_second_tranche_completes_an_underpaid_subscription(self):
        subscription = self._to_awaiting()
        confirm_payment(
            subscription,
            confirmed_by=self.tenant.user,
            amount_received=Decimal("12.00"),
            received_on=timezone.now().date(),
        )
        confirm_payment(
            subscription,
            confirmed_by=self.tenant.user,
            amount_received=Decimal("25.00"),
            received_on=timezone.now().date(),
            notes="Second tranche of 13.00 brought the total to 25.00",
        )
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, SubscriptionStatus.PAID)
        self.assertEqual(subscription.amount_received, Decimal("25.00"))

    def test_accepting_a_partial_payment_as_final_scales_the_allotment_and_owes_the_residual(self):
        subscription = self._to_awaiting()
        confirm_payment(
            subscription,
            confirmed_by=self.tenant.user,
            amount_received=Decimal("16.00"),
            received_on=timezone.now().date(),
            accept_as_final=True,
        )
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, SubscriptionStatus.PAID)
        self.assertEqual(subscription.allotted_quantity, 6)
        self.assertEqual(subscription.refund_amount, Decimal("1.00"))

    def test_a_final_payment_that_covers_no_whole_share_is_refused(self):
        subscription = self._to_awaiting()
        message = self._refusal(
            confirm_payment,
            subscription,
            confirmed_by=self.tenant.user,
            amount_received=Decimal("1.00"),
            received_on=timezone.now().date(),
            accept_as_final=True,
        )
        self.assertEqual(message, NOTHING_COVERED.format(received=Decimal("1.00"), price=Decimal("2.50")))

    def test_a_zero_payment_is_refused(self):
        subscription = self._to_awaiting()
        self.assertEqual(
            self._refusal(
                confirm_payment,
                subscription,
                confirmed_by=self.tenant.user,
                amount_received=Decimal("0"),
                received_on=timezone.now().date(),
            ),
            RECEIVED_NOT_POSITIVE,
        )

    def test_the_stablecoin_rail_demands_the_transfer_hash(self):
        subscription = self._to_awaiting(rail=SettlementRail.STABLECOIN, asset=self.stablecoin)
        self.assertEqual(
            self._refusal(
                confirm_payment,
                subscription,
                confirmed_by=self.tenant.user,
                amount_received=Decimal("25.00"),
                received_on=timezone.now().date(),
            ),
            TX_HASH_REQUIRED,
        )

    def test_one_transfer_hash_cannot_fund_two_subscriptions(self):
        first = self._to_awaiting(rail=SettlementRail.STABLECOIN, asset=self.stablecoin)
        second = self._to_awaiting(
            draft_subscription(self.tenant), rail=SettlementRail.STABLECOIN, asset=self.stablecoin
        )
        tx_hash = "0x" + "1" * 64
        confirm_payment(
            first,
            confirmed_by=self.tenant.user,
            amount_received=Decimal("25.00"),
            received_on=timezone.now().date(),
            tx_hash=tx_hash,
        )
        self.assertEqual(
            self._refusal(
                confirm_payment,
                second,
                confirmed_by=self.tenant.user,
                amount_received=Decimal("25.00"),
                received_on=timezone.now().date(),
                tx_hash=tx_hash,
            ),
            TX_HASH_ALREADY_USED.format(tx_hash=tx_hash),
        )
        second.refresh_from_db()
        self.assertEqual(second.status, SubscriptionStatus.AWAITING_PAYMENT)

    def test_the_same_transfer_hash_in_another_case_is_the_same_transfer(self):
        first = self._to_awaiting(rail=SettlementRail.STABLECOIN, asset=self.stablecoin)
        second = self._to_awaiting(
            draft_subscription(self.tenant), rail=SettlementRail.STABLECOIN, asset=self.stablecoin
        )
        lower = "0x" + "abab" * 16
        confirm_payment(
            first,
            confirmed_by=self.tenant.user,
            amount_received=Decimal("25.00"),
            received_on=timezone.now().date(),
            tx_hash=lower.upper(),
        )
        first.refresh_from_db()
        self.assertEqual(first.payment_tx_hash, lower)
        self.assertEqual(
            self._refusal(
                confirm_payment,
                second,
                confirmed_by=self.tenant.user,
                amount_received=Decimal("25.00"),
                received_on=timezone.now().date(),
                tx_hash=f"  {lower}  ",
            ),
            TX_HASH_ALREADY_USED.format(tx_hash=lower),
        )
        second.refresh_from_db()
        self.assertEqual(second.status, SubscriptionStatus.AWAITING_PAYMENT)

    def test_something_that_is_not_a_transfer_hash_is_refused_before_it_is_stored(self):
        subscription = self._to_awaiting(rail=SettlementRail.STABLECOIN, asset=self.stablecoin)
        for candidate in ("0xdeadbeef", "0x" + "z" * 64, "ab" * 32):
            with self.subTest(candidate=candidate):
                self.assertEqual(
                    self._refusal(
                        confirm_payment,
                        subscription,
                        confirmed_by=self.tenant.user,
                        amount_received=Decimal("25.00"),
                        received_on=timezone.now().date(),
                        tx_hash=candidate,
                    ),
                    TX_HASH_MALFORMED.format(tx_hash=candidate),
                )
        subscription.refresh_from_db()
        self.assertEqual(subscription.payment_tx_hash, "")
        self.assertEqual(subscription.status, SubscriptionStatus.AWAITING_PAYMENT)

    def test_reject_and_withdraw_are_refused_once_money_arrived_and_allowed_after_a_refund(self):
        subscription = self._to_awaiting()
        confirm_payment(
            subscription,
            confirmed_by=self.tenant.user,
            amount_received=Decimal("25.00"),
            received_on=timezone.now().date(),
        )
        expected = MONEY_ALREADY_IN.format(amount=Decimal("25.00"), reference=subscription.reference)
        self.assertEqual(self._refusal(reject, subscription, "Changed our mind"), expected)
        self.assertEqual(self._refusal(withdraw, subscription, "Changed my mind"), expected)
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, SubscriptionStatus.PAID)

        record_refund(subscription, amount=Decimal("25.00"), reference="RTGS-1", notes="Returned in full")
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, SubscriptionStatus.REFUNDED)
        self.assertFalse(subscription.has_money_in)

        reject(subscription, reason="Unwound after the refund")
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, SubscriptionStatus.REJECTED)
        self.assertEqual(subscription.payment_notes, "Unwound after the refund")

    def test_a_dry_subscription_can_still_be_rejected_or_withdrawn(self):
        rejected = self._to_awaiting()
        reject(rejected, reason="Not proceeding")
        rejected.refresh_from_db()
        self.assertEqual(rejected.status, SubscriptionStatus.REJECTED)

        pulled = draft_subscription(self.tenant)
        withdraw(pulled, reason="Investor pulled out")
        pulled.refresh_from_db()
        self.assertEqual(pulled.status, SubscriptionStatus.WITHDRAWN)


class RefundGuardTest(SubscriptionServiceTestCase):
    def _paid(self, amount=Decimal("25.00")):
        subscription = self._to_awaiting()
        confirm_payment(
            subscription,
            confirmed_by=self.tenant.user,
            amount_received=amount,
            received_on=timezone.now().date(),
        )
        subscription.refresh_from_db()
        return subscription

    def test_a_zero_or_negative_refund_returns_nothing_and_is_refused(self):
        subscription = self._paid()
        for amount in (Decimal("0.00"), Decimal("-100.00")):
            with self.subTest(amount=amount):
                self.assertEqual(self._refusal(record_refund, subscription, amount), REFUND_NOT_POSITIVE)
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, SubscriptionStatus.PAID)
        self.assertIsNone(subscription.refunded_at)
        self.assertTrue(subscription.has_money_in)

    def test_a_refund_above_what_arrived_is_refused(self):
        subscription = self._paid()
        self.assertEqual(
            self._refusal(record_refund, subscription, Decimal("2500.00")),
            REFUND_ABOVE_HELD.format(
                amount=Decimal("2500.00"),
                refundable=Decimal("25.00"),
                reference=subscription.reference,
                received=Decimal("25.00"),
                refunded=Decimal("0.00"),
            ),
        )
        subscription.refresh_from_db()
        self.assertIsNone(subscription.refund_amount)
        self.assertEqual(subscription.status, SubscriptionStatus.PAID)

    def test_a_zero_refund_never_opens_the_door_to_a_reject_or_a_withdrawal(self):
        subscription = self._paid()
        self._refusal(record_refund, subscription, Decimal("0.00"))
        subscription.refresh_from_db()
        expected = MONEY_ALREADY_IN.format(amount=Decimal("25.00"), reference=subscription.reference)
        self.assertEqual(self._refusal(reject, subscription, "No longer proceeding"), expected)
        self.assertEqual(self._refusal(withdraw, subscription, "No longer proceeding"), expected)
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, SubscriptionStatus.PAID)

    def test_a_partial_refund_leaves_the_rest_in_and_the_row_still_cannot_close(self):
        subscription = self._paid()
        record_refund(subscription, amount=Decimal("1.00"), reference="RTGS-PART")
        subscription.refresh_from_db()

        self.assertEqual(subscription.status, SubscriptionStatus.REFUNDED)
        self.assertEqual(subscription.money_held, Decimal("24.00"))
        self.assertTrue(subscription.has_money_in)
        self.assertEqual(
            self._refusal(reject, subscription, "No longer proceeding"),
            MONEY_ALREADY_IN.format(amount=Decimal("24.00"), reference=subscription.reference),
        )

    def test_refunds_accumulate_until_every_cent_is_back(self):
        subscription = self._paid()
        record_refund(subscription, amount=Decimal("1.00"), reference="RTGS-1")
        subscription.refresh_from_db()
        self.assertEqual(
            self._refusal(record_refund, subscription, Decimal("24.01")),
            REFUND_ABOVE_HELD.format(
                amount=Decimal("24.01"),
                refundable=Decimal("24.00"),
                reference=subscription.reference,
                received=Decimal("25.00"),
                refunded=Decimal("1.00"),
            ),
        )

        record_refund(subscription, amount=Decimal("24.00"), reference="RTGS-2")
        subscription.refresh_from_db()
        self.assertEqual(subscription.refund_amount, Decimal("25.00"))
        self.assertEqual(subscription.money_held, Decimal("0.00"))
        self.assertFalse(subscription.has_money_in)

        reject(subscription, reason="Unwound once it was all back")
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, SubscriptionStatus.REJECTED)

    def test_a_refund_cannot_be_recorded_against_money_that_never_arrived(self):
        subscription = self._to_awaiting()
        self.assertEqual(
            self._refusal(record_refund, subscription, Decimal("25.00")),
            REFUND_ABOVE_HELD.format(
                amount=Decimal("25.00"),
                refundable=Decimal("0.00"),
                reference=subscription.reference,
                received=Decimal("0.00"),
                refunded=Decimal("0.00"),
            ),
        )
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, SubscriptionStatus.AWAITING_PAYMENT)

    def test_an_overpayment_owed_is_not_yet_money_that_went_back(self):
        subscription = self._paid(amount=Decimal("30.00"))
        self.assertEqual(subscription.refund_amount, Decimal("5.00"))
        self.assertEqual(subscription.refunded_total, Decimal("0.00"))
        self.assertEqual(subscription.money_held, Decimal("30.00"))
        self.assertTrue(subscription.has_money_in)

        record_refund(subscription, amount=Decimal("5.00"), reference="RTGS-OVER")
        subscription.refresh_from_db()
        self.assertEqual(subscription.refund_amount, Decimal("5.00"))
        self.assertEqual(subscription.money_held, Decimal("25.00"))
