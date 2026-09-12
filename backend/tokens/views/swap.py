from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from shared.views import AuthenticatedListViewSet
from tokens.models import SwapOrder
from tokens.serializers.swap_order import SwapOrderListSerializer
from tokens.trading_wallet_access import resolve_verified_evm_wallets


class SwapOrderViewSet(AuthenticatedListViewSet):

    serializer_class = SwapOrderListSerializer
    ordering = ["-created_at"]
    ordering_fields = ["created_at", "status"]

    scoped_model = SwapOrder

    def narrow(self, queryset):
        return queryset.awaiting_signature().with_related()

    def list(self, request, *args, **kwargs):
        wallet_address = request.query_params.get("wallet_address")
        if not wallet_address:
            raise ValidationError({"wallet_address": "This query parameter is required."})

        authorized_wallets = resolve_verified_evm_wallets(request.user, [wallet_address])

        swap_orders = self.filter_queryset(self.get_queryset().for_party_wallets(authorized_wallets.wallet_ids))

        page = self.paginate_queryset(swap_orders)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(swap_orders, many=True)
        return Response(serializer.data)
