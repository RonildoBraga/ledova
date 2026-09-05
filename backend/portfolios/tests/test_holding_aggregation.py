"""Portfolio snapshots aggregate only holdings of active, verified assets."""

from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from assets.models import Asset
from portfolios.services import PortfolioSyncService
from portfolios.tests.test_live_authorization import PortfolioFixtureMixin
from wallets.models import Holding, HoldingSnapshot


class HoldingAggregationTest(PortfolioFixtureMixin, TestCase):
    def test_quarantined_and_inactive_assets_never_reach_holdings_data(self):
        _, _, _, _, wallet = self.make_tenant("alice")
        rows = {
            "VISIBLE": dict(is_active=True, is_verified=True),
            "QUARANTINED": dict(is_active=True, is_verified=False),
            "SWITCHEDOFF": dict(is_active=False, is_verified=True),
        }
        for symbol, flags in rows.items():
            asset = Asset.objects.create(symbol=symbol, name=symbol, asset_type="erc20_token", **flags)
            holding = Holding.objects.create(wallet=wallet, asset=asset, quantity=Decimal("7"))
            HoldingSnapshot.objects.create(holding=holding, snapshot_date=date(2026, 9, 1), quantity=Decimal("7"))

        holdings_data, total = PortfolioSyncService._aggregate_holdings([wallet], timezone.now())

        self.assertEqual(list(holdings_data), ["VISIBLE"])
        self.assertEqual(Decimal(holdings_data["VISIBLE"]["quantity"]), Decimal("7"))
        self.assertEqual(total, Decimal("0"))  # no price snapshot for VISIBLE
