from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from web3 import Web3

from offerings.exceptions import SubscriptionRefusedException
from offerings.models import Offering, Subscription, SubscriptionStatus
from offerings.services.subscription import (
    ALREADY_ALLOTTED,
    BATCH_ABOVE_HEADROOM,
    ISSUANCE_ALREADY_CLAIMED,
    NO_REQUEST_TO_RETRY,
    NOT_PAID,
    NOT_RETRYABLE,
    NOTHING_TO_ALLOT,
    allot,
    allot_batch,
    cap_headroom,
    confirm_payment,
    record_refund,
    reject,
    retry_allotment,
    scale_back,
    withdraw,
)
from offerings.tasks.subscription import allot_subscription_task
from offerings.tests.factories import (
    configure_operator,
    draft_subscription,
    eligible_subscriber,
    extra_wallet,
    open_offering,
    paid_subscription,
)
from shared.tests.tenants import make_tenant
from tokens.models import RequestStatus, ShareIssuance, ShareIssuanceRequest

CHAIN_CLIENT = "tokens.services.share_token_service.get_base_chain_client"
DEFER = "offerings.tasks.subscription.allot_subscription_task.defer"
SIGNER = "0x" + "e" * 40


class AllotmentTestCase(TestCase):
    def setUp(self):
        chain = patch(CHAIN_CLIENT).start().return_value
        chain.is_valid_address.return_value = True
        chain.to_checksum_address.side_effect = Web3.to_checksum_address
        chain.get_address_from_private_key.return_value = SIGNER
        self.defer = patch(DEFER).start()
        self.addCleanup(patch.stopall)

        self.tenant = make_tenant("allot")
        configure_operator()
        self.offering = open_offering(self.tenant, target_shares=200, cap_shares=500)
        eligible_subscriber(self.tenant)
        self.operator_user = make_tenant("allot-staff", staff=True).user

    def _cap(self, offering, shares):
        Offering.objects.filter(pk=offering.pk).update(minimum_shares=1, target_shares=shares, cap_shares=shares)
        offering.refresh_from_db()

    def _supply(self, authorized=1000, issued=0):
        service = patch("offerings.services.subscription.ShareTokenService").start().return_value
        service.share_supply.return_value = (authorized, issued)
        service.create_issuance_request.side_effect = _create_request
        return service


def _create_request(token, recipient, amount, user, reason="", issuance_type="additional"):
    return ShareIssuanceRequest.objects.create(
        token=token,
        recipient_address=recipient,
        amount=amount,
        reason=reason,
        issuance_type=issuance_type,
        submitted_by=user,
    )


class AllotOneSubscriptionTest(AllotmentTestCase):
    def test_a_paid_subscription_creates_an_approved_request_and_defers_the_mint(self):
        subscription = paid_subscription(self.tenant, quantity=10)
        request = allot(subscription, self.operator_user, notes="Allotted by the operator")

        subscription.refresh_from_db()
        self.assertEqual(subscription.issuance_request, request)
        self.assertEqual(subscription.status, SubscriptionStatus.PAID)
        self.assertEqual(request.status, RequestStatus.APPROVED)
        self.assertEqual(request.amount, 10)
        self.assertEqual(request.recipient_address, self.tenant.wallet.address)
        self.assertEqual(request.reviewed_by, self.operator_user)
        self.assertEqual(request.review_notes, "Allotted by the operator")
        self.assertEqual(
            self.defer.call_args.kwargs,
            {"subscription_uuid": str(subscription.uuid), "executed_by": self.operator_user.pk},
        )

    def test_allotting_the_same_subscription_twice_refuses_and_creates_one_request(self):
        subscription = paid_subscription(self.tenant, quantity=10)
        request = allot(subscription, self.operator_user)

        with self.assertRaises(SubscriptionRefusedException) as raised:
            allot(subscription, self.operator_user)

        self.assertEqual(str(raised.exception.detail), ALREADY_ALLOTTED.format(uuid=request.pk))
        self.assertEqual(ShareIssuanceRequest.objects.filter(token=self.offering.token).count(), 1)
        self.assertEqual(self.defer.call_count, 1)

    def test_a_subscription_that_is_not_paid_cannot_be_allotted(self):
        subscription = draft_subscription(self.tenant)
        with self.assertRaises(SubscriptionRefusedException) as raised:
            allot(subscription, self.operator_user)
        self.assertEqual(str(raised.exception.detail), NOT_PAID.format(status="draft"))
        self.assertFalse(ShareIssuanceRequest.objects.exists())

    def test_a_subscription_scaled_to_nothing_is_refused_rather_than_minting_zero(self):
        subscription = paid_subscription(self.tenant, quantity=10, allotted=0)
        with self.assertRaises(SubscriptionRefusedException) as raised:
            allot(subscription, self.operator_user)
        self.assertEqual(str(raised.exception.detail), NOTHING_TO_ALLOT)

    def test_a_scaled_back_subscription_mints_the_scaled_amount(self):
        subscription = paid_subscription(self.tenant, quantity=10, allotted=4)
        request = allot(subscription, self.operator_user)
        self.assertEqual(request.amount, 4)

    def test_retry_re_defers_only_while_the_request_is_executable(self):
        subscription = paid_subscription(self.tenant, quantity=10)
        request = allot(subscription, self.operator_user)
        self.defer.reset_mock()

        retry_allotment(subscription, self.operator_user)
        self.assertEqual(self.defer.call_count, 1)

        ShareIssuanceRequest.objects.filter(pk=request.pk).update(status=RequestStatus.EXECUTED)
        subscription.refresh_from_db()
        with self.assertRaises(SubscriptionRefusedException) as raised:
            retry_allotment(subscription, self.operator_user)
        self.assertEqual(str(raised.exception.detail), NOT_RETRYABLE.format(uuid=request.uuid, status="executed"))

    def test_a_failed_request_is_one_click_from_a_retry(self):
        subscription = paid_subscription(self.tenant, quantity=10)
        request = allot(subscription, self.operator_user)
        request.mark_failed("chain timeout")
        subscription.refresh_from_db()

        self.assertTrue(subscription.issuance_request.can_be_executed)
        self.defer.reset_mock()
        retry_allotment(subscription, self.operator_user)
        self.assertEqual(self.defer.call_count, 1)

    def test_a_subscription_with_no_request_has_nothing_to_retry(self):
        subscription = paid_subscription(self.tenant, quantity=10)
        with self.assertRaises(SubscriptionRefusedException) as raised:
            retry_allotment(subscription, self.operator_user)
        self.assertEqual(str(raised.exception.detail), NO_REQUEST_TO_RETRY)


class MoneyOutNeverLeavesSharesOutTest(AllotmentTestCase):
    def _allotted(self, **kwargs):
        subscription = paid_subscription(self.tenant, quantity=10, **kwargs)
        return subscription, allot(subscription, self.operator_user)

    def _claimed(self, request, verb):
        request.refresh_from_db()
        return ISSUANCE_ALREADY_CLAIMED.format(
            uuid=request.uuid, status=request.get_status_display().lower(), verb=verb
        )

    def test_a_refund_before_the_mint_rejects_the_request_so_the_task_mints_nothing(self):
        subscription, request = self._allotted()
        record_refund(subscription, amount=Decimal("25.00"), reference="RTGS-9")

        subscription.refresh_from_db()
        request.refresh_from_db()
        self.assertEqual(subscription.status, SubscriptionStatus.REFUNDED)
        self.assertEqual(request.status, RequestStatus.REJECTED)
        self.assertFalse(request.can_be_executed)
        self.assertIn(str(subscription.reference), request.rejection_reason)

        result = allot_subscription_task.func(subscription_uuid=str(subscription.uuid))
        self.assertFalse(result["success"])
        self.assertIn("Rejected", result["error"])
        self.assertFalse(ShareIssuance.objects.exists())

    def test_a_refund_is_refused_once_the_worker_has_claimed_the_mint(self):
        subscription, request = self._allotted()
        ShareIssuanceRequest.objects.filter(pk=request.pk).update(status=RequestStatus.EXECUTING)

        with self.assertRaises(SubscriptionRefusedException) as raised:
            record_refund(subscription, amount=Decimal("25.00"))
        self.assertEqual(str(raised.exception.detail), self._claimed(request, "A refund"))
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, SubscriptionStatus.PAID)
        self.assertIsNone(subscription.refunded_at)

    def test_a_refund_is_refused_after_the_mint_and_before_the_reconciler_catches_up(self):
        subscription, request = self._allotted()
        ShareIssuanceRequest.objects.filter(pk=request.pk).update(status=RequestStatus.EXECUTED)

        with self.assertRaises(SubscriptionRefusedException) as raised:
            record_refund(subscription, amount=Decimal("25.00"))
        self.assertEqual(str(raised.exception.detail), self._claimed(request, "A refund"))
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, SubscriptionStatus.PAID)

    def test_reject_and_withdraw_are_refused_while_a_mint_stands(self):
        subscription, request = self._allotted()
        ShareIssuanceRequest.objects.filter(pk=request.pk).update(status=RequestStatus.EXECUTED)

        for call, verb in ((reject, "Rejecting it"), (withdraw, "Withdrawing it")):
            with self.subTest(verb=verb):
                with self.assertRaises(SubscriptionRefusedException) as raised:
                    call(subscription, "Unwinding")
                self.assertEqual(str(raised.exception.detail), self._claimed(request, verb))
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, SubscriptionStatus.PAID)

    def test_the_payment_cannot_be_restated_once_the_shares_are_claimed(self):
        subscription, request = self._allotted()
        with self.assertRaises(SubscriptionRefusedException) as raised:
            confirm_payment(
                subscription,
                confirmed_by=self.operator_user,
                amount_received=Decimal("5.00"),
                received_on=timezone.now().date(),
                accept_as_final=True,
            )
        self.assertEqual(str(raised.exception.detail), self._claimed(request, "Restating the payment"))
        subscription.refresh_from_db()
        self.assertEqual(subscription.amount_received, Decimal("25.00"))
        self.assertIsNone(subscription.allotted_quantity)

    def test_a_refunded_subscription_can_be_closed_and_never_retried(self):
        subscription, request = self._allotted()
        record_refund(subscription, amount=Decimal("25.00"))
        subscription.refresh_from_db()

        with self.assertRaises(SubscriptionRefusedException) as raised:
            retry_allotment(subscription, self.operator_user)
        request.refresh_from_db()
        self.assertEqual(str(raised.exception.detail), NOT_RETRYABLE.format(uuid=request.uuid, status="rejected"))

        reject(subscription, reason="Unwound after the refund")
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, SubscriptionStatus.REJECTED)


class BulkAllotmentTest(AllotmentTestCase):
    def _three(self):
        return [
            paid_subscription(self.tenant, quantity=40, wallet=extra_wallet(self.tenant, letter))
            for letter in ("1", "2", "3")
        ]

    def test_a_batch_inside_the_headroom_allots_every_row(self):
        service = self._supply(authorized=1000, issued=0)
        result = allot_batch(self._three(), self.operator_user, service=service)

        self.assertEqual(result, {"allotted": 3, "refusals": []})
        self.assertEqual(ShareIssuanceRequest.objects.count(), 3)
        self.assertEqual(service.share_supply.call_count, 1)

    def test_the_whole_batch_is_refused_when_it_would_pass_the_offering_cap(self):
        rows = self._three()
        self._cap(self.offering, 100)
        service = self._supply(authorized=1000, issued=0)
        result = allot_batch(rows, self.operator_user, service=service)

        self.assertEqual(result["allotted"], 0)
        self.assertEqual(
            result["refusals"],
            [
                BATCH_ABOVE_HEADROOM.format(
                    total=120, symbol=self.offering.token.symbol, room=100, cap_room=100, chain_room=1000
                )
            ],
        )
        self.assertFalse(ShareIssuanceRequest.objects.exists())
        self.assertFalse(Subscription.objects.exclude(issuance_request__isnull=True).exists())

    def test_the_whole_batch_is_refused_when_the_chain_has_less_room_than_the_cap(self):
        service = self._supply(authorized=1000, issued=950)
        result = allot_batch(self._three(), self.operator_user, service=service)

        self.assertEqual(result["allotted"], 0)
        self.assertIn("50 still available", result["refusals"][0])
        self.assertFalse(ShareIssuanceRequest.objects.exists())

    def test_an_earlier_allotment_eats_the_offering_headroom_of_the_next_batch(self):
        first, second, third = self._three()
        self._cap(self.offering, 100)
        service = self._supply(authorized=1000, issued=0)

        self.assertEqual(allot_batch([first, second], self.operator_user, service=service)["allotted"], 2)
        self.assertEqual(cap_headroom(self.offering), 20)

        result = allot_batch([third], self.operator_user, service=service)
        self.assertEqual(result["allotted"], 0)
        self.assertIn("20 left under the offering cap", result["refusals"][0])

    def test_two_offerings_are_grouped_and_judged_separately(self):
        other = make_tenant("second-issuer")
        open_offering(other)
        eligible_subscriber(other)
        mine = paid_subscription(self.tenant, quantity=40)
        theirs = paid_subscription(other, quantity=50)
        self._cap(other.offering, 10)

        service = self._supply(authorized=1000, issued=0)
        result = allot_batch([mine, theirs], self.operator_user, service=service)
        self.assertEqual(result["allotted"], 1)
        self.assertEqual(len(result["refusals"]), 1)
        mine.refresh_from_db()
        theirs.refresh_from_db()
        self.assertIsNotNone(mine.issuance_request_id)
        self.assertIsNone(theirs.issuance_request_id)


class ScaleBackTest(AllotmentTestCase):
    def test_scale_back_is_pro_rata_and_never_raises_a_request(self):
        first = paid_subscription(self.tenant, quantity=60, wallet=extra_wallet(self.tenant, "1"))
        second = paid_subscription(self.tenant, quantity=30, wallet=extra_wallet(self.tenant, "2"))
        second_created = second.created_at
        self._cap(self.offering, 50)

        result = scale_back(self.offering)
        first.refresh_from_db()
        second.refresh_from_db()

        self.assertEqual(result, {"scaled": 2, "requested": 90, "room": 50})
        self.assertEqual(first.allotted_quantity, 33)
        self.assertEqual(second.allotted_quantity, 16)
        self.assertLessEqual(first.allotted_quantity + second.allotted_quantity, 50)
        self.assertLess(first.allotted_quantity, first.quantity)
        self.assertEqual(second.created_at, second_created)

    def test_scale_back_leaves_a_batch_that_already_fits(self):
        first = paid_subscription(self.tenant, quantity=40, wallet=extra_wallet(self.tenant, "1"))
        second = paid_subscription(self.tenant, quantity=30, wallet=extra_wallet(self.tenant, "2"))

        self.assertEqual(scale_back(self.offering), {"scaled": 0, "requested": 70, "room": 500})
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertIsNone(first.allotted_quantity)
        self.assertIsNone(second.allotted_quantity)

    def test_scale_back_never_raises_an_allotment_already_cut_by_a_partial_payment(self):
        partial = paid_subscription(self.tenant, quantity=80, allotted=20, wallet=extra_wallet(self.tenant, "1"))
        self._cap(self.offering, 100)

        self.assertEqual(scale_back(self.offering), {"scaled": 0, "requested": 20, "room": 100})
        partial.refresh_from_db()
        self.assertEqual(partial.allotted_quantity, 20)

    def test_a_scaled_batch_then_fits_inside_the_cap(self):
        rows = [
            paid_subscription(self.tenant, quantity=60, wallet=extra_wallet(self.tenant, "1")),
            paid_subscription(self.tenant, quantity=30, wallet=extra_wallet(self.tenant, "2")),
        ]
        self._cap(self.offering, 50)
        scale_back(self.offering)
        for row in rows:
            row.refresh_from_db()

        service = self._supply(authorized=1000, issued=0)
        self.assertEqual(allot_batch(rows, self.operator_user, service=service)["allotted"], 2)
        self.assertEqual(cap_headroom(self.offering), 1)

    def test_the_amount_due_is_untouched_by_a_scale_back(self):
        subscription = paid_subscription(self.tenant, quantity=60, wallet=extra_wallet(self.tenant, "1"))
        self._cap(self.offering, 50)
        scale_back(self.offering)
        subscription.refresh_from_db()
        self.assertEqual(subscription.amount_due, Decimal("150.00"))
        self.assertEqual(subscription.allotted_quantity, 50)
