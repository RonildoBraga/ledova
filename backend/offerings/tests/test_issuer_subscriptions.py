from rest_framework.test import APITestCase

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
