from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from shared.views import AuthenticatedReadOnlyViewSet
from tokens.models import ShareToken
from tokens.serializers import ShareTokenListSerializer
from tokens.services import MarketDataService, TradingOrderService


class TradingTokenViewSet(AuthenticatedReadOnlyViewSet):

    serializer_class = ShareTokenListSerializer
    ordering = ["name"]
    ordering_fields = ["name", "symbol", "created_at"]

    def get_queryset(self):
        return ShareToken.objects.with_company().deployed().with_market_summary()

    @action(detail=True, methods=["get"], url_path="market-data")
    def market_data(self, request, uuid=None):
        token = self.get_object()
        market_data = MarketDataService.get_market_data(token)
        return Response(market_data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get"], url_path="order-book")
    def order_book(self, request, uuid=None):
        token = self.get_object()
        order_book = TradingOrderService.get_order_book(token)
        return Response(order_book, status=status.HTTP_200_OK)
