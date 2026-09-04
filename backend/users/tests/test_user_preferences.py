from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from portfolios.models import Portfolio
from users.models import UserAccount, UserPreferences, UserProfile

User = get_user_model()


class UserPreferencesEndpointTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="prefs@example.test", password="pw-12345678")
        self.profile = UserProfile.objects.create(user=self.user, full_name="Prefs Owner")
        self.account = UserAccount.objects.create(account_number="PREFS-A", director=self.profile)
        self.account.user_profiles.add(self.profile)
        self.portfolio = Portfolio.objects.create(user_account=self.account, name="A portfolio")
        self.second_account = UserAccount.objects.create(account_number="PREFS-B", director=self.profile)
        self.second_account.user_profiles.add(self.profile)
        self.second_portfolio = Portfolio.objects.create(user_account=self.second_account, name="B portfolio")

        stranger = User.objects.create_user(email="stranger@example.test", password="pw-12345678")
        stranger_profile = UserProfile.objects.create(user=stranger)
        self.foreign_account = UserAccount.objects.create(account_number="PREFS-F", director=stranger_profile)
        self.foreign_account.user_profiles.add(stranger_profile)
        self.foreign_portfolio = Portfolio.objects.create(user_account=self.foreign_account, name="Foreign")
        self.client.force_authenticate(self.user)

    def post(self, **payload):
        return self.client.post("/api/user-preferences/", payload, format="json")

    def test_list_is_404_until_created_then_returns_client_keys(self):
        self.assertEqual(self.client.get("/api/user-preferences/").status_code, 404)

        created = self.post(selectedAccount=str(self.account.uuid), selectedPortfolio=str(self.portfolio.uuid))
        self.assertEqual(created.status_code, 200, created.content)

        body = self.client.get("/api/user-preferences/").json()
        self.assertEqual(
            set(body), {"uuid", "userProfile", "selectedAccount", "selectedPortfolio", "theme", "displayCurrency"}
        )
        self.assertEqual(
            set(body["selectedAccount"]), {"uuid", "accountNumber", "accountType", "activationDate", "role"}
        )
        self.assertEqual(set(body["selectedPortfolio"]), {"uuid", "userAccount", "name", "isActive"})
        self.assertEqual(body["selectedPortfolio"]["userAccount"], str(self.account.uuid))
        self.assertEqual(body["theme"], "dark")
        self.assertEqual(body["displayCurrency"], "AUD")

    def test_post_upserts_the_single_row(self):
        first = self.post(selectedPortfolio=str(self.portfolio.uuid)).json()
        second = self.post(displayCurrency="USD", theme="light").json()

        self.assertEqual(first["uuid"], second["uuid"])
        self.assertEqual(UserPreferences.objects.filter(user_profile=self.profile).count(), 1)
        self.assertEqual(second["displayCurrency"], "USD")
        self.assertEqual(second["theme"], "light")
        self.assertEqual(second["selectedPortfolio"]["uuid"], str(self.portfolio.uuid))

    def test_portfolio_alone_fills_in_its_account(self):
        body = self.post(selectedPortfolio=str(self.second_portfolio.uuid)).json()

        self.assertEqual(body["selectedAccount"]["uuid"], str(self.second_account.uuid))

    def test_portfolio_must_belong_to_selected_account(self):
        response = self.post(selectedAccount=str(self.account.uuid), selectedPortfolio=str(self.second_portfolio.uuid))

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(), {"selectedPortfolio": ["The selected portfolio must belong to the selected account."]}
        )

    def test_foreign_rows_are_rejected_by_field_scoping(self):
        for payload, key in (
            ({"selectedPortfolio": str(self.foreign_portfolio.uuid)}, "selectedPortfolio"),
            ({"selectedAccount": str(self.foreign_account.uuid)}, "selectedAccount"),
        ):
            with self.subTest(key=key):
                response = self.post(**payload)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(list(response.json()), [key])
                self.assertFalse(UserPreferences.objects.filter(user_profile=self.profile).exists())

    def test_model_layer_no_longer_validates_membership(self):
        preferences = UserPreferences.objects.create(
            user_profile=self.profile, selected_portfolio=self.foreign_portfolio
        )

        self.assertEqual(preferences.selected_portfolio, self.foreign_portfolio)
        self.assertIsNone(self.client.get("/api/user-preferences/").json()["selectedPortfolio"])
