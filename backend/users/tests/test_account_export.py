from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from assets.models import Asset
from portfolios.models import Portfolio
from shared.models import Country
from users.models import FinancialProfile, UserAccount, UserPreferences, UserProfile
from wallets.models import Transaction, Wallet

User = get_user_model()


class AccountExportTest(APITestCase):
    """Pins the camelCase document the dashboard and mobile settings screens write out verbatim."""

    def setUp(self):
        self.user = User.objects.create_user(email="export@example.test", password="pw-12345678")
        self.profile = UserProfile.objects.create(
            user=self.user,
            full_name="Export Owner",
            citizenship_country=Country.objects.create(name="Australia", code="AU"),
        )
        FinancialProfile.objects.create(user_profile=self.profile, occupation="Engineer")
        self.account = UserAccount.objects.create(account_number="EXPORT-ACC", director=self.profile)
        self.account.user_profiles.add(self.profile)
        self.portfolio = Portfolio.objects.create(user_account=self.account, name="Main")
        UserPreferences.objects.create(
            user_profile=self.profile, selected_account=self.account, selected_portfolio=self.portfolio
        )
        self.wallet = Wallet.objects.create(user_account=self.account, address="0x" + "a" * 40, chain="base")
        asset = Asset.objects.create(symbol="EXP", name="Export asset", asset_type="tokenized_security", is_active=True)
        Transaction.objects.create(
            tx_hash="0xexport",
            chain="base",
            from_address=self.wallet.address,
            to_address="0x" + "b" * 40,
            asset=asset,
            amount=Decimal("1.5"),
            transaction_fee=Decimal("0.000000000000000001"),
            wallet=self.wallet,
        )
        self.client.force_authenticate(self.user)

    def test_export_keeps_client_document_shape(self):
        body = self.client.get("/api/user-profiles/export-data/").json()

        self.assertEqual(
            set(body),
            {
                "exportedAt",
                "user",
                "profile",
                "preferences",
                "financialProfile",
                "accounts",
                "wallets",
                "transactions",
                "portfolios",
            },
        )
        self.assertIsInstance(body["exportedAt"], str)
        self.assertEqual(set(body["user"]), {"email", "dateJoined", "isEmailVerified"})
        self.assertEqual(
            set(body["profile"]),
            {
                "fullName",
                "dateOfBirth",
                "phoneCountryCode",
                "phoneNumber",
                "residentialAddress",
                "citizenshipCountry",
                "isIdVerified",
                "createdAt",
            },
        )
        self.assertEqual(body["profile"]["citizenshipCountry"], "Australia")
        self.assertEqual(
            body["preferences"],
            {"selectedPortfolio": str(self.portfolio.uuid), "selectedAccount": str(self.account.uuid)},
        )
        self.assertEqual(
            set(body["financialProfile"]),
            {"occupation", "sourceOfFunds", "sourceOfFundsOtherText", "intendedUse", "intendedUseOtherText"},
        )
        self.assertEqual(
            set(body["accounts"][0]), {"uuid", "accountNumber", "accountType", "activationDate", "createdAt"}
        )
        self.assertEqual(body["accounts"][0]["uuid"], str(self.account.uuid))
        self.assertEqual(
            set(body["wallets"][0]),
            {"uuid", "name", "chain", "address", "nativeBalance", "marketValue", "isVerified", "createdAt"},
        )
        self.assertEqual(body["wallets"][0]["nativeBalance"], "0")
        self.assertIs(body["wallets"][0]["isVerified"], False)
        self.assertEqual(
            set(body["transactions"][0]),
            {
                "uuid",
                "txHash",
                "chain",
                "status",
                "asset",
                "amount",
                "transactionFee",
                "fromAddress",
                "toAddress",
                "blockTimestamp",
                "createdAt",
            },
        )
        self.assertEqual(body["transactions"][0]["asset"], "EXP")
        self.assertEqual(Decimal(body["transactions"][0]["amount"]), Decimal("1.5"))
        self.assertEqual(Decimal(body["transactions"][0]["transactionFee"]), Decimal("1E-18"))
        self.assertEqual(set(body["portfolios"][0]), {"uuid", "name", "isActive", "createdAt"})
        self.assertIsInstance(body["portfolios"][0]["createdAt"], str)

    def test_export_without_profile_returns_empty_sections(self):
        bare = User.objects.create_user(email="bare@example.test", password="pw-12345678")
        self.client.force_authenticate(bare)

        body = self.client.get("/api/user-profiles/export-data/").json()

        self.assertEqual(body["user"]["email"], "bare@example.test")
        self.assertIsNone(body["profile"])
        self.assertIsNone(body["preferences"])
        self.assertIsNone(body["financialProfile"])
        self.assertEqual(body["accounts"], [])
        self.assertEqual(body["wallets"], [])
        self.assertEqual(body["transactions"], [])
        self.assertEqual(body["portfolios"], [])

    def test_export_without_financial_profile_or_preferences(self):
        FinancialProfile.objects.filter(user_profile=self.profile).delete()
        UserPreferences.objects.filter(user_profile=self.profile).delete()

        body = self.client.get("/api/user-profiles/export-data/").json()

        self.assertIsNone(body["financialProfile"])
        self.assertIsNone(body["preferences"])
        self.assertEqual(len(body["accounts"]), 1)
