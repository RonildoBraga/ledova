from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from shared.views import AuthenticatedReadOnlyViewSet
from tokens.serializers import ShareTokenListSerializer
from tokens.services import MarketDataService, TradingOrderService
from tokens.services.market_data_service import list_market_tokens


class TradingTokenViewSet(AuthenticatedReadOnlyViewSet):

    serializer_class = ShareTokenListSerializer
    ordering = ["name"]
    ordering_fields = ["name", "symbol", "created_at"]

    def get_queryset(self):
        return list_market_tokens(self.request.user)

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
