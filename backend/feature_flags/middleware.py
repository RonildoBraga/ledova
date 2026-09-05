from django.db import OperationalError, ProgrammingError
from django.http import JsonResponse

from feature_flags.models import FeatureFlag

TRADING_WRITE_PREFIXES = (
    "/api/v1/trading/orders/",
    "/api/v1/trading/wallets/",
    "/api/v1/trading/transfers/",
    "/api/v1/trading/swaps/",
    "/api/v1/trading/events/",
)


class TradingFeatureFlagMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.path.startswith(TRADING_WRITE_PREFIXES):
            return self.get_response(request)

        try:
            enabled = FeatureFlag.objects.filter(name="trading_enabled", enabled=True).exists()
        except (OperationalError, ProgrammingError):
            enabled = False

        if not enabled:
            return JsonResponse({"detail": "Trading is disabled."}, status=403)
        return self.get_response(request)
