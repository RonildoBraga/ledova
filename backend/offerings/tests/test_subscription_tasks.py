from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone
from web3 import Web3

from offerings.models import Subscription, SubscriptionStatus
from offerings.services.subscription import allot
from offerings.tasks import (
    allot_subscription_task,
    expire_unpaid_subscriptions,
    reconcile_subscriptions,
)
from offerings.tasks.subscription import NO_ISSUANCE_REQUEST, SUBSCRIPTION_NOT_FOUND
from offerings.tests.factories import (
    configure_operator,
    draft_subscription,
    eligible_subscriber,
    extra_wallet,
    open_offering,
    paid_subscription,
)
from shared.tests.tenants import make_tenant
from tokens.models import IssuanceStatus, RequestStatus, ShareIssuance
from tokens.services import ShareTokenService

CHAIN_CLIENT = "tokens.services.share_token_service.get_base_chain_client"
WHITELISTED = "tokens.services.share_token_service.ShareTokenService.is_recipient_whitelisted"
SUPPLY = "tokens.services.share_token_service.ShareTokenService.share_supply"
DEFER = "offerings.tasks.subscription.allot_subscription_task.defer"
SIGNER = "0x" + "e" * 40
MINT = {"tx_hash": "0xmint", "block_number": 7, "gas_used": 21000}


@override_settings(BLOCKCHAIN_OPERATOR_KEY="0xkey")
class SubscriptionTaskTest(TestCase):
    def setUp(self):
        chain = patch(CHAIN_CLIENT).start().return_value
        chain.is_valid_address.return_value = True
        chain.to_checksum_address.side_effect = Web3.to_checksum_address
        chain.get_address_from_private_key.return_value = SIGNER
        chain.load_contract.return_value.functions.paused.return_value.call.return_value = False
        patch(WHITELISTED, return_value=True).start()
        patch(SUPPLY, return_value=(1000, 0)).start()
        patch("wallets.services.holdings.sync_holding").start()
        self.defer = patch(DEFER).start()
        self.addCleanup(patch.stopall)

        self.tenant = make_tenant("tasks")
        configure_operator()
        self.offering = open_offering(self.tenant, target_shares=200, cap_shares=500)
        eligible_subscriber(self.tenant)
        self.operator_user = make_tenant("tasks-staff", staff=True).user

    def _allotted(self, quantity=10, wallet=None):
        subscription = paid_subscription(self.tenant, quantity=quantity, wallet=wallet)
        allot(subscription, self.operator_user)
        subscription.refresh_from_db()
        return subscription

    def test_the_task_mints_once_and_mirrors_the_subscription_to_allotted(self):
        subscription = self._allotted()
        with patch.object(ShareTokenService, "_mint_to", return_value=MINT) as mint:
            result = allot_subscription_task(str(subscription.uuid), executed_by=self.operator_user.pk)

        self.assertTrue(result["success"], result)
        self.assertEqual(mint.call_count, 1)
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, SubscriptionStatus.ALLOTTED)
        self.assertEqual(subscription.issuance_request.status, RequestStatus.EXECUTED)
        self.assertEqual(ShareIssuance.objects.count(), 1)

    def test_running_the_task_twice_mints_once(self):
        subscription = self._allotted()
        with patch.object(ShareTokenService, "_mint_to", return_value=MINT) as mint:
            first = allot_subscription_task(str(subscription.uuid), executed_by=self.operator_user.pk)
            second = allot_subscription_task(str(subscription.uuid), executed_by=self.operator_user.pk)

        self.assertTrue(first["success"], first)
        self.assertFalse(second["success"], second)
        self.assertEqual(mint.call_count, 1)
        self.assertEqual(ShareIssuance.objects.count(), 1)
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, SubscriptionStatus.ALLOTTED)

    def test_a_missing_row_or_an_unlinked_subscription_is_reported_not_raised(self):
        self.assertEqual(
            allot_subscription_task("00000000-0000-0000-0000-000000000000"),
            {"success": False, "error": SUBSCRIPTION_NOT_FOUND},
        )
        unlinked = paid_subscription(self.tenant)
        self.assertEqual(
            allot_subscription_task(str(unlinked.uuid)),
            {"success": False, "error": NO_ISSUANCE_REQUEST},
        )

    def test_a_failing_mint_leaves_the_request_re_executable_and_the_row_paid(self):
        subscription = self._allotted()
        with patch.object(ShareTokenService, "_mint_to", side_effect=RuntimeError("rpc down")):
            with self.assertRaisesMessage(RuntimeError, "rpc down"):
                allot_subscription_task(str(subscription.uuid), executed_by=self.operator_user.pk)

        subscription.refresh_from_db()
        self.assertEqual(subscription.status, SubscriptionStatus.PAID)
        self.assertEqual(subscription.issuance_request.status, RequestStatus.FAILED)
        self.assertTrue(subscription.issuance_request.can_be_executed)
        self.assertEqual(ShareIssuance.objects.get().status, IssuanceStatus.FAILED)

        with patch.object(ShareTokenService, "_mint_to", return_value=MINT):
            retried = allot_subscription_task(str(subscription.uuid), executed_by=self.operator_user.pk)

        self.assertTrue(retried["success"], retried)
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, SubscriptionStatus.ALLOTTED)
        self.assertEqual(ShareIssuance.objects.count(), 1)

    def test_reconcile_flips_a_paid_row_whose_request_reached_executed_and_touches_nothing_else(self):
        mirrored = self._allotted(wallet=extra_wallet(self.tenant, "1"))
        with patch.object(ShareTokenService, "_mint_to", return_value=MINT):
            with patch("offerings.tasks.subscription._mirror_allotted", return_value=False):
                allot_subscription_task(str(mirrored.uuid), executed_by=self.operator_user.pk)

        mirrored.refresh_from_db()
        self.assertEqual(mirrored.status, SubscriptionStatus.PAID)
        self.assertEqual(mirrored.issuance_request.status, RequestStatus.EXECUTED)

        untouched_paid = paid_subscription(self.tenant, wallet=extra_wallet(self.tenant, "2"))
        untouched_draft = draft_subscription(self.tenant, wallet=extra_wallet(self.tenant, "3"))
        pending = self._allotted(wallet=extra_wallet(self.tenant, "4"))

        self.assertEqual(reconcile_subscriptions(), {"flipped": 1})

        mirrored.refresh_from_db()
        untouched_paid.refresh_from_db()
        untouched_draft.refresh_from_db()
        pending.refresh_from_db()
        self.assertEqual(mirrored.status, SubscriptionStatus.ALLOTTED)
        self.assertEqual(untouched_paid.status, SubscriptionStatus.PAID)
        self.assertEqual(untouched_draft.status, SubscriptionStatus.DRAFT)
        self.assertEqual(pending.status, SubscriptionStatus.PAID)

        self.assertEqual(reconcile_subscriptions(), {"flipped": 0})

    def test_expiry_only_touches_a_row_with_no_payment_recorded(self):
        overdue = draft_subscription(self.tenant, wallet=extra_wallet(self.tenant, "1"))
        part_paid = draft_subscription(self.tenant, wallet=extra_wallet(self.tenant, "2"))
        in_window = draft_subscription(self.tenant, wallet=extra_wallet(self.tenant, "3"))
        past = timezone.now() - timedelta(days=1)

        Subscription.objects.filter(pk=overdue.pk).update(
            status=SubscriptionStatus.AWAITING_PAYMENT, payment_due_at=past
        )
        Subscription.objects.filter(pk=part_paid.pk).update(
            status=SubscriptionStatus.AWAITING_PAYMENT, payment_due_at=past, amount_received=Decimal("1.00")
        )
        Subscription.objects.filter(pk=in_window.pk).update(
            status=SubscriptionStatus.AWAITING_PAYMENT, payment_due_at=timezone.now() + timedelta(days=1)
        )

        self.assertEqual(expire_unpaid_subscriptions(), {"expired": 1})

        overdue.refresh_from_db()
        part_paid.refresh_from_db()
        in_window.refresh_from_db()
        self.assertEqual(overdue.status, SubscriptionStatus.REJECTED)
        self.assertIn("Payment was not received", overdue.payment_notes)
        self.assertEqual(part_paid.status, SubscriptionStatus.AWAITING_PAYMENT)
        self.assertEqual(in_window.status, SubscriptionStatus.AWAITING_PAYMENT)

    def test_expiry_leaves_a_paid_row_alone_even_past_its_due_date(self):
        paid = paid_subscription(self.tenant)
        Subscription.objects.filter(pk=paid.pk).update(payment_due_at=timezone.now() - timedelta(days=5))
        self.assertEqual(expire_unpaid_subscriptions(), {"expired": 0})
        paid.refresh_from_db()
        self.assertEqual(paid.status, SubscriptionStatus.PAID)
