from unittest.mock import patch

from django.db import OperationalError
from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from feature_flags.middleware import TRADING_WRITE_PREFIXES, TradingFeatureFlagMiddleware
from feature_flags.models import FeatureFlag


class TradingFeatureFlagMiddlewareTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.downstream_calls = 0

        def downstream(_request):
            self.downstream_calls += 1
            return HttpResponse("ok")

        self.middleware = TradingFeatureFlagMiddleware(downstream)

    def test_missing_flag_blocks_every_sensitive_prefix(self):
        for path in TRADING_WRITE_PREFIXES:
            with self.subTest(path=path):
                response = self.middleware(self.factory.get(path))
                self.assertEqual(response.status_code, 403)
        self.assertEqual(self.downstream_calls, 0)

    def test_disabled_flag_blocks_sensitive_prefix(self):
        FeatureFlag.objects.create(name="trading_enabled", enabled=False)
        response = self.middleware(self.factory.post("/api/v1/trading/orders/"))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.downstream_calls, 0)

    def test_enabled_flag_preserves_original_route(self):
        FeatureFlag.objects.create(name="trading_enabled", enabled=True)
        response = self.middleware(self.factory.post("/api/v1/trading/orders/"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.downstream_calls, 1)

    def test_read_only_market_and_unrelated_routes_are_not_gated(self):
        for path in ("/api/v1/trading/tokens/", "/api/v1/trading/stablecoins/", "/api/v1/companies/"):
            with self.subTest(path=path):
                response = self.middleware(self.factory.get(path))
                self.assertEqual(response.status_code, 200)
        self.assertEqual(self.downstream_calls, 3)

    def test_database_error_fails_closed(self):
        with patch("feature_flags.middleware.FeatureFlag.objects.filter", side_effect=OperationalError):
            response = self.middleware(self.factory.get("/api/v1/trading/events/stream/"))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.downstream_calls, 0)
