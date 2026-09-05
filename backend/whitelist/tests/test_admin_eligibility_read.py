from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from users.tests.factories import make_investor, verified_classification
from wallets.models import Wallet
from whitelist.models import WhitelistEntry

User = get_user_model()

TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


@override_settings(STORAGES=TEST_STORAGES)
class WhitelistAdminEligibilityReadTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_superuser(email="wl-admin@example.test", password="pw-12345678")
        self.reviewer = User.objects.create_user(email="wl-reviewer@example.test", password="pw-12345678")
        self.client.force_login(self.admin)
        self.changelist = reverse("admin:whitelist_whitelistentry_changelist")
        self.add_url = reverse("admin:whitelist_whitelistentry_add")

    def _entry(self, label, address):
        _, account = make_investor(label)
        wallet = Wallet.objects.create(user_account=account, address=address, chain="base")
        return account, WhitelistEntry.objects.create(wallet=wallet)

    def test_the_changelist_names_the_reason_an_account_is_not_eligible(self):
        self._entry("wl-ineligible", "0x" + "1" * 40)

        response = self.client.get(self.changelist)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "no_live_classification")

    def test_the_changelist_marks_an_eligible_account(self):
        account, _ = self._entry("wl-eligible", "0x" + "2" * 40)
        verified_classification(account, self.reviewer)

        response = self.client.get(self.changelist)

        self.assertContains(response, "Eligible")
        self.assertNotContains(response, "no_live_classification")

    def test_adding_an_ineligible_wallet_still_succeeds_and_warns(self):
        _, account = make_investor("wl-add")
        Wallet.objects.create(user_account=account, address="0x" + "3" * 40, chain="base")
        address = "0x" + "3" * 40

        response = self.client.post(self.add_url, {"wallet_address": address, "label": "", "notes": ""}, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(WhitelistEntry.objects.filter_by_address(address).exists())
        self.assertContains(response, "not an eligible wholesale investor")

    def test_adding_an_eligible_wallet_raises_no_warning(self):
        _, account = make_investor("wl-add-ok")
        Wallet.objects.create(user_account=account, address="0x" + "4" * 40, chain="base")
        verified_classification(account, self.reviewer)

        response = self.client.post(
            self.add_url, {"wallet_address": "0x" + "4" * 40, "label": "", "notes": ""}, follow=True
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "not an eligible wholesale investor")
