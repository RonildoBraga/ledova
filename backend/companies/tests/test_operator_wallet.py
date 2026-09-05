"""Company.operator_wallet writers: the company PATCH route and the admin change form."""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from companies.models import Company
from shared.tests.tenants import make_tenant
from wallets.constants import WALLET_VERIFICATION_STATUS_VERIFIED
from wallets.models import Wallet

TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


class OperatorWalletApiTest(APITestCase):
    def setUp(self):
        self.tenant = make_tenant("owner")
        self.other = make_tenant("other")
        self.client.force_authenticate(self.tenant.user)
        self.url = f"/api/v1/companies/{self.tenant.company.uuid}/"
        Company.objects.filter(pk=self.tenant.company.pk).update(operator_wallet=None)

    def _patch(self, wallet):
        return self.client.patch(self.url, {"operatorWallet": wallet}, format="json")

    def test_owner_sets_clears_and_reads_a_verified_evm_wallet(self):
        response = self._patch(str(self.tenant.wallet.uuid))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["operatorWallet"], str(self.tenant.wallet.uuid))
        self.tenant.company.refresh_from_db()
        self.assertEqual(self.tenant.company.operator_wallet, self.tenant.wallet)
        self.assertEqual(self.client.get(self.url).json()["operatorWallet"], str(self.tenant.wallet.uuid))

        cleared = self._patch(None)
        self.assertEqual(cleared.status_code, 200, cleared.content)
        self.tenant.company.refresh_from_db()
        self.assertIsNone(self.tenant.company.operator_wallet)

    def test_unverified_foreign_and_non_evm_wallets_are_rejected(self):
        bitcoin = Wallet.objects.create(
            user_account=self.tenant.account,
            address="tb1q" + "0" * 38,
            chain="bitcoin",
            verification_status=WALLET_VERIFICATION_STATUS_VERIFIED,
        )
        for wallet in (self.tenant.spare_wallet, self.other.wallet, bitcoin):
            with self.subTest(wallet=wallet.chain):
                response = self._patch(str(wallet.uuid))
                self.assertEqual(response.status_code, 400, response.content)
                self.assertIn("operatorWallet", response.json())
        self.tenant.company.refresh_from_db()
        self.assertIsNone(self.tenant.company.operator_wallet)


@override_settings(STORAGES=TEST_STORAGES)
class OperatorWalletAdminTest(TestCase):
    def test_change_form_offers_only_the_owners_verified_evm_wallets(self):
        User = get_user_model()
        self.client.force_login(User.objects.create_superuser(email="admin@example.test", password="pw-12345678"))
        tenant = make_tenant("owner")
        other = make_tenant("other")
        page = self.client.get(reverse("admin:companies_company_change", args=[tenant.company.pk]))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'name="operator_wallet"')
        options = page.context["adminform"].form.fields["operator_wallet"].queryset
        self.assertEqual(list(options), [tenant.wallet])
        self.assertNotIn(tenant.spare_wallet, options)
        self.assertNotIn(other.wallet, options)

        add_page = self.client.get(reverse("admin:companies_company_add"))
        self.assertEqual(add_page.status_code, 200)
        self.assertFalse(add_page.context["adminform"].form.fields["operator_wallet"].queryset.exists())
