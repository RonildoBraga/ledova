from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from portfolios.models import Portfolio
from users.models import UserAccount, UserPreferences, UserProfile
from wallets.models import Wallet

User = get_user_model()


class WalletCreatePortfolioAssignmentTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="wallet-create@example.test", password="pw-12345678")
        self.profile = UserProfile.objects.create(user=self.user)
        self.account = UserAccount.objects.create(account_number="WALLET-CREATE")
        self.account.user_profiles.add(self.profile)
        self.portfolio = Portfolio.objects.create(user_account=self.account, name="Selected portfolio")
        self.preferences = UserPreferences.objects.create(
            user_profile=self.profile,
            selected_account=self.account,
            selected_portfolio=self.portfolio,
        )

        self.client.force_authenticate(User.objects.get(pk=self.user.pk))

    def create_wallet(self, address_character):
        response = self.client.post(
            "/api/wallets/",
            {"userAccount": str(self.account.uuid), "address": "0x" + address_character * 40, "chain": "ethereum"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        return Wallet.objects.get(uuid=response.json()["uuid"])

    def test_new_wallet_is_added_to_the_requesters_selected_portfolio(self):
        wallet = self.create_wallet("a")

        self.assertEqual(wallet.verification_status, "PENDING")
        self.assertTrue(self.portfolio.wallets.filter(pk=wallet.pk).exists())

    def test_new_wallet_is_not_added_when_the_selected_portfolio_belongs_to_another_account(self):
        foreign_account = UserAccount.objects.create(account_number="WALLET-FOREIGN")
        foreign_portfolio = Portfolio.objects.create(user_account=foreign_account, name="Foreign portfolio")

        UserPreferences.objects.filter(pk=self.preferences.pk).update(selected_portfolio=foreign_portfolio)

        wallet = self.create_wallet("b")

        self.assertFalse(self.portfolio.wallets.filter(pk=wallet.pk).exists())
        self.assertFalse(foreign_portfolio.wallets.filter(pk=wallet.pk).exists())

    def test_duplicate_address_in_the_same_account_is_rejected_by_validation(self):
        self.create_wallet("c")

        response = self.client.post(
            "/api/wallets/",
            {"userAccount": str(self.account.uuid), "address": "0x" + "c" * 40, "chain": "ethereum"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Wallet.objects.filter(user_account=self.account).count(), 1)
