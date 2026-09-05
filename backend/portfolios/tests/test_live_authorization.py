"""Application-level portfolio isolation through live account membership."""

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from portfolios.models import Portfolio
from users.models import UserAccount, UserPreferences, UserProfile
from wallets.models import Wallet

User = get_user_model()


class PortfolioFixtureMixin:
    def make_tenant(self, label):
        user = User.objects.create_user(email=f"{label}@portfolio.example.test", password="pw-12345678")
        profile = UserProfile.objects.create(user=user)
        account = UserAccount.objects.create(account_number=f"ACCOUNT-{label.upper()}")
        account.user_profiles.add(profile)
        portfolio = Portfolio.objects.create(user_account=account, name=f"{label.title()} Portfolio")
        wallet = Wallet.objects.create(
            user_account=account,
            address="0x" + ("a" if label == "alice" else "b") * 40,
            chain="ethereum",
        )
        return user, profile, account, portfolio, wallet

    @staticmethod
    def rows(response):
        body = response.json()
        return body.get("results", body) if isinstance(body, dict) else body


class PortfolioLiveAuthorizationTest(PortfolioFixtureMixin, APITestCase):
    def setUp(self):
        self.alice, self.alice_profile, self.alice_account, self.alice_portfolio, _ = self.make_tenant("alice")
        self.bob, self.bob_profile, self.bob_account, self.bob_portfolio, _ = self.make_tenant("bob")
        self.preferences = UserPreferences.objects.create(
            user_profile=self.alice_profile,
            selected_account=self.alice_account,
            selected_portfolio=self.alice_portfolio,
        )

    def test_membership_removal_revokes_full_tree(self):
        self.alice_account.user_profiles.remove(self.alice_profile)

        self.assertNotIn(self.alice_portfolio, Portfolio.objects.visible_to_user(self.alice))

        self.client.force_authenticate(self.alice)
        self.assertEqual(
            self.client.get(f"/api/portfolios/{self.alice_portfolio.uuid}/").status_code,
            404,
        )
        preferences_response = self.client.get("/api/user-preferences/")
        self.assertEqual(preferences_response.status_code, 200)
        self.assertIsNone(preferences_response.json()["selectedAccount"])
        self.assertIsNone(preferences_response.json()["selectedPortfolio"])

        export_response = self.client.get("/api/user-profiles/export-data/")
        self.assertEqual(export_response.status_code, 200)
        self.assertIsNone(export_response.json()["preferences"]["selectedAccount"])
        self.assertIsNone(export_response.json()["preferences"]["selectedPortfolio"])
        self.assertEqual(export_response.json()["portfolios"], [])

    def test_reverse_membership_addition_reveals_preexisting_tree(self):
        self.alice_profile.user_accounts.add(self.bob_account)

        self.assertIn(self.bob_portfolio, Portfolio.objects.visible_to_user(self.alice))


class PortfolioEndpointIsolationTest(PortfolioFixtureMixin, APITestCase):
    def setUp(self):
        self.alice, self.alice_profile, self.alice_account, self.alice_portfolio, self.alice_wallet = self.make_tenant(
            "alice"
        )
        self.bob, self.bob_profile, self.bob_account, self.bob_portfolio, self.bob_wallet = self.make_tenant("bob")
        self.client.force_authenticate(self.alice)

    def test_portfolio_list_filter_cannot_expand_the_live_scope(self):
        filtered_response = self.client.get(
            "/api/portfolios/",
            {"user_profile": str(self.alice_profile.uuid)},
        )
        self.assertEqual(filtered_response.status_code, 200)
        self.assertEqual(
            {row["uuid"] for row in self.rows(filtered_response)},
            {str(self.alice_portfolio.uuid)},
        )

        foreign_filter = self.client.get("/api/portfolios/", {"user_profile": str(self.bob_profile.uuid)})
        self.assertEqual(foreign_filter.status_code, 200)
        self.assertNotIn(str(self.bob_portfolio.uuid), {row["uuid"] for row in self.rows(foreign_filter)})

    def test_own_wallet_can_be_added_and_removed(self):
        add_response = self.client.post(
            f"/api/portfolios/{self.alice_portfolio.uuid}/add-wallet/",
            {"walletUuid": str(self.alice_wallet.uuid)},
            format="json",
        )
        self.assertEqual(add_response.status_code, 200)
        self.assertEqual(add_response.json()["portfolio"]["walletUuids"], [str(self.alice_wallet.uuid)])
        self.assertTrue(self.alice_portfolio.wallets.filter(pk=self.alice_wallet.pk).exists())

        remove_response = self.client.post(
            f"/api/portfolios/{self.alice_portfolio.uuid}/remove-wallet/",
            {"walletUuid": str(self.alice_wallet.uuid)},
            format="json",
        )
        self.assertEqual(remove_response.status_code, 200)
        self.assertEqual(remove_response.json()["portfolio"]["walletUuids"], [])
        self.assertFalse(self.alice_portfolio.wallets.filter(pk=self.alice_wallet.pk).exists())

    def test_inconsistent_foreign_wallet_link_is_hidden_from_portfolio_output(self):
        self.alice_portfolio.wallets.add(self.alice_wallet, self.bob_wallet)

        response = self.client.get(f"/api/portfolios/{self.alice_portfolio.uuid}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["walletUuids"], [str(self.alice_wallet.uuid)])
        self.assertEqual(response.json()["walletCount"], 1)

        remove_response = self.client.post(
            f"/api/portfolios/{self.alice_portfolio.uuid}/remove-wallet/",
            {"walletUuid": str(self.bob_wallet.uuid)},
            format="json",
        )
        self.assertEqual(remove_response.status_code, 404)
        self.assertTrue(self.alice_portfolio.wallets.filter(pk=self.bob_wallet.pk).exists())


class PortfolioCreateAccountSelectionTest(PortfolioFixtureMixin, APITestCase):
    def setUp(self):
        self.alice, self.alice_profile, self.account_a, _, _ = self.make_tenant("alice")
        self.bob, _, self.bob_account, _, _ = self.make_tenant("bob")
        self.account_b = UserAccount.objects.create(account_number="ACCOUNT-ALICE-B")
        self.account_b.user_profiles.add(self.alice_profile)
        self.client.force_authenticate(self.alice)

    def _create(self, payload):
        return self.client.post("/api/portfolios/", payload, format="json")

    def test_defaults_to_selected_account(self):
        UserPreferences.objects.create(user_profile=self.alice_profile, selected_account=self.account_b)

        response = self._create({"name": "Selected"})

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["userAccount"], str(self.account_b.uuid))
        self.assertEqual(Portfolio.objects.get(name="Selected").user_account, self.account_b)

    def test_explicit_own_account_wins_over_selected_account(self):
        UserPreferences.objects.create(user_profile=self.alice_profile, selected_account=self.account_b)

        response = self._create({"name": "Explicit", "userAccount": str(self.account_a.uuid)})

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Portfolio.objects.get(name="Explicit").user_account, self.account_a)

    def test_foreign_account_is_rejected(self):
        response = self._create({"name": "Stolen", "userAccount": str(self.bob_account.uuid)})

        self.assertEqual(response.status_code, 400)
        self.assertIn("userAccount", response.json())
        self.assertFalse(Portfolio.objects.filter(name="Stolen").exists())

    def test_ambiguous_accounts_without_selection_are_rejected(self):
        response = self._create({"name": "Ambiguous"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("userAccount", response.json())
        self.assertFalse(Portfolio.objects.filter(name="Ambiguous").exists())

    def test_single_account_without_preferences_is_used(self):
        self.account_b.user_profiles.remove(self.alice_profile)

        response = self._create({"name": "Only"})

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Portfolio.objects.get(name="Only").user_account, self.account_a)

    def test_stale_selected_account_is_not_used(self):
        UserPreferences.objects.create(user_profile=self.alice_profile, selected_account=self.account_b)
        self.account_b.user_profiles.remove(self.alice_profile)

        response = self._create({"name": "Stale"})

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Portfolio.objects.get(name="Stale").user_account, self.account_a)
