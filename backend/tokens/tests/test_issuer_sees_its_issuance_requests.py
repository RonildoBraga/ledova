from unittest import skipUnless
from unittest.mock import patch

from django.conf import settings
from django.db import connection
from rest_framework.test import APITestCase

from offerings.models import Subscription
from shared.db.principal import PRINCIPAL_SETTING
from shared.tests.tenants import make_tenant, open_to_investors
from shared.tests.under_the_policies import what_the_policies_admit_to
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

    def test_a_successful_submission_appears_in_the_token_history(self):
        with patch("tokens.services.share_token_service.get_base_chain_client", side_effect=AssertionError("No RPC")):
            response = self.client.post(
                f"/api/v1/tokens/{self.tenant.deployed_token.uuid}/issue/",
                {"recipient": self.tenant.wallet.address, "amount": 10, "reason": "New allocation"},
            )
        self.assertEqual(response.status_code, 201, response.content)
        submitted = response.json()["issuanceRequest"]
        self.assertEqual(submitted["status"], RequestStatus.SUBMITTED)
        listed = self.client.get(f"{BASE}?token={self.tenant.deployed_token.uuid}").json()["results"]
        self.assertEqual(listed[0], submitted)

    def test_the_row_carries_the_status_the_issuer_is_waiting_on(self):
        ShareIssuanceRequest.objects.filter(pk=self.request.pk).update(status=RequestStatus.SUBMITTED)

        row = self.listed()["results"][0]

        self.assertEqual(row["status"], RequestStatus.SUBMITTED)
        self.assertEqual(row["amount"], self.request.amount)
        self.assertEqual(row["recipientAddress"], self.request.recipient_address)

    def test_another_company_s_request_is_not_listed(self):
        foreign = self.a_request(self.stranger)
        body = self.listed()

        self.assertEqual(body["count"], 1)
        self.assertNotIn(str(foreign.uuid), [row["uuid"] for row in body["results"]])

    def test_list_and_detail_keep_operator_notes_private(self):
        ShareIssuanceRequest.objects.filter(pk=self.request.pk).update(
            review_notes="Private provider credentials and reviewer deliberation",
            execution_notes="Execution failed. Operations review is required.",
        )

        for path in (BASE, f"{BASE}{self.request.uuid}/"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                body = response.json()
                row = body["results"][0] if path == BASE else body
                self.assertEqual(row["executionNotes"], "Execution failed. Operations review is required.")
                self.assertNotIn("reviewNotes", row)
                self.assertNotIn(b"Private provider", response.content)

    def test_the_history_endpoint_cannot_change_or_delete_a_request(self):
        detail = f"{BASE}{self.request.uuid}/"
        self.assertEqual(self.client.post(BASE, {}).status_code, 405)
        self.assertEqual(self.client.patch(detail, {"status": "approved"}).status_code, 405)
        self.assertEqual(self.client.delete(detail).status_code, 405)
        self.assertTrue(ShareIssuanceRequest.objects.filter(pk=self.request.pk).exists())

    def test_older_requests_remain_accessible_on_the_next_page(self):
        for _ in range(25):
            self.a_request(self.tenant)
        first = self.listed()
        self.assertEqual(first["count"], 26)
        self.assertEqual(len(first["results"]), 25)
        second = self.client.get(first["next"]).json()
        self.assertEqual([row["uuid"] for row in second["results"]], [str(self.request.uuid)])
        self.assertIsNone(second["next"])

    def test_it_can_be_narrowed_to_one_token(self):
        body = self.client.get(f"{BASE}?token={self.tenant.deployed_token.uuid}").json()

        self.assertEqual([row["uuid"] for row in body["results"]], [str(self.request.uuid)])

    def test_an_anonymous_caller_is_told_nothing(self):
        self.client.force_authenticate(None)

        self.assertIn(self.client.get(BASE).status_code, (401, 403))

    def test_the_visibility_reads_the_owner_column_rather_than_joining_to_the_token(self):
        sql = str(what_the_policies_admit_to(self.tenant.user, ShareIssuanceRequest).query)

        self.assertIn("company_id", sql)
        self.assertNotIn("tokens_sharetoken", sql)

    @skipUnless(connection.vendor == "postgresql", "PostgreSQL request policies")
    def test_subscriber_database_access_does_not_expose_another_issuers_history(self):
        foreign = self.a_request(self.stranger)
        open_to_investors(self.stranger)
        Subscription.objects.create(
            offering=self.stranger.offering,
            user_account=self.tenant.account,
            wallet=self.tenant.wallet,
            submitted_by=self.tenant.user,
            quantity=10,
            price_per_share=self.stranger.offering.price_per_share,
            amount_due=25,
            issuance_request=foreign,
        )
        self.addCleanup(self.restore_role)
        with connection.cursor() as cursor:
            cursor.execute(f"SET ROLE {settings.RLS_ROLES['app']}")
            cursor.execute("SELECT set_config(%s, %s, false)", [PRINCIPAL_SETTING, str(self.tenant.user.pk)])

        self.assertEqual(ShareIssuanceRequest.objects.get(pk=foreign.pk), foreign)
        self.assertEqual(self.client.get(f"{BASE}?token={foreign.token_id}").json()["results"], [])
        self.assertEqual(self.client.get(f"{BASE}{foreign.uuid}/").status_code, 404)
        self.assertEqual(self.listed()["count"], 1)

    def restore_role(self):
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")
            cursor.execute("SELECT set_config(%s, NULL, false)", [PRINCIPAL_SETTING])
