from django.contrib.auth import get_user_model
from django.test import TestCase

from companies.models import Company, CompanyStatus, CompanyType
from companies.serializers import CompanyDetailSerializer
from users.models import UserAccount, UserProfile
from wallets.models import Wallet

User = get_user_model()


class CompanyPrimaryContactTest(TestCase):
    def test_primary_contact_is_the_owner_profile(self):
        owner = User.objects.create_user(email="owner@example.test", password="pw-12345678")
        profile = UserProfile.objects.create(user=owner, full_name="Owner Person")
        company = Company.objects.create(
            owner=owner,
            name="Contact Pty Ltd",
            company_type=CompanyType.PROPRIETARY,
            acn="000000777",
            status=CompanyStatus.ACTIVE,
        )

        self.assertEqual(company.primary_contact, profile)
        self.assertEqual(CompanyDetailSerializer(company).data["primary_contact"]["full_name"], "Owner Person")


class CompanyPrimaryWalletTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(email="wallets@example.test", password="pw-12345678")
        self.account = UserAccount.objects.create()
        self.account.user_profiles.add(UserProfile.objects.create(user=self.owner))
        self.company = Company.objects.create(
            owner=self.owner, name="Wallets Pty Ltd", company_type=CompanyType.PROPRIETARY, acn="000000778"
        )

    def _wallet(self, chain, suffix, account=None):
        return Wallet.objects.create(user_account=account or self.account, address="0x" + suffix * 40, chain=chain)

    def test_operator_wallet_wins_and_owner_wallets_fall_back_to_ethereum(self):
        self.assertIsNone(self.company.get_primary_wallet())

        ethereum = self._wallet("ethereum", "1")
        self.assertEqual(self.company.get_primary_wallet(), ethereum)

        base = self._wallet("base", "2")
        self.assertEqual(self.company.get_primary_wallet(), base)
        self.assertEqual(self.company.get_primary_wallet("ethereum"), ethereum)

        other_account = UserAccount.objects.create()
        operator = self._wallet("base", "3", account=other_account)
        self.company.operator_wallet = operator
        self.company.save(update_fields=["operator_wallet"])
        self.assertEqual(self.company.get_primary_wallet(), operator)
        self.assertEqual(self.company.get_primary_wallet("ethereum"), ethereum)

    def test_wallets_of_other_users_are_never_primary(self):
        stranger = User.objects.create_user(email="stranger@example.test", password="pw-12345678")
        stranger_account = UserAccount.objects.create()
        stranger_account.user_profiles.add(UserProfile.objects.create(user=stranger))
        self._wallet("base", "4", account=stranger_account)

        self.assertIsNone(self.company.get_primary_wallet())
