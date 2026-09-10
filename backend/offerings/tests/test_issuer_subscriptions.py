from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APITestCase

from offerings.models import Subscription
from offerings.tests.factories import (
    configure_operator,
    eligible_subscriber,
    forget_fixture_subscriptions,
    open_offering,
    paid_subscription,
)
from shared.tests.tenants import make_tenant
from tokens.models import (
    IssuanceStatus,
    RequestStatus,
    ShareIssuance,
    ShareIssuanceRequest,
)


class IssuerSubscriptionReadTest(APITestCase):
    def setUp(self):
        self.tenant = make_tenant("issuer")
        forget_fixture_subscriptions()
        configure_operator()
        self.offering = open_offering(self.tenant)
        eligible_subscriber(self.tenant)
        self.subscription = paid_subscription(self.tenant, quantity=10)
        self.client.force_authenticate(self.tenant.user)

    def test_the_issuer_sees_payment_confirmed_and_allotment_pending(self):
        response = self.client.get(f"/api/v1/offerings/{self.offering.uuid}/subscriptions/")

        self.assertEqual(response.status_code, 200)
        row = response.json()["results"][0]
        self.assertEqual(row["uuid"], str(self.subscription.uuid))
        self.assertEqual(row["status"], "paid")
        self.assertEqual(row["investorName"], "issuer owner")
        self.assertEqual(row["amountReceived"], "25.00")
        self.assertEqual(row["allotmentState"], "Not allotted")
        self.assertEqual(row["walletAddress"], self.tenant.wallet.address)

    def test_the_route_is_read_only_and_closed_to_another_tenant(self):
        self.assertEqual(self.client.post(f"/api/v1/offerings/{self.offering.uuid}/subscriptions/").status_code, 405)

        other = make_tenant("outsider")
        self.client.force_authenticate(other.user)
        response = self.client.get(f"/api/v1/offerings/{self.offering.uuid}/subscriptions/")

        self.assertEqual(response.status_code, 404)

    def test_an_allotment_names_the_subscription_that_paid_for_it(self):
        token = self.tenant.deployed_token
        request = ShareIssuanceRequest.objects.create(
            token=token,
            recipient_address=self.tenant.wallet.address,
            amount=10,
            reason="Allotment",
            status=RequestStatus.EXECUTED,
        )
        issuance = ShareIssuance.objects.create(
            token=token,
            recipient_address=self.tenant.wallet.address,
            amount="10",
            status=IssuanceStatus.COMPLETED,
        )
        request.executed_issuance = issuance
        request.save(update_fields=["executed_issuance"])
        self.subscription.issuance_request = request
        self.subscription.save(update_fields=["issuance_request"])

        response = self.client.get(f"/api/v1/tokens/{token.uuid}/issuances/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"][0]["subscriptionReference"], self.subscription.reference)

    def test_an_issuance_with_no_subscription_reports_none(self):
        token = self.tenant.deployed_token
        ShareIssuance.objects.create(
            token=token, recipient_address="0x" + "7" * 40, amount="5", status=IssuanceStatus.COMPLETED
        )

        response = self.client.get(f"/api/v1/tokens/{token.uuid}/issuances/")

        self.assertIsNone(response.json()["results"][0]["subscriptionReference"])

    def test_the_issuer_keeps_other_investors_on_newest_first_pages(self):
        other = make_tenant("subscriber")
        first_created = self.subscription.created_at
        later = []
        for index in range(25):
            subscription = Subscription.objects.create(
                offering=self.offering,
                user_account=other.account,
                wallet=other.wallet,
                submitted_by=other.user,
                quantity=index + 1,
                price_per_share=self.offering.price_per_share,
                amount_due=(index + 1) * self.offering.price_per_share,
            )
            Subscription.objects.filter(pk=subscription.pk).update(
                created_at=first_created + timedelta(seconds=index + 1)
            )
            later.append(str(subscription.uuid))

        path = f"/api/v1/offerings/{self.offering.uuid}/subscriptions/"
        first = self.client.get(path)
        self.assertEqual(first.status_code, 200)
        body = first.json()
        self.assertEqual(body["count"], 26)
        self.assertEqual([row["uuid"] for row in body["results"]], list(reversed(later)))
        self.assertEqual({row["investorName"] for row in body["results"]}, {"subscriber owner"})
        second = self.client.get(body["next"]).json()
        self.assertEqual([row["uuid"] for row in second["results"]], [str(self.subscription.uuid)])
        self.assertIsNone(second["next"])
        self.client.force_authenticate(other.user)
        self.assertEqual(self.client.get(path).status_code, 404)

    def test_issuance_history_keeps_token_status_ordering_and_pagination(self):
        token = self.tenant.deployed_token
        other = make_tenant("other-issuer")
        started = timezone.now()
        completed = []
        for index in range(26):
            issuance = ShareIssuance.objects.create(
                token=token,
                recipient_address=self.tenant.wallet.address,
                amount=str(index + 1),
                status=IssuanceStatus.COMPLETED,
                completed_at=started + timedelta(seconds=index),
            )
            completed.append(str(issuance.uuid))
        ShareIssuance.objects.create(
            token=other.deployed_token,
            recipient_address=other.wallet.address,
            amount="999",
            status=IssuanceStatus.COMPLETED,
            completed_at=started + timedelta(minutes=1),
        )
        ShareIssuance.objects.create(
            token=token, recipient_address=self.tenant.wallet.address, amount="555", status=IssuanceStatus.PENDING
        )

        path = f"/api/v1/tokens/{token.uuid}/issuances/?status=completed"
        first = self.client.get(path)
        self.assertEqual(first.status_code, 200)
        body = first.json()
        self.assertEqual(body["count"], 26)
        self.assertEqual([row["uuid"] for row in body["results"]], list(reversed(completed[1:])))
        self.assertEqual({row["token"] for row in body["results"]}, {str(token.uuid)})
        self.assertEqual(body["results"][0]["amount"], "26")
        second = self.client.get(body["next"]).json()
        self.assertEqual([row["uuid"] for row in second["results"]], [completed[0]])
        self.assertIsNone(second["next"])
        self.client.force_authenticate(other.user)
        self.assertEqual(self.client.get(path).status_code, 404)
