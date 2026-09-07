from unittest.mock import patch

from rest_framework.test import APITestCase

from companies.models import Company, CompanyStatus
from offerings.models import Offering, OfferingStatus
from offerings.serializers.offering import NOT_EDITABLE
from offerings.services.offering import ALREADY_LIVE
from offerings.views.offering import NOT_DELETABLE
from shared.tests.tenants import make_tenant

BASE = "/api/v1/offerings/"
REASON = "The exemption does not apply to this class."
NOT_EDITABLE_STATUSES = (
    OfferingStatus.SUBMITTED,
    OfferingStatus.UNDER_REVIEW,
    OfferingStatus.APPROVED,
    OfferingStatus.CLOSED,
    OfferingStatus.WITHDRAWN,
)


class ARejectedOfferingIsEditableAgainTest(APITestCase):
    def setUp(self):
        patch("offerings.services.offering.send_push_notification").start()
        self.addCleanup(patch.stopall)
        self.tenant = make_tenant("issuer")
        Company.objects.filter(pk=self.tenant.company.pk).update(status=CompanyStatus.ACTIVE)
        self.client.force_authenticate(self.tenant.user)
        self.offering = self.tenant.offering
        self.detail = f"{BASE}{self.offering.uuid}/"

    def _set(self, status, **fields):
        Offering.objects.filter(pk=self.offering.pk).update(status=status, **fields)
        self.offering.refresh_from_db()

    def _edit(self, summary="Corrected after the review"):
        return self.client.patch(self.detail, {"summary": summary}, format="json")

    def test_a_draft_is_editable(self):
        self._set(OfferingStatus.DRAFT)

        response = self._edit()

        self.assertEqual(response.status_code, 200, response.content)
        self.offering.refresh_from_db()
        self.assertEqual(self.offering.summary, "Corrected after the review")

    def test_a_rejected_offering_is_editable_again(self):
        self._set(OfferingStatus.REJECTED, rejection_reason=REASON)

        response = self._edit()

        self.assertEqual(response.status_code, 200, response.content)
        self.offering.refresh_from_db()
        self.assertEqual(self.offering.summary, "Corrected after the review")

    def test_editing_a_rejected_offering_leaves_it_rejected_until_it_is_resubmitted(self):
        self._set(OfferingStatus.REJECTED, rejection_reason=REASON)

        response = self._edit()

        self.assertEqual(response.status_code, 200, response.content)
        self.offering.refresh_from_db()
        self.assertEqual(self.offering.status, OfferingStatus.REJECTED)

    def test_the_rejection_reason_survives_the_edit_because_it_is_the_only_record_of_it(self):
        self._set(OfferingStatus.REJECTED, rejection_reason=REASON)

        response = self._edit()

        self.assertEqual(response.status_code, 200, response.content)
        self.offering.refresh_from_db()
        self.assertEqual(self.offering.rejection_reason, REASON)

    def test_every_other_status_is_refused_and_the_refusal_says_which_one_it_is(self):
        for status in NOT_EDITABLE_STATUSES:
            with self.subTest(status=status):
                self._set(status)

                response = self._edit()

                self.assertEqual(response.status_code, 400, response.content)
                self.assertIn(
                    NOT_EDITABLE.format(status=self.offering.get_status_display().lower()),
                    str(response.json()),
                )


class ARejectedOfferingIsResubmittedNotRecreatedTest(APITestCase):
    def setUp(self):
        patch("offerings.services.offering.send_push_notification").start()
        self.addCleanup(patch.stopall)
        self.tenant = make_tenant("issuer")
        Company.objects.filter(pk=self.tenant.company.pk).update(status=CompanyStatus.ACTIVE)
        self.client.force_authenticate(self.tenant.user)
        self.offering = self.tenant.offering
        self.detail = f"{BASE}{self.offering.uuid}/"

    def _reject(self):
        Offering.objects.filter(pk=self.offering.pk).update(status=OfferingStatus.REJECTED, rejection_reason=REASON)
        self.offering.refresh_from_db()

    def test_a_rejected_offering_can_be_submitted_again(self):
        self._reject()

        response = self.client.post(f"{self.detail}submit/")

        self.assertEqual(response.status_code, 200, response.content)
        self.offering.refresh_from_db()
        self.assertEqual(self.offering.status, OfferingStatus.SUBMITTED)

    def test_it_goes_from_rejected_to_submitted_without_passing_back_through_draft(self):
        self._reject()

        self.client.post(f"{self.detail}submit/")

        self.offering.refresh_from_db()
        self.assertNotEqual(self.offering.status, OfferingStatus.DRAFT)
        self.assertEqual(self.offering.status, OfferingStatus.SUBMITTED)

    def test_the_reason_is_still_there_while_it_sits_rejected_and_editable(self):
        self._reject()

        self.assertEqual(self.offering.rejection_reason, REASON)

        self.client.patch(self.detail, {"summary": "Corrected"}, format="json")

        self.offering.refresh_from_db()
        self.assertEqual(self.offering.rejection_reason, REASON)

    def test_resubmitting_clears_the_reason_so_an_approval_does_not_carry_it(self):
        self._reject()

        self.client.post(f"{self.detail}submit/")

        self.offering.refresh_from_db()
        self.assertEqual((self.offering.status, self.offering.rejection_reason), (OfferingStatus.SUBMITTED, ""))

    def test_an_offering_approved_after_a_rejection_carries_no_rejection_reason(self):
        self._reject()
        self.client.post(f"{self.detail}submit/")
        self.offering.refresh_from_db()
        self.offering.approve(notes="Fixed on resubmission")

        self.offering.refresh_from_db()
        self.assertEqual((self.offering.status, self.offering.rejection_reason), (OfferingStatus.APPROVED, ""))

    def test_resubmitting_while_another_offering_is_live_is_refused_rather_than_a_constraint_error(self):
        rival = Offering.objects.get(pk=self.offering.pk)
        rival.pk = None
        rival.status = OfferingStatus.APPROVED
        rival.save()
        self._reject()

        response = self.client.post(f"{self.detail}submit/")

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn(ALREADY_LIVE.split("{")[0], str(response.json()))


class DeletingAnOfferingStaysADraftOnlyActionTest(APITestCase):
    def setUp(self):
        patch("offerings.services.offering.send_push_notification").start()
        self.addCleanup(patch.stopall)
        self.tenant = make_tenant("issuer")
        Company.objects.filter(pk=self.tenant.company.pk).update(status=CompanyStatus.ACTIVE)
        self.client.force_authenticate(self.tenant.user)
        self.offering = self.tenant.offering
        self.detail = f"{BASE}{self.offering.uuid}/"

    def test_a_draft_is_deleted(self):
        spare = Offering.objects.get(pk=self.offering.pk)
        spare.pk = None
        spare.status = OfferingStatus.DRAFT
        spare.save()

        response = self.client.delete(f"{BASE}{spare.uuid}/")

        self.assertEqual(response.status_code, 204, response.content)
        self.assertFalse(Offering.objects.filter(pk=spare.pk).exists())

    def test_a_rejected_offering_is_editable_but_not_deletable(self):
        Offering.objects.filter(pk=self.offering.pk).update(status=OfferingStatus.REJECTED)

        response = self.client.delete(self.detail)

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn(NOT_DELETABLE, str(response.json()))
        self.assertTrue(Offering.objects.filter(pk=self.offering.pk).exists())

    def test_the_message_stays_true_because_deletion_did_not_follow_editing(self):
        self.assertEqual(NOT_DELETABLE, "Only a draft offering can be deleted.")
