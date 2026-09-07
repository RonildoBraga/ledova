from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework.test import APITestCase

from assets.models import AssetChainDeployment
from offerings.models import (
    Offering,
    OfferingStatus,
    SettlementRail,
    Subscription,
    SubscriptionStatus,
)
from offerings.services.subscription import accept, confirm_payment, issue_instruction, submit
from offerings.tests.factories import (
    configure_operator,
    draft_subscription,
    eligible_subscriber,
    forget_fixture_subscriptions,
    open_offering,
)
from shared.tests.tenants import make_tenant
from users.models import InvestorClassification

BASE = "/api/v1/subscriptions/"


class SubscriptionApiTest(APITestCase):
    def setUp(self):
        self.tenant = make_tenant("api")
        forget_fixture_subscriptions()
        self.stablecoin = self.tenant.refs.stablecoin
        configure_operator(stablecoin=self.stablecoin)
        self.offering = open_offering(self.tenant, stablecoin=self.stablecoin)
        eligible_subscriber(self.tenant)
        self.client.force_authenticate(self.tenant.user)

    def _payload(self, **overrides):
        return {
            "offering": str(self.offering.uuid),
            "userAccount": str(self.tenant.account.uuid),
            "wallet": str(self.tenant.wallet.uuid),
            "quantity": 10,
            **overrides,
        }

    def test_an_eligible_investor_creates_a_draft_with_the_price_snapshotted(self):
        response = self.client.post(BASE, self._payload(), format="json")
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()
        self.assertEqual(body["status"], SubscriptionStatus.DRAFT)
        self.assertEqual(body["quantity"], 10)
        self.assertEqual(body["pricePerShare"], "2.50")
        self.assertEqual(body["amountDue"], "25.00")
        self.assertIsNone(body["paymentInstruction"])
        self.assertEqual(Subscription.objects.count(), 1)

    def test_an_ineligible_investor_cannot_name_the_offering(self):
        InvestorClassification.objects.filter(user_account=self.tenant.account).update(
            expires_at=timezone.now() - timedelta(days=1)
        )
        response = self.client.post(BASE, self._payload(), format="json")
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("offering", response.json())
        self.assertFalse(Subscription.objects.exists())

    def test_an_offering_that_has_not_opened_is_not_a_choice(self):
        Offering.objects.filter(pk=self.offering.pk).update(opens_at=timezone.now() + timedelta(days=2))
        response = self.client.post(BASE, self._payload(), format="json")
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("offering", response.json())

    def test_a_submitted_but_unapproved_offering_is_not_a_choice(self):
        Offering.objects.filter(pk=self.offering.pk).update(status=OfferingStatus.SUBMITTED)
        response = self.client.post(BASE, self._payload(), format="json")
        self.assertEqual(response.status_code, 400, response.content)

    def test_a_wallet_that_is_not_the_callers_is_refused(self):
        stranger = make_tenant("api-stranger")
        response = self.client.post(BASE, self._payload(wallet=str(stranger.wallet.uuid)), format="json")
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("wallet", response.json())

    def test_an_unverified_wallet_is_not_a_choice(self):
        response = self.client.post(BASE, self._payload(wallet=str(self.tenant.spare_wallet.uuid)), format="json")
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("wallet", response.json())

    def test_a_quantity_below_the_offering_minimum_is_refused_by_the_service(self):
        response = self.client.post(BASE, self._payload(quantity=1), format="json")
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("asks for at least 10 shares", str(response.json()))

    def test_the_list_carries_only_the_callers_subscriptions(self):
        other = make_tenant("api-other")
        forget_fixture_subscriptions()
        mine = draft_subscription(self.tenant)
        open_offering(other)
        eligible_subscriber(other)
        draft_subscription(other)

        response = self.client.get(BASE)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual([row["uuid"] for row in response.json()["results"]], [str(mine.uuid)])

    def test_the_detail_nests_the_bank_instruction_read_only(self):
        subscription = draft_subscription(self.tenant)
        submit(subscription, submitted_by=self.tenant.user)
        accept(subscription)
        issue_instruction(subscription, rail=SettlementRail.BANK_TRANSFER)

        body = self.client.get(f"{BASE}{subscription.uuid}/").json()
        instruction = body["paymentInstruction"]
        self.assertEqual(instruction["rail"], SettlementRail.BANK_TRANSFER)
        self.assertEqual(instruction["reference"], subscription.reference)
        self.assertEqual(instruction["bankBsb"], "062000")
        self.assertEqual(instruction["amountDue"], "25.00")
        self.assertEqual(body["status"], SubscriptionStatus.AWAITING_PAYMENT)

    def test_the_detail_nests_the_stablecoin_instruction(self):
        subscription = draft_subscription(self.tenant)
        submit(subscription, submitted_by=self.tenant.user)
        accept(subscription)
        issue_instruction(subscription, rail=SettlementRail.STABLECOIN, settlement_asset=self.stablecoin)

        instruction = self.client.get(f"{BASE}{subscription.uuid}/").json()["paymentInstruction"]
        self.assertEqual(instruction["contractAddress"], "0x" + "5" * 40)
        self.assertEqual(instruction["decimals"], 2)
        self.assertEqual(instruction["settlementAmount"], "2500")

    def test_a_paid_subscription_stops_asking_for_money(self):
        subscription = draft_subscription(self.tenant)
        submit(subscription, submitted_by=self.tenant.user)
        accept(subscription)
        issue_instruction(subscription, rail=SettlementRail.BANK_TRANSFER)
        confirm_payment(
            subscription,
            confirmed_by=self.tenant.user,
            amount_received=subscription.amount_due,
            received_on=timezone.now().date(),
        )

        body = self.client.get(f"{BASE}{subscription.uuid}/").json()

        self.assertEqual(body["status"], SubscriptionStatus.PAID)
        self.assertIsNone(body["paymentInstruction"])
        self.assertEqual(body["reference"], subscription.reference)

    def test_a_part_payment_that_leaves_it_awaiting_keeps_the_instruction(self):
        subscription = draft_subscription(self.tenant)
        submit(subscription, submitted_by=self.tenant.user)
        accept(subscription)
        issue_instruction(subscription, rail=SettlementRail.BANK_TRANSFER)
        confirm_payment(
            subscription,
            confirmed_by=self.tenant.user,
            amount_received=Decimal("1.00"),
            received_on=timezone.now().date(),
        )

        body = self.client.get(f"{BASE}{subscription.uuid}/").json()

        self.assertEqual(body["status"], SubscriptionStatus.AWAITING_PAYMENT)
        self.assertIsNotNone(body["paymentInstruction"])

    def test_only_an_awaiting_subscription_carries_an_instruction(self):
        subscription = draft_subscription(self.tenant)
        submit(subscription, submitted_by=self.tenant.user)
        accept(subscription)
        issue_instruction(subscription, rail=SettlementRail.BANK_TRANSFER)
        detail = f"{BASE}{subscription.uuid}/"

        self.assertIsNotNone(self.client.get(detail).json()["paymentInstruction"])

        for status in (SubscriptionStatus.PAID, SubscriptionStatus.ALLOTTED, SubscriptionStatus.REFUNDED):
            with self.subTest(status=status):
                Subscription.objects.filter(pk=subscription.pk).update(status=status)

                self.assertIsNone(self.client.get(detail).json()["paymentInstruction"])

    def test_a_deployment_withdrawn_after_the_instruction_leaves_the_detail_readable(self):
        subscription = draft_subscription(self.tenant)
        submit(subscription, submitted_by=self.tenant.user)
        accept(subscription)
        issue_instruction(subscription, rail=SettlementRail.STABLECOIN, settlement_asset=self.stablecoin)
        AssetChainDeployment.objects.filter(asset=self.stablecoin, chain="base").update(is_active=False)

        response = self.client.get(f"{BASE}{subscription.uuid}/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIsNone(response.json()["paymentInstruction"])
        self.assertEqual(response.json()["reference"], subscription.reference)

    def test_submit_moves_the_row_and_withdraw_closes_it(self):
        subscription = draft_subscription(self.tenant)
        submitted = self.client.post(f"{BASE}{subscription.uuid}/submit/", {}, format="json")
        self.assertEqual(submitted.status_code, 200, submitted.content)
        self.assertEqual(submitted.json()["status"], SubscriptionStatus.SUBMITTED)

        pulled = self.client.post(f"{BASE}{subscription.uuid}/withdraw/", {"reason": "Changed my mind"}, format="json")
        self.assertEqual(pulled.status_code, 200, pulled.content)
        self.assertEqual(pulled.json()["status"], SubscriptionStatus.WITHDRAWN)

    def test_withdraw_is_refused_once_money_is_recorded(self):
        subscription = draft_subscription(self.tenant)
        Subscription.objects.filter(pk=subscription.pk).update(
            status=SubscriptionStatus.PAID, amount_received=Decimal("25.00")
        )
        response = self.client.post(f"{BASE}{subscription.uuid}/withdraw/", {}, format="json")
        self.assertEqual(response.status_code, 400, response.content)
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, SubscriptionStatus.PAID)

    def test_there_is_no_operator_write_surface_on_the_api(self):
        subscription = draft_subscription(self.tenant)
        detail = f"{BASE}{subscription.uuid}/"
        self.assertEqual(self.client.put(detail, {}, format="json").status_code, 405)
        self.assertEqual(self.client.patch(detail, {}, format="json").status_code, 405)
        self.assertEqual(self.client.delete(detail).status_code, 405)
        for verb in ("accept", "confirm-payment", "allot", "reject"):
            self.assertEqual(self.client.post(f"{detail}{verb}/", {}, format="json").status_code, 404)

    def test_an_anonymous_caller_is_refused(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(BASE).status_code, 401)
        self.assertEqual(self.client.post(BASE, self._payload(), format="json").status_code, 401)


class SubscriptionSurvivesDeletionTest(APITestCase):
    def setUp(self):
        self.tenant = make_tenant("protect")
        forget_fixture_subscriptions()
        configure_operator()
        self.offering = open_offering(self.tenant)
        eligible_subscriber(self.tenant)
        self.subscription = draft_subscription(self.tenant)
        self.client.force_authenticate(self.tenant.user)

    def test_deleting_the_offering_that_carries_a_subscription_is_refused(self):
        Offering.objects.filter(pk=self.offering.pk).update(status=OfferingStatus.DRAFT)
        response = self.client.delete(f"/api/v1/offerings/{self.offering.uuid}/")
        self.assertEqual(response.status_code, 409, response.content)
        self.assertTrue(Subscription.objects.filter(pk=self.subscription.pk).exists())
        self.assertTrue(Offering.objects.filter(pk=self.offering.pk).exists())

    def test_deleting_the_company_behind_a_subscription_is_refused(self):
        response = self.client.delete(f"/api/v1/companies/{self.tenant.company.uuid}/")
        self.assertEqual(response.status_code, 409, response.content)
        self.assertIn("cannot be deleted", response.json()["detail"])
        self.assertTrue(Subscription.objects.filter(pk=self.subscription.pk).exists())
