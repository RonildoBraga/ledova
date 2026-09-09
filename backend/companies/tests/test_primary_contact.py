from django.contrib.auth import get_user_model
from django.test import TestCase

from companies.models import Company, CompanyStatus, CompanyType
from companies.serializers import CompanyDetailSerializer
from companies.services.company import primary_wallet_for
from users.models import UserAccount, UserProfile
from wallets.constants import (
    WALLET_VERIFICATION_STATUS_PENDING,
    WALLET_VERIFICATION_STATUS_VERIFIED,
)
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

    def _wallet(self, chain, suffix, account=None, verified=True):
        return Wallet.objects.create(
            user_account=account or self.account,
            address="0x" + suffix * 40,
            chain=chain,
            verification_status=WALLET_VERIFICATION_STATUS_VERIFIED if verified else WALLET_VERIFICATION_STATUS_PENDING,
        )

    def test_primary_wallets_are_selected_only_on_the_requested_network(self):
        self.assertIsNone(primary_wallet_for(self.company))

        self._wallet("base", "0", verified=False)
        self.assertIsNone(primary_wallet_for(self.company))

        ethereum = self._wallet("ethereum", "1")
        self.assertIsNone(primary_wallet_for(self.company))

        base = self._wallet("base", "2")
        self.assertEqual(primary_wallet_for(self.company), base)
        self.assertEqual(primary_wallet_for(self.company, "ethereum"), ethereum)

        other_account = UserAccount.objects.create()
        operator = self._wallet("base", "3", account=other_account)
        self.company.operator_wallet = operator
        self.company.save(update_fields=["operator_wallet"])
        self.assertEqual(primary_wallet_for(self.company), operator)
        self.assertIsNone(primary_wallet_for(self.company, "ethereum"))

    def test_wallets_of_other_users_are_never_primary(self):
        stranger = User.objects.create_user(email="stranger@example.test", password="pw-12345678")
        stranger_account = UserAccount.objects.create()
        stranger_account.user_profiles.add(UserProfile.objects.create(user=stranger))
        self._wallet("base", "4", account=stranger_account)

        self.assertIsNone(primary_wallet_for(self.company))
