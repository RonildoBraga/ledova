from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from users.models import UserAccount
from wallets.models import Wallet
from whitelist.models import WhitelistEntry
from whitelist.models.choices import WhitelistStatus

User = get_user_model()


TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


@override_settings(STORAGES=TEST_STORAGES)
class WhitelistAdminBlockchainConfirmViewsTest(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(email="admin-whitelist@ex.com", password="pw-12345678")
        self.client.force_login(self.admin)
        account = UserAccount.objects.create()
        self.pending_entry = WhitelistEntry.objects.create(
            wallet=Wallet.objects.create(user_account=account, address="0x" + "c" * 40, chain="ethereum")
        )
        self.active_entry = WhitelistEntry.objects.create(
            wallet=Wallet.objects.create(user_account=account, address="0x" + "d" * 40, chain="ethereum"),
            status=WhitelistStatus.ACTIVE,
            is_whitelisted=True,
        )

    def test_add_confirm_page_shows_current_status_label(self):
        url = reverse("admin:whitelist_whitelistentry_add_to_blockchain", args=[self.pending_entry.uuid])

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "admin/whitelist/whitelistentry/add_to_blockchain_confirm.html")
        self.assertContains(response, "<td>Pending</td>", html=False)
        self.assertContains(response, self.pending_entry.wallet.address)

    def test_remove_confirm_page_shows_current_status_label(self):
        url = reverse("admin:whitelist_whitelistentry_remove_from_blockchain", args=[self.active_entry.uuid])

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "admin/whitelist/whitelistentry/remove_from_blockchain_confirm.html")
        self.assertContains(response, '<span class="badge badge-success">Active</span>')
        self.assertContains(response, self.active_entry.wallet.address)
