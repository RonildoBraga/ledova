from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from shared.views import AuthenticatedListViewSet
from tokens.models import SwapOrder
from tokens.serializers.swap_order import SwapOrderListSerializer
from tokens.services import AtomicSwapService
from tokens.trading_wallet_access import resolve_verified_evm_wallets


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

        authorized_wallets = resolve_verified_evm_wallets(request.user, [wallet_address])

        atomic_swap_service = AtomicSwapService()
        swap_orders = atomic_swap_service.get_pending_swaps_for_wallet_ids(authorized_wallets.wallet_ids)
        swap_orders = self.filter_queryset(swap_orders)

        page = self.paginate_queryset(swap_orders)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(swap_orders, many=True)
        return Response(serializer.data)
