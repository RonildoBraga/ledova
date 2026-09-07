from unittest.mock import patch

from rest_framework.test import APITestCase

from companies.models import Company, CompanyStatus
from offerings.models import Offering, OfferingStatus
from shared.tests.tenants import make_tenant

BASE = "/api/v1/offerings/"

READ_BY_THE_ISSUER_PAGE = {
    "canBeDeleted",
    "canBeEdited",
    "capShares",
    "closeReason",
    "closesAt",
    "exemption",
    "exemptionDisplay",
    "maximumShares",
    "minimumShares",
    "opensAt",
    "priceCurrency",
    "pricePerShare",
    "rejectionReason",
    "status",
    "statusDisplay",
    "targetShares",
    "tokenName",
    "tokenSymbol",
    "uuid",
}


class TheListSendsWhatTheIssuerPageReadsTest(APITestCase):
    def setUp(self):
        patch("offerings.services.offering.send_push_notification").start()
        self.addCleanup(patch.stopall)
        self.tenant = make_tenant("issuer")
        Company.objects.filter(pk=self.tenant.company.pk).update(status=CompanyStatus.ACTIVE)
        self.client.force_authenticate(self.tenant.user)

    def _row(self):
        response = self.client.get(BASE)
        self.assertEqual(response.status_code, 200)
        rows = response.json()
        rows = rows if isinstance(rows, list) else rows["results"]
        self.assertEqual(len(rows), 1)
        return rows[0]

    def test_every_field_the_issuer_page_reads_is_sent(self):
        self.assertEqual(READ_BY_THE_ISSUER_PAGE - set(self._row()), set())

    def test_a_draft_reports_that_it_can_be_edited_so_submit_renders(self):
        Offering.objects.filter(pk=self.tenant.offering.pk).update(status=OfferingStatus.DRAFT)

        self.assertIs(self._row()["canBeEdited"], True)

    def test_a_rejected_offering_carries_the_reason_the_page_shows(self):
        Offering.objects.filter(pk=self.tenant.offering.pk).update(
            status=OfferingStatus.REJECTED, rejection_reason="The exemption does not apply."
        )

        row = self._row()
        self.assertEqual(row["rejectionReason"], "The exemption does not apply.")

    def test_a_rejected_offering_is_editable_again_but_still_not_deletable(self):
        Offering.objects.filter(pk=self.tenant.offering.pk).update(status=OfferingStatus.REJECTED)

        row = self._row()
        self.assertIs(row["canBeEdited"], True)
        self.assertIs(row["canBeDeleted"], False)

    def test_a_draft_is_the_one_state_that_is_both_editable_and_deletable(self):
        Offering.objects.filter(pk=self.tenant.offering.pk).update(status=OfferingStatus.DRAFT)

        row = self._row()
        self.assertIs(row["canBeEdited"], True)
        self.assertIs(row["canBeDeleted"], True)

    def test_an_approved_offering_is_neither(self):
        Offering.objects.filter(pk=self.tenant.offering.pk).update(status=OfferingStatus.APPROVED)

        row = self._row()
        self.assertIs(row["canBeEdited"], False)
        self.assertIs(row["canBeDeleted"], False)

    def test_a_closed_offering_carries_the_close_reason(self):
        Offering.objects.filter(pk=self.tenant.offering.pk).update(
            status=OfferingStatus.CLOSED, close_reason="The window elapsed."
        )

        self.assertEqual(self._row()["closeReason"], "The window elapsed.")
