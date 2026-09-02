from unittest.mock import Mock, call, patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework.test import APITestCase

from blockchain.models import BlockchainTransaction
from users.models import UserAccount, UserProfile
from wallets.models import Wallet
from whitelist.exceptions import WalletNotRegisteredException
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
        foreign_account = UserAccount.objects.create()
        self.foreign_wallet = Wallet.objects.create(
            user_account=foreign_account,
            address="0x" + "b" * 40,
            chain="ethereum",
        )
        self.foreign_entry = WhitelistEntry.objects.create(
            wallet=self.foreign_wallet,
            is_whitelisted=True,
        )
        self.staff = User.objects.create_user(
            email="staff-whitelist@ex.com",
            password="pw-12345678",
            is_staff=True,
        )
        self.superuser_only = User.objects.create_user(
            email="superuser-only-whitelist@ex.com",
            password="pw-12345678",
            is_superuser=True,
            is_staff=False,
        )
        self.list_url = "/api/v1/whitelist/"
        self.detail_url = f"{self.list_url}{self.entry.uuid}/"
        self.by_address_url = f"/api/v1/whitelist/entry/{self.wallet.address}/"
        self.export_url = "/api/v1/whitelist/export/"
        self.add_url = "/api/v1/whitelist/add/"
        self.remove_url = "/api/v1/whitelist/remove/"
        self.batch_add_url = "/api/v1/whitelist/batch-add/"
        self.sync_url = f"/api/v1/whitelist/sync/{self.wallet.address}/"

    def _operator_route_requests(self):
        return [
            ("get", self.list_url, None),
            ("get", self.detail_url, None),
            ("get", self.by_address_url, None),
            ("get", self.export_url, None),
            ("post", self.add_url, {"walletAddress": self.wallet.address}),
            ("post", self.remove_url, {"walletAddress": self.wallet.address}),
            (
                "post",
                self.batch_add_url,
                {"entries": [{"walletAddress": self.wallet.address}]},
            ),
            ("post", self.sync_url, None),
            ("post", self.list_url, {"status": "active"}),
            ("put", self.detail_url, {"status": "active"}),
            ("patch", self.detail_url, {"status": "active"}),
            ("delete", self.detail_url, None),
        ]

    def test_queryset_is_visible_only_to_authenticated_staff(self):
        for actor in (None, AnonymousUser(), self.member, self.superuser_only):
            with self.subTest(actor=actor):
                self.assertFalse(WhitelistEntry.objects.visible_to_user(actor).exists())

        self.assertEqual(
            set(WhitelistEntry.objects.visible_to_user(self.staff)),
            {self.entry, self.foreign_entry},
        )

    @patch("whitelist.views.entry.WhitelistService")
    def test_nonoperators_cannot_use_operator_routes(self, whitelist_service):
        for actor in (self.member, self.superuser_only):
            self.client.force_authenticate(actor)
            for method, url, data in self._operator_route_requests():
                with self.subTest(actor=actor.email, method=method, url=url):
                    response = getattr(self.client, method)(url, data, format="json")
                    self.assertEqual(response.status_code, 403)

        whitelist_service.assert_not_called()

    @patch("whitelist.views.entry.WhitelistService")
    def test_anonymous_cannot_use_operator_routes(self, whitelist_service):
        for method, url, data in self._operator_route_requests():
            with self.subTest(method=method, url=url):
                response = getattr(self.client, method)(url, data, format="json")
                self.assertEqual(response.status_code, 401)

        whitelist_service.assert_not_called()

    def test_staff_can_list_retrieve_and_export_global_operator_rows(self):
        self.client.force_authenticate(self.staff)

        list_response = self.client.get(self.list_url)
        retrieve_response = self.client.get(self.detail_url)
        export_response = self.client.get(self.export_url)

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(
            {entry["uuid"] for entry in list_response.json()["results"]},
            {str(self.entry.uuid), str(self.foreign_entry.uuid)},
        )
        self.assertEqual(retrieve_response.status_code, 200)
        self.assertEqual(retrieve_response.json()["uuid"], str(self.entry.uuid))
        self.assertEqual(export_response.status_code, 200)
        self.assertEqual(export_response["Content-Type"], "text/csv")
        exported = export_response.content.decode()
        self.assertIn(self.wallet.address, exported)
        self.assertIn(self.foreign_wallet.address, exported)

    @patch("whitelist.views.entry.WhitelistService")
    def test_staff_can_use_all_operator_custom_actions(self, whitelist_service):
        service = whitelist_service.return_value
        service.add_to_whitelist.return_value = ("0xadd", self.entry)
        service.remove_from_whitelist.return_value = ("0xremove", self.entry)
        service.sync_entry.return_value = self.entry
        self.client.force_authenticate(self.staff)

        add_response = self.client.post(
            self.add_url,
            {"walletAddress": self.wallet.address},
            format="json",
        )
        remove_response = self.client.post(
            self.remove_url,
            {"walletAddress": self.wallet.address},
            format="json",
        )
        batch_response = self.client.post(
            self.batch_add_url,
            {"entries": [{"walletAddress": self.wallet.address}]},
            format="json",
        )
        sync_response = self.client.post(self.sync_url)

        self.assertEqual(add_response.status_code, 201)
        self.assertEqual(remove_response.status_code, 200)
        self.assertEqual(batch_response.status_code, 200)
        self.assertEqual(batch_response.json()["successful"], 1)
        self.assertEqual(sync_response.status_code, 200)
        self.assertEqual(whitelist_service.call_count, 4)
        service.add_to_whitelist.assert_has_calls(
            [
                call(address=self.wallet.address, wait_for_receipt=True),
                call(address=self.wallet.address, wait_for_receipt=True),
            ]
        )
        service.remove_from_whitelist.assert_called_once_with(
            address=self.wallet.address,
            wait_for_receipt=True,
        )
        service.sync_entry.assert_called_once_with(
            self.wallet.address,
            wallet_uuid=self.wallet.uuid,
        )

    @patch("whitelist.views.entry.WhitelistService")
    def test_staff_standard_write_routes_are_absent_and_preserve_rows(self, whitelist_service):
        self.entry.notes = "preserve me"
        self.entry.save(update_fields=["notes", "updated_at"])
        original = {
            "wallet_id": self.entry.wallet_id,
            "status": self.entry.status,
            "is_whitelisted": self.entry.is_whitelisted,
            "notes": self.entry.notes,
        }
        original_count = WhitelistEntry.objects.count()
        self.client.force_authenticate(self.staff)

        responses = [
            self.client.post(self.list_url, {"walletAddress": self.wallet.address}, format="json"),
            self.client.put(self.detail_url, {"status": "active"}, format="json"),
            self.client.patch(self.detail_url, {"status": "active"}, format="json"),
            self.client.delete(self.detail_url),
        ]

        for response in responses:
            self.assertEqual(response.status_code, 405)
        self.assertEqual(WhitelistEntry.objects.count(), original_count)
        self.entry.refresh_from_db()
        self.assertEqual(
            {
                "wallet_id": self.entry.wallet_id,
                "status": self.entry.status,
                "is_whitelisted": self.entry.is_whitelisted,
                "notes": self.entry.notes,
            },
            original,
        )
        whitelist_service.assert_not_called()

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

        response = self.client.post("/api/v1/whitelist/sync/0xcccccccccccccccccccccccccccccccccccccccc/")

        self.assertEqual(response.status_code, 404)
        whitelist_service.assert_not_called()

    def _service_with_mocked_chain(self):
        service = WhitelistService.__new__(WhitelistService)
        service.chain_client = Mock()
        service.chain_client.to_checksum_address.side_effect = lambda address: address
        service.signer_key = "0xoperator"
        service.contract_address = "0x" + "d" * 40
        service.is_whitelisted = Mock(return_value=False)
        return service

    def test_add_rejects_unregistered_address_without_creating_rows(self):
        unknown = "0x" + "c" * 40

        with self.assertRaises(WalletNotRegisteredException):
            self._service_with_mocked_chain().add_to_whitelist(unknown)

        self.assertFalse(Wallet.objects.filter_by_address(unknown).exists())
        self.assertFalse(WhitelistEntry.objects.filter(wallet__address__iexact=unknown).exists())
        self.assertFalse(BlockchainTransaction.objects.exists())

    def test_add_rejects_ambiguous_address(self):
        Wallet.objects.create(user_account=UserAccount.objects.create(), address=self.wallet.address, chain="base")

        with self.assertRaises(WalletNotRegisteredException):
            self._service_with_mocked_chain().add_to_whitelist(self.wallet.address)

        self.assertFalse(BlockchainTransaction.objects.exists())
