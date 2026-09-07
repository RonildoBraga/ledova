from rest_framework.test import APITestCase

from shared.tests.tenants import make_tenant
from tokens.models import RequestStatus, ShareIssuanceRequest

BASE = "/api/v1/tokens/issuance-requests/"


class AnIssuerCanSeeTheRequestItMadeTest(APITestCase):

    def setUp(self):
        self.tenant = make_tenant("issuer")
        self.stranger = make_tenant("stranger")
        self.request = self.a_request(self.tenant)
        self.client.force_authenticate(self.tenant.user)

    @staticmethod
    def a_request(tenant):
        return ShareIssuanceRequest.objects.create(
            token=tenant.deployed_token,
            recipient_address="0x" + "b" * 40,
            amount=10000,
            reason="Founder allocation",
            submitted_by=tenant.user,
        )

    def listed(self):
        return self.client.get(BASE).json()

    def test_the_request_it_made_is_listed(self):
        response = self.client.get(BASE)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual([row["uuid"] for row in response.json()["results"]], [str(self.request.uuid)])

    def test_the_row_carries_the_status_the_issuer_is_waiting_on(self):
        ShareIssuanceRequest.objects.filter(pk=self.request.pk).update(status=RequestStatus.SUBMITTED)

        row = self.listed()["results"][0]

        self.assertEqual(row["status"], RequestStatus.SUBMITTED)
        self.assertEqual(row["amount"], self.request.amount)
        self.assertEqual(row["recipientAddress"], self.request.recipient_address)

    def test_another_company_s_request_is_not_listed(self):
        body = self.listed()

        self.assertEqual(body["count"], 1)
        self.assertNotIn(str(self.a_request(self.stranger).uuid), [row["uuid"] for row in body["results"]])

    def test_it_can_be_narrowed_to_one_token(self):
        body = self.client.get(f"{BASE}?token={self.tenant.deployed_token.uuid}").json()

        self.assertEqual([row["uuid"] for row in body["results"]], [str(self.request.uuid)])

    def test_an_anonymous_caller_is_told_nothing(self):
        self.client.force_authenticate(None)

        self.assertIn(self.client.get(BASE).status_code, (401, 403))

    def test_the_visibility_reads_the_owner_column_rather_than_joining_to_the_token(self):
        sql = str(ShareIssuanceRequest.objects.visible_to_user(self.tenant.user).query)

        self.assertIn("company_id", sql)
        self.assertNotIn("tokens_sharetoken", sql)
