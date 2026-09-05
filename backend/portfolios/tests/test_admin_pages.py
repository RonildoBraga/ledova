"""Every portfolios ModelAdmin renders; the portfolio changelist counts wallets in the list query."""

from django.contrib import admin
from django.test import TestCase, override_settings
from django.urls import reverse

from shared.tests.tenants import make_tenant

TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


@override_settings(STORAGES=TEST_STORAGES)
class PortfoliosAdminPagesTest(TestCase):
    def setUp(self):
        self.tenant = make_tenant("portfolioadmin", superuser=True)
        self.client.force_login(self.tenant.user)
        self.instances = [self.tenant.portfolio]

    def test_every_portfolios_model_is_registered_and_renders(self):
        registered = {model for model in admin.site._registry if model._meta.app_label == "portfolios"}
        self.assertEqual(registered, {type(instance) for instance in self.instances})

        for instance in self.instances:
            info = (instance._meta.app_label, instance._meta.model_name)
            with self.subTest(model=instance._meta.label):
                self.assertEqual(self.client.get(reverse("admin:%s_%s_changelist" % info)).status_code, 200)
                self.assertEqual(
                    self.client.get(reverse("admin:%s_%s_change" % info, args=[instance.pk])).status_code, 200
                )
        self.assertEqual(self.client.get(reverse("admin:portfolios_portfolio_add")).status_code, 200)

    def test_wallet_count_is_annotated(self):
        self.tenant.portfolio.wallets.add(self.tenant.spare_wallet)
        response = self.client.get(reverse("admin:portfolios_portfolio_changelist"), {"o": "4"})
        self.assertEqual([row.wallet_count for row in response.context["cl"].result_list], [2])
