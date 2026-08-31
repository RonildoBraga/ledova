from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from shared.views import AuthenticatedReadOnlyViewSet
from tokens.models import ShareToken, Stablecoin
from tokens.serializers import ShareTokenListSerializer, StablecoinListSerializer
from tokens.serializers.stablecoin import StablecoinTransparencySerializer
from tokens.services import MarketDataService, TradingOrderService
from tokens.services.base_token_service import get_multi_chain_supply


class TradingTokenViewSet(AuthenticatedReadOnlyViewSet):

    serializer_class = ShareTokenListSerializer
    ordering = ["name"]
    ordering_fields = ["name", "symbol", "created_at"]

    def get_queryset(self):
        return ShareToken.objects.with_company().deployed()

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


class TradingStablecoinViewSet(AuthenticatedReadOnlyViewSet):

    serializer_class = StablecoinListSerializer
    ordering = ["symbol"]
    ordering_fields = ["symbol", "name", "created_at"]

    def get_queryset(self):
        return Stablecoin.objects.filter(is_active=True)

    @action(detail=True, methods=["get"], url_path="transparency")
    def transparency(self, request, uuid=None):
        stablecoin = self.get_object()
        total_supply, chain_deployments = get_multi_chain_supply(stablecoin.symbol)

        serializer = StablecoinTransparencySerializer(
            stablecoin,
            context={
                "total_supply": str(total_supply) if total_supply is not None else None,
                "chain_deployments": chain_deployments,
            },
        )
        return Response(serializer.data, status=status.HTTP_200_OK)
