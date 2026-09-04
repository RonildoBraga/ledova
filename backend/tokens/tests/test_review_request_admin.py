"""Both request admins walk start-review, approve, reject and execute through the shared workflow views."""

from unittest.mock import patch

from django.contrib.admin.sites import site
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from shared.tests.tenants import make_tenant
from tokens.models import CapitalIncreaseRequest, RequestStatus, ShareIssuanceRequest

User = get_user_model()

TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


def url(obj, action):
    args = {"changelist": [], "change": [obj.pk]}.get(action, [obj.uuid])
    return reverse(f"admin:tokens_{obj._meta.model_name}_{action}", args=args)


@override_settings(STORAGES=TEST_STORAGES)
class ReviewRequestAdminTest(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(email="admin@example.test", password="pw-12345678")
        self.client.force_login(self.admin)
        self.tenant = make_tenant("owner")
        self.capital_increase = self.tenant.capital_increase
        self.capital_increase.submit(self.tenant.user)
        self.issuance = ShareIssuanceRequest.objects.create(
            token=self.tenant.deployed_token,
            recipient_address="0x" + "a" * 40,
            recipient_name="Alice",
            amount=10,
            reason="Bonus",
            submitted_by=self.tenant.user,
            submitted_at=timezone.now(),
        )
        self.requests = (self.capital_increase, self.issuance)

    def test_changelist_and_change_pages_render_with_the_review_buttons(self):
        for obj in self.requests:
            with self.subTest(model=obj._meta.model_name):
                self.assertEqual(self.client.get(url(obj, "changelist")).status_code, 200)
                change = self.client.get(url(obj, "change"))
                self.assertEqual(change.status_code, 200)
                self.assertContains(change, url(obj, "start_review"))
                self.assertContains(change, url(obj, "approve"))
                self.assertContains(change, url(obj, "reject"))
                self.assertNotContains(change, url(obj, "execute"))

    def test_start_review_approve_then_execute_defers_one_task(self):
        for obj, step in ((self.capital_increase, "setAuthorizedShares(1100)"), (self.issuance, "mint(0x")):
            with self.subTest(model=obj._meta.model_name):
                started = self.client.get(url(obj, "start_review"))
                self.assertRedirects(started, url(obj, "change"), fetch_redirect_response=False)
                obj.refresh_from_db()
                self.assertEqual((obj.status, obj.reviewed_by), (RequestStatus.UNDER_REVIEW, self.admin))
                self.assertContains(self.client.get(url(obj, "change")), "Review started for")

                page = self.client.get(url(obj, "approve"))
                self.assertContains(page, "Approve Request")
                self.assertContains(page, obj.token.symbol)
                approved = self.client.post(url(obj, "approve"), {"notes": "Looks fine"})
                self.assertRedirects(approved, url(obj, "change"), fetch_redirect_response=False)
                obj.refresh_from_db()
                self.assertEqual((obj.status, obj.review_notes), (RequestStatus.APPROVED, "Looks fine"))
                change = self.client.get(url(obj, "change"))
                self.assertContains(change, "Ready for execution")
                self.assertContains(change, url(obj, "execute"))

                self.assertContains(self.client.get(url(obj, "execute")), step)
                with patch("tokens.admin.review_workflow.execute_review_request_task") as task:
                    executed = self.client.post(url(obj, "execute"))
                self.assertRedirects(executed, url(obj, "change"), fetch_redirect_response=False)
                task.defer.assert_called_once_with(model_label=obj._meta.label, request_uuid=str(obj.uuid))
                self.assertContains(self.client.get(url(obj, "change")), "execution started for")

    def test_reject_needs_a_reason_and_closes_the_request(self):
        for obj in self.requests:
            with self.subTest(model=obj._meta.model_name):
                invalid = self.client.post(url(obj, "reject"), {"reason": ""})
                self.assertContains(invalid, "This field is required.")
                obj.refresh_from_db()
                self.assertEqual(obj.status, RequestStatus.SUBMITTED)

                rejected = self.client.post(url(obj, "reject"), {"reason": "Not this quarter"})
                self.assertRedirects(rejected, url(obj, "change"), fetch_redirect_response=False)
                obj.refresh_from_db()
                self.assertEqual((obj.status, obj.rejection_reason), (RequestStatus.REJECTED, "Not this quarter"))
                self.assertContains(self.client.get(url(obj, "change")), "Request Rejected")

                self.client.get(url(obj, "approve"))
                self.assertContains(
                    self.client.get(url(obj, "change")), "Cannot approve: request status is &#x27;Rejected&#x27;"
                )

    def test_state_guards_redirect_and_failed_requests_offer_a_retry(self):
        draft = CapitalIncreaseRequest.objects.create(
            token=self.tenant.deployed_token,
            additional_shares=5,
            new_authorized_total=1005,
            purpose="Later",
            board_resolution_reference="BOARD-2",
        )
        self.client.get(url(draft, "start_review"))
        self.assertContains(
            self.client.get(url(draft, "change")), "Cannot start review: request status is &#x27;Draft&#x27;"
        )
        self.assertContains(self.client.get(url(draft, "change")), "Awaiting Submission")

        for obj in self.requests:
            with self.subTest(model=obj._meta.model_name):
                refused = self.client.post(url(obj, "execute"))
                self.assertRedirects(refused, url(obj, "change"), fetch_redirect_response=False)
                self.assertContains(
                    self.client.get(url(obj, "change")), "Cannot execute: request status is &#x27;Submitted&#x27;"
                )

                obj.mark_failed("rpc down")
                change = self.client.get(url(obj, "change"))
                self.assertContains(change, "Retry Execute")
                self.assertContains(change, url(obj, "execute"))
                self.assertEqual(self.client.get(url(obj, "execute")).status_code, 200)

    def test_requests_are_deletable_only_in_their_initial_status(self):
        request = RequestFactory().get("/")
        request.user = self.admin
        capital_admin = site._registry[CapitalIncreaseRequest]
        issuance_admin = site._registry[ShareIssuanceRequest]

        self.assertFalse(capital_admin.has_delete_permission(request, self.capital_increase))
        self.assertTrue(issuance_admin.has_delete_permission(request, self.issuance))
        self.assertFalse(capital_admin.has_add_permission(request))

        CapitalIncreaseRequest.objects.filter(pk=self.capital_increase.pk).update(status=RequestStatus.DRAFT)
        self.capital_increase.refresh_from_db()
        self.issuance.approve(self.admin)
        self.assertTrue(capital_admin.has_delete_permission(request, self.capital_increase))
        self.assertFalse(issuance_admin.has_delete_permission(request, self.issuance))
