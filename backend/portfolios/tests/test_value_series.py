from datetime import datetime, time, timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework.test import APITestCase

from assets.models import Asset, AssetSnapshot
from portfolios.services import portfolio_value_series
from portfolios.tests.test_live_authorization import PortfolioFixtureMixin
from wallets.models import Holding, HoldingSnapshot, Wallet


def at(day, hour=0):
    return timezone.make_aware(datetime.combine(day, time(hour=hour)))


class ValueSeriesFixtureMixin(PortfolioFixtureMixin):

    def day(self, number):
        return timezone.now().date() - timedelta(days=22 - number)

    def build_scenario(self):
        self.user, _, self.account, self.portfolio, self.wallet_1 = self.make_tenant("alice")
        self.wallet_2 = Wallet.objects.create(user_account=self.account, address="0x" + "2" * 40, chain="ethereum")
        self.portfolio.wallets.add(self.wallet_1, self.wallet_2)
        self.aaa = Asset.objects.create(symbol="AAA", name="AAA", asset_type="erc20_token", is_verified=True)
        self.bbb = Asset.objects.create(symbol="BBB", name="BBB", asset_type="erc20_token", is_verified=True)
        quarantined = Asset.objects.create(symbol="QUAR", name="QUAR", asset_type="erc20_token", is_verified=False)
        for wallet, asset, quantity, number in (
            (self.wallet_1, self.aaa, "1", 1),
            (self.wallet_1, self.aaa, "2", 5),
            (self.wallet_1, self.bbb, "10", 1),
            (self.wallet_2, self.aaa, "3", 20),
            (self.wallet_2, quarantined, "99", 1),
        ):
            holding, _ = Holding.objects.get_or_create(wallet=wallet, asset=asset, defaults={"quantity": quantity})
            HoldingSnapshot.objects.create(
                holding=holding, quantity=Decimal(quantity), snapshot_date=self.day(number), snapshot_reason="DAILY"
            )
        for number in range(1, 23):
            self.price(self.aaa, 100 + number, self.day(number))
        self.price(self.aaa, 999, self.day(10), hour=12)
        self.price(self.bbb, 5, self.day(3))
        self.price(self.bbb, 7, self.day(15))

    @staticmethod
    def price(asset, price, day, hour=0):
        AssetSnapshot.objects.create(asset=asset, price=Decimal(price), source_timestamp=at(day, hour), data_source="t")


class PortfolioValueSeriesTest(ValueSeriesFixtureMixin, APITestCase):
    def setUp(self):
        self.build_scenario()

    def point(self, points, number):
        return next(point for point in points if point["snapshot_date"] == self.day(number))

    @staticmethod
    def values(point):
        return {
            symbol: (Decimal(entry["quantity"]), Decimal(entry["market_value"]) if "market_value" in entry else None)
            for symbol, entry in point["holdings_data"].items()
        }

    def test_hand_computed_series(self):
        points = portfolio_value_series(self.portfolio)

        self.assertEqual([point["snapshot_date"] for point in points], [self.day(n) for n in range(1, 23)])
        self.assertEqual(
            self.values(self.point(points, 1)), {"AAA": (Decimal("1"), Decimal("101")), "BBB": (Decimal("10"), None)}
        )
        self.assertEqual(self.point(points, 1)["total_market_value"], Decimal("101"))
        self.assertEqual(
            self.values(self.point(points, 3)),
            {"AAA": (Decimal("1"), Decimal("103")), "BBB": (Decimal("10"), Decimal("50"))},
        )
        self.assertEqual(self.point(points, 4)["total_market_value"], Decimal("154"))
        self.assertEqual(
            self.values(self.point(points, 5)),
            {"AAA": (Decimal("2"), Decimal("210")), "BBB": (Decimal("10"), Decimal("50"))},
        )
        self.assertEqual(self.point(points, 10)["holdings_data"]["AAA"]["price"], "999.000000000000000000")
        self.assertEqual(self.point(points, 11)["total_market_value"], Decimal("272"))
        self.assertEqual(
            self.values(self.point(points, 15)),
            {"AAA": (Decimal("2"), Decimal("230")), "BBB": (Decimal("10"), Decimal("70"))},
        )
        self.assertEqual(
            self.values(self.point(points, 20)),
            {"AAA": (Decimal("5"), Decimal("600")), "BBB": (Decimal("10"), Decimal("70"))},
        )
        self.assertEqual(
            sorted(self.point(points, 20)["holdings_data"]["AAA"]["wallets"]),
            sorted([str(self.wallet_1.uuid), str(self.wallet_2.uuid)]),
        )
        self.assertEqual(self.point(points, 19)["holdings_data"]["AAA"]["wallets"], [str(self.wallet_1.uuid)])
        self.assertEqual(self.point(points, 22)["total_market_value"], Decimal("680"))
        self.assertEqual(self.point(points, 22)["snapshot_date"], timezone.now().date())
        self.assertEqual(self.point(points, 22)["holdings_data"]["AAA"]["asset_uuid"], str(self.aaa.uuid))
        self.assertTrue(all(point["has_value_data"] for point in points))
        self.assertTrue(all("QUAR" not in point["holdings_data"] for point in points))

    def test_range_clipping_and_nothing_before_the_first_holding_snapshot(self):
        self.assertEqual(portfolio_value_series(self.portfolio, end_date=self.day(0)), [])
        self.assertEqual(portfolio_value_series(self.portfolio, start_date=self.day(23)), [])
        self.assertEqual(
            [p["snapshot_date"] for p in portfolio_value_series(self.portfolio, self.day(-5), self.day(2))],
            [self.day(1), self.day(2)],
        )
        clipped = portfolio_value_series(self.portfolio, self.day(21), self.day(40))
        self.assertEqual([p["snapshot_date"] for p in clipped], [self.day(21), self.day(22)])
        self.assertEqual(self.values(clipped[0])["AAA"], (Decimal("5"), Decimal("605")))

    def test_unpriced_holdings_have_a_null_total(self):
        AssetSnapshot.objects.all().delete()

        point = self.point(portfolio_value_series(self.portfolio), 22)

        self.assertEqual(set(point["holdings_data"]["AAA"]), {"asset_uuid", "quantity", "wallets", "per_chain"})
        self.assertIsNone(point["total_market_value"])
        self.assertFalse(point["has_value_data"])

    def test_quarantined_and_inactive_assets_never_reach_holdings_data(self):
        for symbol, flags in {
            "QUARANTINED": dict(is_active=True, is_verified=False),
            "SWITCHEDOFF": dict(is_active=False, is_verified=True),
        }.items():
            asset = Asset.objects.create(symbol=symbol, name=symbol, asset_type="erc20_token", **flags)
            holding = Holding.objects.create(wallet=self.wallet_1, asset=asset, quantity=Decimal("7"))
            HoldingSnapshot.objects.create(holding=holding, snapshot_date=self.day(22), quantity=Decimal("7"))

        self.assertEqual(set(self.point(portfolio_value_series(self.portfolio), 22)["holdings_data"]), {"AAA", "BBB"})

    def test_foreign_and_unlinked_wallets_do_not_count(self):
        _, _, bob_account, _, bob_wallet = self.make_tenant("bob")
        holding = Holding.objects.create(wallet=bob_wallet, asset=self.aaa, quantity=Decimal("50"))
        HoldingSnapshot.objects.create(holding=holding, snapshot_date=self.day(1), quantity=Decimal("50"))
        self.portfolio.wallets.add(bob_wallet)
        self.portfolio.wallets.remove(self.wallet_2)

        point = self.point(portfolio_value_series(self.portfolio), 22)

        self.assertEqual(self.values(point)["AAA"], (Decimal("2"), Decimal("244")))
        self.assertEqual(point["holdings_data"]["AAA"]["wallets"], [str(self.wallet_1.uuid)])


class PortfolioSnapshotsEndpointTest(ValueSeriesFixtureMixin, APITestCase):
    def setUp(self):
        self.build_scenario()
        self.client.force_authenticate(self.user)
        self.url = f"/api/portfolios/{self.portfolio.uuid}/snapshots/"

    def test_row_shape_the_clients_read(self):
        response = self.client.get(self.url, {"order_by": "snapshot_date", "snapshot_reason": "DAILY"})

        self.assertEqual(response.status_code, 200)
        rows = response.json()
        self.assertEqual(len(rows), 22)
        first, last = rows[0], rows[-1]
        self.assertEqual(
            set(first),
            {
                "uuid",
                "portfolio",
                "portfolioName",
                "accountId",
                "holdingsData",
                "totalMarketValue",
                "hasValueData",
                "snapshotDate",
                "snapshotReason",
                "createdAt",
                "updatedAt",
            },
        )
        self.assertEqual(first["snapshotDate"], self.day(1).isoformat())
        self.assertEqual(last["snapshotDate"], timezone.now().date().isoformat())
        self.assertEqual(first["uuid"], f"{self.portfolio.uuid}:{self.day(1).isoformat()}")
        self.assertEqual(first["portfolio"], str(self.portfolio.uuid))
        self.assertEqual(first["portfolioName"], self.portfolio.name)
        self.assertEqual(first["accountId"], str(self.account.uuid))
        self.assertEqual(first["snapshotReason"], "DAILY")
        self.assertEqual(first["totalMarketValue"], "101.000000000000000000")
        self.assertTrue(first["hasValueData"])
        self.assertEqual(
            set(first["holdingsData"]["AAA"]), {"assetUuid", "quantity", "wallets", "price", "marketValue", "perChain"}
        )
        self.assertEqual(set(first["holdingsData"]["BBB"]), {"assetUuid", "quantity", "wallets", "perChain"})
        self.assertEqual(first["holdingsData"]["AAA"]["quantity"], "1.000000000000000000")
        self.assertEqual(first["holdingsData"]["AAA"]["price"], "101.000000000000000000")
        self.assertEqual(Decimal(first["holdingsData"]["AAA"]["marketValue"]), Decimal("101"))
        self.assertIsInstance(first["holdingsData"]["AAA"]["marketValue"], str)
        self.assertEqual(first["holdingsData"]["AAA"]["wallets"], [str(self.wallet_1.uuid)])
        self.assertEqual(last["totalMarketValue"], "680.000000000000000000")

    def test_default_order_is_newest_first_and_max_points_samples_evenly(self):
        newest_first = self.client.get(self.url).json()
        self.assertEqual(
            [row["snapshotDate"] for row in newest_first][:2], [self.day(22).isoformat(), self.day(21).isoformat()]
        )

        sampled = self.client.get(self.url, {"order_by": "snapshot_date", "max_points": 4}).json()
        self.assertEqual([row["snapshotDate"] for row in sampled], [self.day(n).isoformat() for n in (1, 8, 15, 22)])

        bounded = self.client.get(
            self.url, {"start_date": self.day(2).isoformat(), "end_date": self.day(3).isoformat()}
        )
        self.assertEqual(
            [row["snapshotDate"] for row in bounded.json()], [self.day(3).isoformat(), self.day(2).isoformat()]
        )

    def test_unpriced_days_serialise_a_null_total(self):
        AssetSnapshot.objects.all().delete()
        row = self.client.get(self.url).json()[0]
        self.assertIsNone(row["totalMarketValue"])
        self.assertFalse(row["hasValueData"])
        self.assertEqual(row["holdingsData"]["AAA"]["quantity"], "5.000000000000000000")

    def test_malformed_dates_are_400_and_foreign_portfolios_404(self):
        self.assertEqual(self.client.get(self.url, {"start_date": "yesterday"}).status_code, 400)
        self.assertEqual(self.client.get(self.url, {"end_date": "2026-13-01"}).status_code, 400)

        bob, _, _, bob_portfolio, _ = self.make_tenant("bob")
        self.assertEqual(self.client.get(f"/api/portfolios/{bob_portfolio.uuid}/snapshots/").status_code, 404)
        self.client.force_authenticate(bob)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.get(f"/api/portfolios/{bob_portfolio.uuid}/snapshots/").status_code, 200)


class PortfolioNetworkHistoryTest(ValueSeriesFixtureMixin, APITestCase):
    def setUp(self):
        self.build_scenario()
        self.base_wallet = Wallet.objects.create(user_account=self.account, address=self.wallet_1.address, chain="base")
        self.portfolio.wallets.add(self.base_wallet)
        self.base_holding = Holding.objects.create(wallet=self.base_wallet, asset=self.aaa, quantity=Decimal("90"))
        for number, quantity in ((5, "4"), (20, "0")):
            HoldingSnapshot.objects.create(
                holding=self.base_holding, quantity=Decimal(quantity), snapshot_date=self.day(number)
            )
        self.client.force_authenticate(self.user)
        self.url = f"/api/portfolios/{self.portfolio.uuid}/snapshots/"

    def row(self, number):
        response = self.client.get(self.url, {"start_date": self.day(number), "end_date": self.day(number)})
        self.assertEqual(response.status_code, 200)
        return response.json()[0]

    def test_same_address_retains_each_networks_historical_quantity_and_wallet(self):
        before = self.row(4)["holdingsData"]["AAA"]
        self.assertEqual([entry["chain"] for entry in before["perChain"]], ["ethereum"])

        point = self.row(5)
        self.assertEqual(set(point["holdingsData"]), {"AAA", "BBB"})
        asset = point["holdingsData"]["AAA"]
        self.assertEqual(asset["assetUuid"], str(self.aaa.uuid))
        self.assertEqual(Decimal(asset["quantity"]), Decimal("6"))
        self.assertEqual(Decimal(asset["marketValue"]), Decimal("630"))
        self.assertEqual(Decimal(point["totalMarketValue"]), Decimal("680"))
        self.assertEqual([entry["chain"] for entry in asset["perChain"]], ["base", "ethereum"])
        base, ethereum = asset["perChain"]
        self.assertEqual(base["wallets"], [str(self.base_wallet.uuid)])
        self.assertEqual(ethereum["wallets"], [str(self.wallet_1.uuid)])
        self.assertEqual(Decimal(base["quantity"]), Decimal("4"))
        self.assertEqual(Decimal(ethereum["quantity"]), Decimal("2"))
        self.assertEqual(Decimal(base["marketValue"]), Decimal("420"))
        self.assertEqual(Decimal(ethereum["marketValue"]), Decimal("210"))

        carried = {entry["chain"]: entry for entry in self.row(19)["holdingsData"]["AAA"]["perChain"]}
        self.assertEqual(Decimal(carried["base"]["quantity"]), Decimal("4"))
        self.assertEqual(Decimal(carried["base"]["marketValue"]), Decimal("476"))

        emptied = {entry["chain"]: entry for entry in self.row(20)["holdingsData"]["AAA"]["perChain"]}
        self.assertEqual(Decimal(emptied["base"]["quantity"]), Decimal("0"))
        self.assertEqual(Decimal(emptied["base"]["marketValue"]), Decimal("0"))
        self.assertEqual(Decimal(emptied["ethereum"]["quantity"]), Decimal("5"))
        self.assertCountEqual(emptied["ethereum"]["wallets"], [str(self.wallet_1.uuid), str(self.wallet_2.uuid)])

    def test_unpriced_network_slices_keep_quantity_without_inventing_value(self):
        AssetSnapshot.objects.all().delete()

        point = self.row(5)

        self.assertIsNone(point["totalMarketValue"])
        self.assertFalse(point["hasValueData"])
        self.assertNotIn("marketValue", point["holdingsData"]["AAA"])
        self.assertEqual(
            [(entry["chain"], Decimal(entry["quantity"])) for entry in point["holdingsData"]["AAA"]["perChain"]],
            [("base", Decimal("4")), ("ethereum", Decimal("2"))],
        )
        for entry in point["holdingsData"]["AAA"]["perChain"]:
            self.assertNotIn("marketValue", entry)

    def test_foreign_same_address_and_unlinked_network_are_excluded(self):
        _, _, account, _, _ = self.make_tenant("bob")
        foreign = Wallet.objects.create(user_account=account, address=self.wallet_1.address, chain="base")
        holding = Holding.objects.create(wallet=foreign, asset=self.aaa, quantity=Decimal("50"))
        HoldingSnapshot.objects.create(holding=holding, quantity=Decimal("50"), snapshot_date=self.day(1))
        self.portfolio.wallets.add(foreign)
        self.assertEqual(Decimal(self.row(5)["holdingsData"]["AAA"]["quantity"]), Decimal("6"))

        self.portfolio.wallets.remove(self.base_wallet)

        asset = self.row(5)["holdingsData"]["AAA"]
        self.assertEqual(Decimal(asset["quantity"]), Decimal("2"))
        self.assertEqual([entry["chain"] for entry in asset["perChain"]], ["ethereum"])
        self.assertEqual(asset["perChain"][0]["wallets"], [str(self.wallet_1.uuid)])


class SharesOnlyPortfolioTest(ValueSeriesFixtureMixin, APITestCase):
    def setUp(self):
        self.user, _, self.account, self.portfolio, self.wallet = self.make_tenant("shareholder")
        self.portfolio.wallets.add(self.wallet)
        self.share = Asset.objects.create(
            symbol="ORD", name="Acme Ordinary", asset_type="tokenized_security", decimals=0, is_verified=True
        )
        holding = Holding.objects.create(wallet=self.wallet, asset=self.share, quantity=Decimal("250"))
        HoldingSnapshot.objects.create(
            holding=holding, quantity=Decimal("250"), snapshot_date=self.day(20), snapshot_reason="DAILY"
        )

    def test_a_shares_only_series_stops_being_empty_and_carries_a_null_total(self):
        points = portfolio_value_series(self.portfolio)

        self.assertEqual([point["snapshot_date"] for point in points], [self.day(20), self.day(21), self.day(22)])
        self.assertEqual({point["total_market_value"] for point in points}, {None})
        self.assertEqual({point["has_value_data"] for point in points}, {False})
        entry = points[0]["holdings_data"]["ORD"]
        self.assertEqual(entry["quantity"], "250.000000000000000000")
        self.assertNotIn("market_value", entry)

    def test_the_holdings_route_reports_the_share_count_with_no_market_value(self):
        self.client.force_authenticate(self.user)

        response = self.client.get(f"/api/wallets/{self.wallet.uuid}/holdings/")

        self.assertEqual(response.status_code, 200)
        row = next(row for row in response.json() if row["assetSymbol"] == "ORD")
        self.assertEqual(row["quantity"], "250.000000000000000000")
        self.assertIsNone(row["marketValue"])
