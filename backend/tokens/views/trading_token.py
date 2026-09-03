import logging
from decimal import Decimal

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from assets.models import Asset
from integrations.blockchain.factory import get_blockchain_client
from shared.constants import EVM_BLOCKCHAINS
from shared.views import AuthenticatedReadOnlyViewSet
from tokens.models import ShareToken, Stablecoin
from tokens.serializers import ShareTokenListSerializer, StablecoinListSerializer
from tokens.serializers.stablecoin import StablecoinTransparencySerializer
from tokens.services import MarketDataService, TradingOrderService

logger = logging.getLogger(__name__)


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


def _multi_chain_supply(symbol: str) -> tuple[Decimal | None, list[dict]]:
    """Sum the on-chain supply of every active EVM deployment; None when no chain answered."""
    asset = Asset.objects.filter(symbol=symbol).first()
    if not asset:
        return None, []

    deployments = asset.chain_deployments.filter(is_active=True, chain__in=EVM_BLOCKCHAINS)
    if not deployments.exists():
        return None, []

    total = Decimal("0")
    any_success = False
    chain_data = []

    for deployment in deployments:
        entry = {
            "chain": deployment.chain,
            "contract_address": deployment.contract_address,
            "decimals": deployment.decimals,
            "supply": None,
        }
        try:
            client = get_blockchain_client(deployment.chain)
            supply = client.get_total_supply(deployment.contract_address, deployment.decimals)
            total += supply
            any_success = True
            entry["supply"] = str(supply)
        except Exception:
            logger.warning(f"Failed to fetch supply for {symbol} on {deployment.chain}")
        chain_data.append(entry)

    return (total if any_success else None), chain_data


class TradingStablecoinViewSet(AuthenticatedReadOnlyViewSet):

    serializer_class = StablecoinListSerializer
    ordering = ["symbol"]
    ordering_fields = ["symbol", "name", "created_at"]

    def get_queryset(self):
        return Stablecoin.objects.filter(is_active=True)

    @action(detail=True, methods=["get"], url_path="transparency")
    def transparency(self, request, uuid=None):
        stablecoin = self.get_object()
        total_supply, chain_deployments = _multi_chain_supply(stablecoin.symbol)

        serializer = StablecoinTransparencySerializer(
            stablecoin,
            context={
                "total_supply": str(total_supply) if total_supply is not None else None,
                "chain_deployments": chain_deployments,
            },
        )
        return Response(serializer.data, status=status.HTTP_200_OK)
