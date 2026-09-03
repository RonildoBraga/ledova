"""The admin deploy button goes through the same ShareTokenService.start_deployment as the API."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from companies.models import Company, CompanyStatus
from shared.tests.tenants import make_tenant
from tokens.models import ShareTokenStatus

User = get_user_model()

TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


@override_settings(STORAGES=TEST_STORAGES)
class ShareTokenAdminDeployTest(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_superuser(email="admin@example.test", password="pw-12345678"))
        self.tenant = make_tenant("owner")
        self.change_url = reverse("admin:tokens_sharetoken_change", args=[self.tenant.token.pk])
        self.deploy_url = reverse("admin:tokens_sharetoken_deploy", args=[self.tenant.token.uuid])

    @patch("tokens.tasks.deploy_share_token_task")
    def test_confirm_page_and_post_start_the_deployment(self, deploy_task):
        Company.objects.filter(pk=self.tenant.company.pk).update(status=CompanyStatus.ACTIVE)

        confirm = self.client.get(self.deploy_url)
        self.assertEqual(confirm.status_code, 200)
        self.assertEqual(confirm.context["primary_wallet"], self.tenant.wallet)

        started = self.client.post(self.deploy_url)
        self.assertRedirects(started, self.change_url, fetch_redirect_response=False)
        self.assertContains(self.client.get(self.change_url), "Deployment started for")
        self.tenant.token.refresh_from_db()
        self.assertEqual(self.tenant.token.status, ShareTokenStatus.DEPLOYING)
        deploy_task.defer.assert_called_once_with(token_uuid=str(self.tenant.token.uuid))

    @patch("tokens.tasks.deploy_share_token_task")
    def test_readiness_guards_redirect_with_the_reason(self, deploy_task):
        for method in (self.client.get, self.client.post):
            response = method(self.deploy_url)
            self.assertRedirects(response, self.change_url, fetch_redirect_response=False)
            change_page = self.client.get(self.change_url)
            self.assertContains(change_page, "Cannot deploy: Company must be active before deploying tokens.")
            self.assertContains(change_page, "⚠ Company must be active before deploying tokens.")

        self.tenant.token.refresh_from_db()
        self.assertEqual(self.tenant.token.status, ShareTokenStatus.DRAFT)
        deploy_task.defer.assert_not_called()
