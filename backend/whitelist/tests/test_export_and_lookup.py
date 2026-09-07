import csv
from io import StringIO

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APITestCase

from users.models import UserAccount
from wallets.models import Wallet
from whitelist.exceptions import WalletNotRegisteredException
from whitelist.models import WhitelistEntry
from whitelist.services import unique_wallet_uuid_for

User = get_user_model()

FORMULA = '=HYPERLINK("http://x","c")'
EXPORT_URL = "/api/v1/whitelist/export/"


class WhitelistExportEscapingTest(APITestCase):
    def setUp(self):
        self.staff = User.objects.create_user(email="staff-export@ex.com", password="pw-12345678", is_staff=True)
        self.client.force_authenticate(self.staff)

    def _rows(self):
        response = self.client.get(EXPORT_URL)
        self.assertEqual(response.status_code, 200)
        return list(csv.reader(StringIO(response.content.decode())))

    def test_a_formula_in_a_stored_address_is_neutralised_in_the_export(self):
        WhitelistEntry.objects.create(address=FORMULA, label="Treasury")

        cell = self._rows()[1][0]

        self.assertTrue(cell.startswith("'"))
        self.assertEqual(cell, f"'{FORMULA}")

    def test_every_formula_lead_character_is_covered_not_just_equals(self):
        for index, lead in enumerate("=+-@"):
            WhitelistEntry.objects.create(address=f"{lead}cmd{index}", label=f"Treasury {index}")

        cells = [row[0] for row in self._rows()[1:]]

        self.assertEqual(len(cells), 4)
        for cell in cells:
            self.assertTrue(cell.startswith("'"), cell)

    def test_an_ordinary_address_is_written_unchanged(self):
        wallet = Wallet.objects.create(user_account=UserAccount.objects.create(), address="0x" + "a" * 40, chain="base")
        WhitelistEntry.objects.create(wallet=wallet)

        self.assertEqual(self._rows()[1][0], wallet.address)


class UniqueWalletUuidForTest(TestCase):
    def setUp(self):
        self.address = "0x" + "a" * 40

    def _wallet(self, address=None, chain="base"):
        return Wallet.objects.create(
            user_account=UserAccount.objects.create(), address=address or self.address, chain=chain
        )

    def test_exactly_one_wallet_gives_its_uuid(self):
        wallet = self._wallet()

        self.assertEqual(unique_wallet_uuid_for(self.address), wallet.uuid)

    def test_no_wallet_is_refused(self):
        with self.assertRaises(WalletNotRegisteredException):
            unique_wallet_uuid_for(self.address)

    def test_two_wallets_at_one_address_are_refused_rather_than_guessed_between(self):
        self._wallet(chain="base")
        self._wallet(chain="ethereum")

        with self.assertRaises(WalletNotRegisteredException):
            unique_wallet_uuid_for(self.address)

    def test_the_refusal_answers_404(self):
        self.assertEqual(WalletNotRegisteredException.status_code, 404)
