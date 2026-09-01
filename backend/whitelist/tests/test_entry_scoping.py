from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from users.models import UserAccount, UserProfile
from wallets.models import Wallet
from whitelist.models import WhitelistEntry
from whitelist.services import WhitelistService

User = get_user_model()


class WhitelistEntryScopingTest(APITestCase):
    def setUp(self):
        self.member = User.objects.create_user(email="member-whitelist@ex.com", password="pw-12345678")
        profile = UserProfile.objects.create(user=self.member)
        account = UserAccount.objects.create()
        account.user_profiles.add(profile)
        self.wallet = Wallet.objects.create(
            user_account=account,
            address="0x" + "a" * 40,
            chain="ethereum",
        )
        self.entry = WhitelistEntry.objects.create(wallet=self.wallet)
        self.staff = User.objects.create_user(
            email="staff-whitelist@ex.com",
            password="pw-12345678",
            is_staff=True,
        )
        self.by_address_url = f"/api/v1/whitelist/entry/{self.wallet.address}/"
        self.sync_url = f"/api/v1/whitelist/sync/{self.wallet.address}/"

    def test_nonstaff_by_address_is_not_found(self):
        self.client.force_authenticate(self.member)

        response = self.client.get(self.by_address_url)

        self.assertEqual(response.status_code, 404)

    def test_staff_by_address_succeeds(self):
        self.client.force_authenticate(self.staff)

        response = self.client.get(self.by_address_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["uuid"], str(self.entry.uuid))

    def test_staff_by_address_fails_closed_when_address_is_ambiguous(self):
        other_account = UserAccount.objects.create()
        duplicate_wallet = Wallet.objects.create(
            user_account=other_account,
            address=self.wallet.address,
            chain="base",
        )
        WhitelistEntry.objects.create(wallet=duplicate_wallet)
        self.client.force_authenticate(self.staff)

        response = self.client.get(self.by_address_url)

        self.assertEqual(response.status_code, 404)

    @patch("whitelist.views.entry.WhitelistService")
    def test_nonstaff_cannot_sync(self, whitelist_service):
        self.client.force_authenticate(self.member)

        response = self.client.post(self.sync_url)

        self.assertEqual(response.status_code, 403)
        whitelist_service.assert_not_called()

    @patch("whitelist.views.entry.WhitelistService")
    def test_staff_can_sync(self, whitelist_service):
        whitelist_service.return_value.sync_entry.return_value = self.entry
        self.client.force_authenticate(self.staff)

        response = self.client.post(self.sync_url)

        self.assertEqual(response.status_code, 200)
        whitelist_service.assert_called_once_with()
        whitelist_service.return_value.sync_entry.assert_called_once_with(
            self.wallet.address,
            wallet_uuid=self.wallet.uuid,
        )

    @patch("whitelist.views.entry.WhitelistService")
    def test_staff_sync_fails_closed_when_wallet_address_is_ambiguous(self, whitelist_service):
        other_account = UserAccount.objects.create()
        Wallet.objects.create(
            user_account=other_account,
            address=self.wallet.address,
            chain="base",
        )
        self.client.force_authenticate(self.staff)

        response = self.client.post(self.sync_url)

        self.assertEqual(response.status_code, 404)
        whitelist_service.assert_not_called()

    def test_sync_service_uses_explicit_wallet_uuid_when_duplicate_is_added(self):
        other_account = UserAccount.objects.create()
        Wallet.objects.create(
            user_account=other_account,
            address=self.wallet.address,
            chain="base",
        )
        service = WhitelistService.__new__(WhitelistService)
        service.chain_client = Mock()
        service.chain_client.to_checksum_address.return_value = self.wallet.address
        service.get_investor_info = Mock(return_value={"whitelisted": True, "kyc_timestamp": 0})

        entry = service.sync_entry(self.wallet.address, wallet_uuid=self.wallet.uuid)

        self.assertEqual(entry.wallet_id, self.wallet.uuid)

    @patch("whitelist.views.entry.WhitelistService")
    def test_staff_sync_unknown_address_is_not_found_before_service(self, whitelist_service):
        self.client.force_authenticate(self.staff)

        response = self.client.post("/api/v1/whitelist/sync/0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb/")

        self.assertEqual(response.status_code, 404)
        whitelist_service.assert_not_called()
