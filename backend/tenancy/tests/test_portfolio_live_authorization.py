"""Application-level portfolio isolation through live account membership."""

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.utils import timezone
from guardian.shortcuts import assign_perm, remove_perm
from rest_framework.test import APITestCase

from assets.models import Asset
from portfolios.models import AssetAllocation, Portfolio, PortfolioSnapshot
from portfolios.services import PortfolioSyncService
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
        self.asset = Asset.objects.create(
            symbol="LIVE",
            name="Live membership asset",
            asset_type="tokenized_security",
            is_active=True,
        )
        self.alice_allocation = AssetAllocation.objects.create(
            portfolio=self.alice_portfolio,
            asset=self.asset,
            percentage="50.00",
        )
        self.alice_snapshot = PortfolioSnapshot.objects.create(
            portfolio=self.alice_portfolio,
            snapshot_date=date(2026, 9, 1),
            snapshot_reason="DAILY",
            holdings_data={"LIVE": {"quantity": "1"}},
        )
        self.preferences = UserPreferences.objects.create(
            user_profile=self.alice_profile,
            selected_account=self.alice_account,
            selected_portfolio=self.alice_portfolio,
        )

    def test_membership_removal_revokes_full_tree_despite_stale_guardian_grants(self):
        assign_perm("portfolios.view_portfolio", self.alice, self.alice_portfolio)
        assign_perm("portfolios.view_assetallocation", self.alice, self.alice_allocation)
        assign_perm("portfolios.view_portfoliosnapshot", self.alice, self.alice_snapshot)

        self.alice_account.user_profiles.remove(self.alice_profile)

        self.assertNotIn(self.alice_portfolio, Portfolio.objects.visible_to_user(self.alice))
        self.assertNotIn(self.alice_allocation, AssetAllocation.objects.visible_to_user(self.alice))
        self.assertNotIn(self.alice_snapshot, PortfolioSnapshot.objects.visible_to_user(self.alice))

        self.client.force_authenticate(self.alice)
        self.assertEqual(
            self.client.get(f"/api/portfolios/{self.alice_portfolio.uuid}/").status_code,
            404,
        )
        self.assertEqual(
            self.client.get(f"/api/asset-allocations/{self.alice_allocation.uuid}/").status_code,
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

    def test_reverse_membership_addition_reveals_preexisting_tree_without_grants(self):
        self.alice_profile.user_accounts.add(self.bob_account)
        remove_perm("portfolios.view_portfolio", self.alice, self.bob_portfolio)

        bob_allocation = AssetAllocation.objects.create(
            portfolio=self.bob_portfolio,
            asset=self.asset,
            percentage="25.00",
        )
        bob_snapshot = PortfolioSnapshot.objects.create(
            portfolio=self.bob_portfolio,
            snapshot_date=date(2026, 9, 1),
            snapshot_reason="DAILY",
        )
        remove_perm("portfolios.view_assetallocation", self.alice, bob_allocation)
        remove_perm("portfolios.view_portfoliosnapshot", self.alice, bob_snapshot)

        self.assertIn(self.bob_portfolio, Portfolio.objects.visible_to_user(self.alice))
        self.assertIn(bob_allocation, AssetAllocation.objects.visible_to_user(self.alice))
        self.assertIn(bob_snapshot, PortfolioSnapshot.objects.visible_to_user(self.alice))

    def test_staff_and_superuser_keep_global_visibility(self):
        staff = User.objects.create_user(
            email="staff@portfolio.example.test",
            password="pw-12345678",
            is_staff=True,
        )
        superuser = User.objects.create_user(
            email="super@portfolio.example.test",
            password="pw-12345678",
            is_superuser=True,
        )

        for privileged_user in (staff, superuser):
            with self.subTest(user=privileged_user.email):
                self.assertIn(self.alice_portfolio, Portfolio.objects.visible_to_user(privileged_user))
                self.assertIn(self.alice_allocation, AssetAllocation.objects.visible_to_user(privileged_user))
                self.assertIn(self.alice_snapshot, PortfolioSnapshot.objects.visible_to_user(privileged_user))


class PortfolioEndpointIsolationTest(PortfolioFixtureMixin, APITestCase):
    def setUp(self):
        self.alice, self.alice_profile, self.alice_account, self.alice_portfolio, self.alice_wallet = self.make_tenant(
            "alice"
        )
        self.bob, self.bob_profile, self.bob_account, self.bob_portfolio, self.bob_wallet = self.make_tenant("bob")
        self.asset = Asset.objects.create(
            symbol="SCOPE",
            name="Scoped asset",
            asset_type="tokenized_security",
            is_active=True,
        )
        self.alice_allocation = AssetAllocation.objects.create(
            portfolio=self.alice_portfolio,
            asset=self.asset,
            percentage="60.00",
        )
        self.bob_allocation = AssetAllocation.objects.create(
            portfolio=self.bob_portfolio,
            asset=self.asset,
            percentage="40.00",
        )
        self.alice_snapshot = PortfolioSnapshot.objects.create(
            portfolio=self.alice_portfolio,
            snapshot_date=date(2026, 9, 1),
            snapshot_reason="DAILY",
        )
        self.bob_snapshot = PortfolioSnapshot.objects.create(
            portfolio=self.bob_portfolio,
            snapshot_date=date(2026, 9, 1),
            snapshot_reason="DAILY",
        )
        self.client.force_authenticate(self.alice)

    def test_portfolio_list_filter_and_positive_nested_reads_stay_within_tenant(self):
        list_response = self.client.get("/api/portfolios/")
        self.assertEqual(list_response.status_code, 200)
        returned = {row["uuid"] for row in self.rows(list_response)}
        self.assertEqual(returned, {str(self.alice_portfolio.uuid)})

        filtered_response = self.client.get(
            "/api/portfolios/",
            {"user_profile": str(self.alice_profile.uuid)},
        )
        self.assertEqual(filtered_response.status_code, 200)
        self.assertEqual(
            {row["uuid"] for row in self.rows(filtered_response)},
            {str(self.alice_portfolio.uuid)},
        )

        allocations_response = self.client.get(f"/api/portfolios/{self.alice_portfolio.uuid}/allocations/")
        snapshots_response = self.client.get(f"/api/portfolios/{self.alice_portfolio.uuid}/snapshots/")
        self.assertEqual(allocations_response.status_code, 200)
        self.assertEqual(snapshots_response.status_code, 200)
        self.assertEqual(
            {row["uuid"] for row in self.rows(allocations_response)},
            {str(self.alice_allocation.uuid)},
        )
        self.assertEqual(
            {row["uuid"] for row in self.rows(snapshots_response)},
            {str(self.alice_snapshot.uuid)},
        )

    def test_foreign_portfolio_and_nested_actions_are_not_found(self):
        base_url = f"/api/portfolios/{self.bob_portfolio.uuid}/"
        cases = (
            ("get", base_url, None),
            ("patch", base_url, {"name": "Stolen"}),
            ("delete", base_url, None),
            ("get", f"{base_url}allocations/", None),
            ("get", f"{base_url}snapshots/", None),
            ("post", f"{base_url}add-wallet/", {"walletUuid": str(self.alice_wallet.uuid)}),
            ("post", f"{base_url}remove-wallet/", {"walletUuid": str(self.bob_wallet.uuid)}),
        )
        for method, url, payload in cases:
            with self.subTest(method=method, url=url):
                response = getattr(self.client, method)(url, payload, format="json")
                self.assertEqual(response.status_code, 404)

        self.bob_portfolio.refresh_from_db()
        self.assertTrue(self.bob_portfolio.is_active)
        self.assertEqual(self.bob_portfolio.name, "Bob Portfolio")

    def test_allocation_crud_and_bulk_delete_do_not_cross_tenants(self):
        list_response = self.client.get("/api/asset-allocations/")
        self.assertEqual(list_response.status_code, 200)
        returned = {row["uuid"] for row in self.rows(list_response)}
        self.assertIn(str(self.alice_allocation.uuid), returned)
        self.assertNotIn(str(self.bob_allocation.uuid), returned)

        foreign_url = f"/api/asset-allocations/{self.bob_allocation.uuid}/"
        for method, payload in (
            ("get", None),
            ("patch", {"percentage": "10.00"}),
            ("delete", None),
        ):
            with self.subTest(method=method):
                response = getattr(self.client, method)(foreign_url, payload, format="json")
                self.assertEqual(response.status_code, 404)

        create_response = self.client.post(
            "/api/asset-allocations/",
            {
                "portfolio": str(self.bob_portfolio.uuid),
                "asset": str(self.asset.uuid),
                "percentage": "10.00",
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, 400)
        self.assertIn("portfolio", create_response.json())

        delete_response = self.client.delete(f"/api/asset-allocations/by-portfolio/{self.bob_portfolio.uuid}/")
        self.assertEqual(delete_response.status_code, 404)
        self.assertTrue(AssetAllocation.objects.filter(pk=self.bob_allocation.pk).exists())

    def test_wallet_actions_do_not_reveal_foreign_wallet_existence(self):
        add_url = f"/api/portfolios/{self.alice_portfolio.uuid}/add-wallet/"
        own_add = self.client.post(add_url, {"walletUuid": str(self.alice_wallet.uuid)}, format="json")
        self.assertEqual(own_add.status_code, 200)
        self.assertTrue(self.alice_portfolio.wallets.filter(pk=self.alice_wallet.pk).exists())

        remove_url = f"/api/portfolios/{self.alice_portfolio.uuid}/remove-wallet/"
        own_remove = self.client.post(remove_url, {"walletUuid": str(self.alice_wallet.uuid)}, format="json")
        self.assertEqual(own_remove.status_code, 200)
        self.assertFalse(self.alice_portfolio.wallets.filter(pk=self.alice_wallet.pk).exists())

        foreign_add = self.client.post(add_url, {"walletUuid": str(self.bob_wallet.uuid)}, format="json")
        missing_add = self.client.post(add_url, {"walletUuid": str(uuid4())}, format="json")
        self.assertEqual(foreign_add.status_code, 404)
        self.assertEqual(missing_add.status_code, 404)
        self.assertIn("not found", foreign_add.json()["detail"].lower())
        self.assertIn("not found", missing_add.json()["detail"].lower())

        foreign_remove = self.client.post(remove_url, {"walletUuid": str(self.bob_wallet.uuid)}, format="json")
        missing_remove = self.client.post(remove_url, {"walletUuid": str(uuid4())}, format="json")
        self.assertEqual(foreign_remove.status_code, 404)
        self.assertEqual(missing_remove.status_code, 404)
        self.assertEqual(foreign_remove.json(), missing_remove.json())

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

    def test_legacy_foreign_wallet_snapshot_is_quarantined_from_output(self):
        self.alice_portfolio.wallets.add(self.alice_wallet, self.bob_wallet)
        self.alice_snapshot.holdings_data = {
            "SCOPE": {
                "asset_uuid": str(self.asset.uuid),
                "quantity": "17",
                "wallets": [str(self.bob_wallet.uuid)],
                "market_value": "1700",
            }
        }
        self.alice_snapshot.total_market_value = Decimal("1700")
        self.alice_snapshot.save(update_fields=["holdings_data", "total_market_value", "updated_at"])

        safe_snapshot = PortfolioSnapshot.objects.create(
            portfolio=self.alice_portfolio,
            snapshot_date=date(2026, 8, 31),
            snapshot_reason="DAILY",
            holdings_data={
                "SCOPE": {
                    "asset_uuid": str(self.asset.uuid),
                    "quantity": "2",
                    "wallets": [str(self.alice_wallet.uuid)],
                    "market_value": "200",
                }
            },
            total_market_value=Decimal("200"),
        )
        # Historical same-account holdings remain safe after a portfolio unlink.
        self.alice_portfolio.wallets.remove(self.alice_wallet)

        response = self.client.get(f"/api/portfolios/{self.alice_portfolio.uuid}/snapshots/")

        self.assertEqual(response.status_code, 200)
        rows = {row["uuid"]: row for row in self.rows(response)}
        contaminated_row = rows[str(self.alice_snapshot.uuid)]
        self.assertEqual(contaminated_row["holdingsData"], {})
        self.assertIsNone(contaminated_row["totalMarketValue"])
        self.assertFalse(contaminated_row["hasValueData"])
        self.assertNotIn(str(self.bob_wallet.uuid), response.content.decode())

        safe_row = rows[str(safe_snapshot.uuid)]
        self.assertEqual(safe_row["holdingsData"]["SCOPE"]["quantity"], "2")
        self.assertEqual(safe_row["holdingsData"]["SCOPE"]["wallets"], [str(self.alice_wallet.uuid)])
        self.assertEqual(safe_row["totalMarketValue"], "200.000000000000000000")
        self.assertTrue(safe_row["hasValueData"])

    def test_sync_replaces_untrusted_valued_snapshot_even_when_rebuild_is_empty(self):
        self.alice_portfolio.wallets.add(self.alice_wallet, self.bob_wallet)
        self.alice_snapshot.holdings_data = {
            "SCOPE": {
                "quantity": "17",
                "wallets": [str(self.bob_wallet.uuid)],
            }
        }
        self.alice_snapshot.total_market_value = Decimal("1700")
        self.alice_snapshot.save(update_fields=["holdings_data", "total_market_value", "updated_at"])

        snapshot_at = timezone.make_aware(datetime(2026, 9, 1, 12, 0, 0))
        with patch.object(PortfolioSyncService, "_aggregate_holdings", return_value=({}, Decimal("0"))) as aggregate:
            changed = PortfolioSyncService._create_snapshot_for_date(
                self.alice_portfolio,
                self.alice_portfolio.account_wallets(),
                snapshot_at,
            )

        self.assertTrue(changed)
        aggregate.assert_called_once()
        self.alice_snapshot.refresh_from_db()
        self.assertEqual(self.alice_snapshot.holdings_data, {})
        self.assertIsNone(self.alice_snapshot.total_market_value)

    def test_daily_sync_preserves_manual_snapshot_on_same_date(self):
        self.alice_portfolio.wallets.add(self.alice_wallet)
        manual_snapshot = PortfolioSnapshot.objects.create(
            portfolio=self.alice_portfolio,
            snapshot_date=date(2026, 9, 2),
            snapshot_reason="MANUAL",
            holdings_data={
                "SCOPE": {
                    "quantity": "17",
                    "wallets": [str(self.bob_wallet.uuid)],
                }
            },
            total_market_value=Decimal("1700"),
        )

        snapshot_at = timezone.make_aware(datetime(2026, 9, 2, 12, 0, 0))
        with patch.object(PortfolioSyncService, "_aggregate_holdings", return_value=({}, Decimal("0"))):
            changed = PortfolioSyncService._create_snapshot_for_date(
                self.alice_portfolio,
                self.alice_portfolio.account_wallets(),
                snapshot_at,
            )

        self.assertTrue(changed)
        manual_snapshot.refresh_from_db()
        self.assertEqual(manual_snapshot.total_market_value, Decimal("1700"))
        self.assertEqual(manual_snapshot.holdings_data["SCOPE"]["wallets"], [str(self.bob_wallet.uuid)])
        daily_snapshot = PortfolioSnapshot.objects.get(
            portfolio=self.alice_portfolio,
            snapshot_date=date(2026, 9, 2),
            snapshot_reason="DAILY",
        )
        self.assertEqual(daily_snapshot.holdings_data, {})
        self.assertIsNone(daily_snapshot.total_market_value)
