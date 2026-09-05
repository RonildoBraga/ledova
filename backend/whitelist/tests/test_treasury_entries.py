"""Whitelist entries for operator-held addresses no user wallet backs: admin add form, service and read routes."""

from unittest.mock import Mock

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from blockchain.models import BlockchainTransaction
from users.models import UserAccount
from wallets.models import Wallet
from whitelist.exceptions import WalletNotRegisteredException
from whitelist.models import WhitelistEntry, WhitelistStatus
from whitelist.services import WhitelistService

User = get_user_model()
TREASURY = "0x" + "ab" * 20
TREASURY_CHECKSUM = "0xABaBaBaBABabABabAbAbABAbABabababaBaBABaB"
RECEIPT = {"blockNumber": 7, "blockHash": bytes.fromhex("ab" * 32), "gasUsed": 21000}
TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


def treasury_entry(label="Treasury"):
    return WhitelistEntry.objects.create(address=TREASURY_CHECKSUM, label=label)


class TreasuryEntryModelTest(TestCase):
    def test_address_falls_back_to_the_stored_one_and_an_entry_needs_one_of_the_two(self):
        entry = treasury_entry()
        wallet = Wallet.objects.create(user_account=UserAccount.objects.create(), address="0x" + "c" * 40, chain="base")
        backed = WhitelistEntry.objects.create(wallet=wallet)

        self.assertEqual((entry.wallet_address, str(entry)), (TREASURY_CHECKSUM, f"{TREASURY_CHECKSUM[:10]}..."))
        self.assertEqual(backed.wallet_address, wallet.address)
        self.assertEqual(WhitelistEntry.objects.filter_by_address(TREASURY.lower()).get(), entry)
        self.assertEqual(WhitelistEntry.objects.filter_by_address(wallet.address).get(), backed)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                WhitelistEntry.objects.create(label="Nothing behind it")


class TreasuryEntryServiceTest(TestCase):
    def _service(self, on_chain=False):
        service = WhitelistService.__new__(WhitelistService)
        service.chain_client = Mock()
        service.chain_client.to_checksum_address.side_effect = lambda address: address
        service.chain_client.account_from_key.return_value.address = "0x" + "f" * 40
        service.chain_client.send_transaction.return_value = ("0xhash", RECEIPT)
        service.signer_key = "0xoperator"
        service.contract_address = "0x" + "d" * 40
        service._contract = Mock()
        service.is_whitelisted = Mock(return_value=on_chain)
        service.get_investor_info = Mock(return_value={"whitelisted": on_chain, "kyc_timestamp": 0})
        return service

    def test_add_resolves_the_treasury_entry_without_a_wallet(self):
        entry = treasury_entry()

        tx_hash, resolved = self._service().add_to_whitelist(TREASURY_CHECKSUM)

        self.assertEqual((tx_hash, resolved), ("0xhash", entry))
        entry.refresh_from_db()
        self.assertEqual((entry.status, entry.is_whitelisted, entry.wallet), (WhitelistStatus.ACTIVE, True, None))
        self.assertEqual(BlockchainTransaction.objects.get().related_uuid, entry.uuid)

    def test_ensure_whitelisted_and_sync_work_on_a_treasury_entry(self):
        entry = treasury_entry()
        service = self._service()

        self.assertEqual(service.ensure_whitelisted([entry]), {"added": 1, "synced": 0, "skipped": 0, "errors": []})
        entry.refresh_from_db()
        self.assertTrue(entry.is_whitelisted)

        synced = self._service(on_chain=True).sync_entry(TREASURY_CHECKSUM)
        self.assertEqual((synced, synced.status, synced.wallet), (entry, WhitelistStatus.ACTIVE, None))
        self.assertEqual(WhitelistEntry.objects.count(), 1)

    def test_an_unknown_address_without_a_treasury_entry_is_still_refused(self):
        with self.assertRaises(WalletNotRegisteredException):
            self._service().add_to_whitelist("0x" + "9" * 40)
        self.assertFalse(WhitelistEntry.objects.exists())


@override_settings(STORAGES=TEST_STORAGES)
class TreasuryEntryAdminTest(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_superuser(email="admin@example.test", password="pw-12345678"))
        self.add_url = reverse("admin:whitelist_whitelistentry_add")

    def test_unknown_address_needs_a_label_and_is_stored_checksummed_without_a_wallet(self):
        refused = self.client.post(self.add_url, {"wallet_address": TREASURY, "label": "", "notes": ""})
        self.assertEqual(refused.status_code, 200)
        self.assertContains(refused, "Give the entry a label")
        self.assertFalse(WhitelistEntry.objects.exists())

        malformed = self.client.post(self.add_url, {"wallet_address": "0x1234", "label": "Treasury", "notes": ""})
        self.assertContains(malformed, "Enter a valid EVM address.")

        created = self.client.post(self.add_url, {"wallet_address": TREASURY, "label": "Treasury", "notes": ""})
        self.assertEqual(created.status_code, 302)
        entry = WhitelistEntry.objects.get()
        self.assertEqual((entry.wallet, entry.address, entry.label), (None, TREASURY_CHECKSUM, "Treasury"))

        duplicate = self.client.post(
            self.add_url, {"wallet_address": TREASURY.upper().replace("0X", "0x"), "label": "x"}
        )
        self.assertContains(duplicate, "already has a whitelist entry")

    def test_a_users_wallet_still_binds_the_entry_to_the_wallet(self):
        wallet = Wallet.objects.create(user_account=UserAccount.objects.create(), address="0x" + "c" * 40, chain="base")

        response = self.client.post(self.add_url, {"wallet_address": wallet.address, "label": "", "notes": ""})

        self.assertEqual(response.status_code, 302)
        entry = WhitelistEntry.objects.get()
        self.assertEqual((entry.wallet, entry.address), (wallet, ""))

    def test_change_page_and_confirm_pages_render_for_a_treasury_entry(self):
        entry = treasury_entry("Custodian")

        for name in ("change", "add_to_blockchain"):
            response = self.client.get(reverse(f"admin:whitelist_whitelistentry_{name}", args=[entry.pk]))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, TREASURY_CHECKSUM)
            self.assertContains(response, "Custodian")
        changelist = self.client.get(reverse("admin:whitelist_whitelistentry_changelist"))
        self.assertContains(changelist, "Operator (treasury/custodian)")


class TreasuryEntryRoutesTest(APITestCase):
    def setUp(self):
        self.entry = treasury_entry("Treasury")
        self.client.force_authenticate(
            User.objects.create_user(email="staff@example.test", password="pw-12345678", is_staff=True)
        )

    def test_staff_read_routes_carry_the_stored_address_and_label(self):
        listed = self.client.get("/api/v1/whitelist/").json()["results"]
        self.assertEqual((listed[0]["walletAddress"], listed[0]["label"]), (TREASURY_CHECKSUM, "Treasury"))

        by_address = self.client.get(f"/api/v1/whitelist/entry/{TREASURY}/")
        self.assertEqual(by_address.status_code, 200)
        self.assertEqual(by_address.json()["uuid"], str(self.entry.uuid))

        exported = self.client.get("/api/v1/whitelist/export/").content.decode()
        self.assertIn(TREASURY_CHECKSUM, exported)
