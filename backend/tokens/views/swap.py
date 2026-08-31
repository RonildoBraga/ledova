import logging

from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from shared.views import AuthenticatedListViewSet
from tokens.models import SwapOrder
from tokens.serializers.swap_order import SwapOrderListSerializer
from tokens.services import AtomicSwapService

logger = logging.getLogger(__name__)


class SwapOrderViewSet(AuthenticatedListViewSet):

    serializer_class = SwapOrderListSerializer
    ordering = ["-created_at"]
    ordering_fields = ["created_at", "status"]

    def get_queryset(self):
        return SwapOrder.objects.select_related(
            "share_token",
            "payment_token",
            "sell_order",
            "buy_order",
        )

    def list(self, request, *args, **kwargs):
        wallet_address = request.query_params.get("wallet_address")
        if not wallet_address:
            raise ValidationError({"wallet_address": "This query parameter is required."})

        atomic_swap_service = AtomicSwapService()
        swap_orders = atomic_swap_service.get_pending_swaps_for_address(wallet_address)

        serializer = self.get_serializer(swap_orders, many=True)
        return Response(serializer.data)
