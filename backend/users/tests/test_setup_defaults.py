from django.contrib.auth import get_user_model
from django.test import TestCase

from portfolios.models import Portfolio
from users.models import UserAccount, UserPreferences, UserProfile
from users.services.setup import ensure_defaults

User = get_user_model()


class EnsureDefaultsTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="defaults@example.test", password="pw-12345678")

    def test_new_user_gets_profile_account_portfolio_and_preferences(self):
        profile, account, portfolio, preferences = ensure_defaults(self.user)

        self.assertEqual(profile.user, self.user)
        self.assertEqual(account.account_number, f"ACC-{self.user.id:06d}")
        self.assertEqual(account.director, profile)
        self.assertIn(profile, account.user_profiles.all())
        self.assertEqual(portfolio.user_account, account)
        self.assertEqual(portfolio.name, "My Portfolio")
        self.assertEqual(preferences.selected_account, account)
        self.assertEqual(preferences.selected_portfolio, portfolio)

    def test_second_call_reuses_every_row(self):
        first = ensure_defaults(self.user)

        second = ensure_defaults(self.user)

        self.assertEqual([row.pk for row in first], [row.pk for row in second])
        self.assertEqual(UserAccount.objects.filter(user_profiles__user=self.user).count(), 1)
        self.assertEqual(Portfolio.objects.filter(user_account__user_profiles__user=self.user).count(), 1)
        self.assertEqual(UserPreferences.objects.filter(user_profile__user=self.user).count(), 1)

    def test_existing_account_without_portfolio_gets_one_and_empty_preferences_are_filled(self):
        profile = UserProfile.objects.create(user=self.user)
        account = UserAccount.objects.create(account_number="EXISTING", director=profile)
        account.user_profiles.add(profile)
        preferences = UserPreferences.objects.create(user_profile=profile)

        _, returned_account, portfolio, returned_preferences = ensure_defaults(self.user)

        self.assertEqual(returned_account, account)
        self.assertEqual(account.portfolios.count(), 1)
        self.assertEqual(returned_preferences.pk, preferences.pk)
        preferences.refresh_from_db()
        self.assertEqual(preferences.selected_account, account)
        self.assertEqual(preferences.selected_portfolio, portfolio)

    def test_populated_preferences_are_left_alone(self):
        profile = UserProfile.objects.create(user=self.user)
        account = UserAccount.objects.create(account_number="EXISTING", director=profile)
        account.user_profiles.add(profile)
        first_portfolio = Portfolio.objects.create(user_account=account, name="First")
        chosen_portfolio = Portfolio.objects.create(user_account=account, name="Chosen")
        UserPreferences.objects.create(
            user_profile=profile, selected_account=account, selected_portfolio=chosen_portfolio
        )

        _, _, portfolio, preferences = ensure_defaults(self.user)

        self.assertIn(portfolio, (first_portfolio, chosen_portfolio))
        self.assertEqual(preferences.selected_portfolio, chosen_portfolio)
        self.assertEqual(account.portfolios.count(), 2)
