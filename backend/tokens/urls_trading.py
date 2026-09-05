from django.urls import path
from rest_framework.routers import DefaultRouter

from tokens.views import (
    SwapOrderViewSet,
    TradingOrderViewSet,
    TradingTokenViewSet,
    TradingTransferViewSet,
    TradingWalletViewSet,
)
from tokens.views.trading_events import trading_events_stream
from whitelist.views import WhitelistStatusView

app_name = "trading"

router = DefaultRouter()
router.register(r"tokens", TradingTokenViewSet, basename="tokens")
router.register(r"orders", TradingOrderViewSet, basename="orders")
router.register(r"wallets", TradingWalletViewSet, basename="wallets")
router.register(r"transfers", TradingTransferViewSet, basename="transfers")
router.register(r"swaps", SwapOrderViewSet, basename="swaps")

urlpatterns = router.urls + [
    path("whitelist/<str:address>/status/", WhitelistStatusView.as_view(), name="whitelist-status"),
    path("events/stream/", trading_events_stream, name="trading-events-stream"),
]
