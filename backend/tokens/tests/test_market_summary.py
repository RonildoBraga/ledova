from decimal import Decimal

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APITestCase

from feature_flags.models import FeatureFlag
from shared.tests.tenants import make_eligible, make_tenant, open_to_investors
from tokens.models import ShareToken, SwapOrder

DIRECTORY = "/api/v1/directory/tokens/"
TRADING = "/api/v1/trading/tokens/"


class MarketSummaryTest(APITestCase):
    def setUp(self):
        FeatureFlag.objects.update_or_create(name="trading_enabled", defaults={"enabled": True})
        self.alice = make_tenant("alice")
        self.bob = make_tenant("bob")
        make_eligible(self.alice)
        open_to_investors(self.alice)
        open_to_investors(self.bob)
        SwapOrder.objects.filter(pk=self.alice.swap.pk).update(status="completed", completed_at=timezone.now())
        self.client.force_authenticate(self.alice.user)

    @staticmethod
    def rows(response):
        body = response.json()
        return {row["uuid"]: row for row in body.get("results", body)}

    def test_queryset_annotations_match_the_per_row_queries(self):
        summary = {token.uuid: token for token in ShareToken.objects.with_market_summary()}
        traded = summary[self.alice.deployed_token.uuid]
        self.assertEqual((traded.best_bid, traded.best_ask), (Decimal("1.50"), Decimal("1.50")))
        self.assertEqual((traded.last_trade_payment_amount, traded.last_trade_share_amount), (1500, 10))
        self.assertEqual(traded.last_trade_decimals, 2)

        untraded = summary[self.bob.deployed_token.uuid]
        self.assertIsNone(untraded.last_trade_share_amount)
        draft = summary[self.alice.token.uuid]
        self.assertEqual((draft.best_bid, draft.best_ask, draft.last_trade_share_amount), (None, None, None))

    def test_lists_expose_market_fields_without_per_row_queries(self):
        for position, path in enumerate((TRADING, DIRECTORY, "/api/v1/tokens/")):
            with self.subTest(path=path):
                self.client.get(path)
                with CaptureQueriesContext(connection) as before:
                    response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                rows = self.rows(response)
                traded = rows[str(self.alice.deployed_token.uuid)]
                self.assertEqual((traded["lastPrice"], traded["bestBid"], traded["bestAsk"]), ("1.5", "1.50", "1.50"))

                extra = [make_tenant(f"extra-{position}-{index}") for index in range(2)]
                for tenant in extra:
                    open_to_investors(tenant)
                self.client.force_authenticate(self.alice.user)
                with CaptureQueriesContext(connection) as after:
                    response = self.client.get(path)
                self.assertEqual(len(after), len(before), [query["sql"] for query in after])
                if path in (TRADING, DIRECTORY):
                    self.assertEqual(len(self.rows(response)), len(rows) + 2)
                    untraded = self.rows(response)[str(extra[0].deployed_token.uuid)]
                    self.assertEqual((untraded["lastPrice"], untraded["bestBid"]), (None, "1.50"))
                else:
                    self.assertEqual(set(self.rows(response)), {str(self.alice.token.uuid), str(traded["uuid"])})
                    draft = self.rows(response)[str(self.alice.token.uuid)]
                    self.assertEqual((draft["lastPrice"], draft["bestBid"], draft["bestAsk"]), (None, None, None))

    def test_market_data_endpoint_keeps_its_keys(self):
        response = self.client.get(f"{TRADING}{self.alice.deployed_token.uuid}/market-data/")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["lastTradePrice"], "1.5")
        self.assertEqual((body["bestBid"], body["bestAsk"], body["midpointPrice"]), ("1.50", "1.50", "1.50"))
        self.assertEqual(body["lastTrade"]["paymentAmount"], "15")
        self.assertEqual(body["lastTrade"]["paymentToken"], "TUSD")

    def test_directory_list_keeps_the_market_summary_keys(self):
        response = self.client.get(DIRECTORY)
        row = self.rows(response)[str(self.alice.deployed_token.uuid)]
        self.assertEqual({"lastPrice", "bestBid", "bestAsk"} & set(row), {"lastPrice", "bestBid", "bestAsk"})
        self.assertEqual((row["lastPrice"], row["bestBid"], row["bestAsk"]), ("1.5", "1.50", "1.50"))
