from unittest.mock import patch

from django.utils import timezone
from rest_framework.test import APITestCase

from companies.models import Company, CompanyStatus
from offerings.models import Offering, OfferingStatus
from offerings.services.offering import ALREADY_LIVE
from shared.tests.tenants import make_tenant

BASE = "/api/v1/offerings/"
STAFF_ACTIONS = ("approve", "reject", "close", "start-review", "start_review")

PAYLOAD = {
    "exemption": "s708_11_professional",
    "pricePerShare": "3.00",
    "minimumShares": 5,
    "targetShares": 40,
    "capShares": 80,
    "opensAt": "2027-03-01T00:00:00Z",
    "closesAt": "2027-04-01T00:00:00Z",
    "summary": "Second tranche",
    "useOfProceeds": "Plant",
}


class OfferingApiTest(APITestCase):
    def setUp(self):
        patch("offerings.services.offering.send_push_notification").start()
        self.addCleanup(patch.stopall)
        self.tenant = make_tenant("issuer")
        self.other = make_tenant("outsider")
        Company.objects.filter(pk=self.tenant.company.pk).update(status=CompanyStatus.ACTIVE)
        self.client.force_authenticate(self.tenant.user)

    def _detail(self, offering=None):
        return f"{BASE}{(offering or self.tenant.offering).uuid}/"

    def test_no_staff_action_is_routed_on_the_api(self):
        for action in STAFF_ACTIONS:
            for method in ("post", "get", "put", "patch"):
                with self.subTest(action=action, method=method):
                    response = getattr(self.client, method)(f"{self._detail()}{action}/", {}, format="json")
                    self.assertIn(response.status_code, (404, 405), f"{method} {action}: {response.status_code}")

    def test_the_issuer_creates_submits_and_withdraws(self):
        created = self.client.post(BASE, {"token": str(self.tenant.token.uuid), **PAYLOAD}, format="json")
        self.assertEqual(created.status_code, 201, created.content)
        uuid = created.json()["uuid"]
        self.assertEqual(created.json()["status"], "draft")

        withdrawn = self.client.post(f"{BASE}{uuid}/withdraw/", {"reason": "Not yet"}, format="json")
        self.assertEqual(withdrawn.status_code, 200, withdrawn.content)
        self.assertEqual(withdrawn.json()["status"], "withdrawn")

        submitted = self.client.post(f"{self._detail()}submit/", {}, format="json")
        self.assertEqual(submitted.status_code, 200, submitted.content)
        self.assertEqual(submitted.json()["status"], "submitted")

    def test_a_second_tranche_while_one_is_live_is_refused_not_a_server_error(self):
        first = self.client.post(f"{self._detail()}submit/", {}, format="json")
        self.assertEqual(first.status_code, 200, first.content)

        created = self.client.post(BASE, {"token": str(self.tenant.deployed_token.uuid), **PAYLOAD}, format="json")
        self.assertEqual(created.status_code, 201, created.content)
        second = self.client.post(f"{BASE}{created.json()['uuid']}/submit/", {}, format="json")

        self.assertEqual(second.status_code, 400, second.content)
        self.tenant.offering.refresh_from_db()
        self.assertEqual(
            second.json()["detail"],
            ALREADY_LIVE.format(
                symbol=self.tenant.deployed_token.symbol,
                status="submitted for review",
                opens=self.tenant.offering.opens_at.date().isoformat(),
            ),
        )
        self.assertEqual(Offering.objects.get(uuid=created.json()["uuid"]).status, OfferingStatus.DRAFT)

    def test_withdrawing_a_rejected_offering_preserves_the_operator_review(self):
        reviewed_at = timezone.now()
        offering = self.tenant.offering
        Offering.objects.filter(pk=offering.pk).update(
            status=OfferingStatus.REJECTED,
            rejection_reason="The evidence does not support this exemption.",
            reviewed_by=self.other.user,
            reviewed_at=reviewed_at,
            review_notes="Evidence reviewed.",
        )
        response = self.client.post(f"{self._detail()}withdraw/", {"reason": "No longer proceeding"}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        offering.refresh_from_db()
        self.assertEqual(offering.status, OfferingStatus.WITHDRAWN)
        self.assertEqual(offering.close_reason, "No longer proceeding")
        self.assertIsNotNone(offering.closed_at)
        self.assertEqual(offering.rejection_reason, "The evidence does not support this exemption.")
        self.assertEqual(offering.reviewed_by, self.other.user)
        self.assertEqual(offering.reviewed_at, reviewed_at)
        self.assertEqual(offering.review_notes, "Evidence reviewed.")
        self.assertFalse(response.json()["canBeEdited"])
        self.assertFalse(response.json()["canBeDeleted"])
        self.assertEqual(self.client.post(f"{self._detail()}withdraw/").status_code, 400)
        self.assertEqual(self.client.post(f"{self._detail()}submit/").status_code, 400)
        self.assertEqual(self.client.delete(self._detail()).status_code, 400)

    def test_another_issuer_cannot_withdraw_the_rejected_offering(self):
        Offering.objects.filter(pk=self.other.offering.pk).update(status=OfferingStatus.REJECTED)
        response = self.client.post(f"{self._detail(self.other.offering)}withdraw/")
        self.assertEqual(response.status_code, 404)
        self.other.offering.refresh_from_db()
        self.assertEqual(self.other.offering.status, OfferingStatus.REJECTED)

    def test_a_foreign_share_class_cannot_be_offered(self):
        response = self.client.post(BASE, {"token": str(self.other.deployed_token.uuid), **PAYLOAD}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("token", response.json())

    def test_a_foreign_offering_is_not_found(self):
        self.assertEqual(self.client.get(self._detail(self.other.offering)).status_code, 404)
        self.assertEqual(self.client.delete(self._detail(self.other.offering)).status_code, 404)

    def test_a_submitted_offering_can_no_longer_be_edited_or_deleted(self):
        Offering.objects.filter(pk=self.tenant.offering.pk).update(status=OfferingStatus.SUBMITTED)
        patched = self.client.patch(self._detail(), {"summary": "Changed"}, format="json")
        self.assertEqual(patched.status_code, 400, patched.content)
        deleted = self.client.delete(self._detail())
        self.assertEqual(deleted.status_code, 400, deleted.content)

    def test_the_list_shows_only_the_issuers_own_offerings(self):
        response = self.client.get(BASE)
        self.assertEqual({row["uuid"] for row in response.json()["results"]}, {str(self.tenant.offering.uuid)})

    def test_the_settlement_asset_choices_are_the_operators_supported_assets(self):
        response = self.client.post(
            BASE,
            {
                "token": str(self.tenant.token.uuid),
                "settlementAssets": [str(self.tenant.refs.stablecoin.uuid)],
                **PAYLOAD,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("settlementAssets", response.json())
