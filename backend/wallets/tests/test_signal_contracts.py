from django.contrib.auth import get_user_model
from django.test import TestCase

from portfolios.models import Portfolio
from users.models import UserAccount, UserPreferences, UserProfile
from wallets.models import Wallet

User = get_user_model()


class WalletSignalContractTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="wallet-signal@example.test",
            password="pw-12345678",
        )
        self.profile = UserProfile.objects.create(user=self.user)
        self.account = UserAccount.objects.create(account_number="WALLET-SIGNAL")
        self.account.user_profiles.add(self.profile)
        self.portfolio = Portfolio.objects.create(
            user_account=self.account,
            name="Selected portfolio",
        )

    def create_wallet(self, address_character):
        return Wallet.objects.create(
            user_account=self.account,
            address="0x" + address_character * 40,
            chain="ethereum",
        )

    def test_new_wallet_is_added_to_matching_selected_portfolio(self):
        UserPreferences.objects.create(
            user_profile=self.profile,
            selected_account=self.account,
            selected_portfolio=self.portfolio,
        )

        wallet = self.create_wallet("a")

        self.assertTrue(self.portfolio.wallets.filter(pk=wallet.pk).exists())

    def test_new_wallet_is_not_added_to_mismatched_selected_portfolio(self):
        preferences = UserPreferences.objects.create(
            user_profile=self.profile,
            selected_account=self.account,
            selected_portfolio=self.portfolio,
        )
        foreign_account = UserAccount.objects.create(account_number="WALLET-SIGNAL-FOREIGN")
        foreign_portfolio = Portfolio.objects.create(
            user_account=foreign_account,
            name="Foreign portfolio",
        )
        UserPreferences.objects.filter(pk=preferences.pk).update(selected_portfolio=foreign_portfolio)

        wallet = self.create_wallet("b")

        self.assertFalse(self.portfolio.wallets.filter(pk=wallet.pk).exists())
        self.assertFalse(foreign_portfolio.wallets.filter(pk=wallet.pk).exists())

    def test_updating_existing_wallet_does_not_trigger_auto_assignment(self):
        wallet = self.create_wallet("c")
        UserPreferences.objects.create(
            user_profile=self.profile,
            selected_account=self.account,
            selected_portfolio=self.portfolio,
        )

        wallet.name = "Updated wallet"
        wallet.save(update_fields=["name"])

        self.assertFalse(self.portfolio.wallets.filter(pk=wallet.pk).exists())
