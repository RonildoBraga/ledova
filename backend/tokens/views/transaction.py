from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from shared.views import AuthenticatedListViewSet
from tokens.models import SwapOrder
from tokens.serializers.transaction import (
    MintTransactionSerializer,
    ShareIssuanceTransactionSerializer,
    SwapPaymentTransactionSerializer,
    SwapShareTransactionSerializer,
)
from tokens.services import TransactionHistoryService
from tokens.trading_wallet_access import resolve_verified_evm_wallets


class TransactionHistoryViewSet(AuthenticatedListViewSet):
    serializer_class = SwapShareTransactionSerializer
    ordering = ["-created_at"]
    ordering_fields = ["created_at"]

    def get_queryset(self):
        return SwapOrder.objects.none()

    def list(self, request, *args, **kwargs):
        wallet_addresses_param = request.query_params.get("wallet_addresses", "")
        wallet_addresses = [a.strip() for a in wallet_addresses_param.split(",") if a.strip()]

        if not wallet_addresses:
            return Response({"results": [], "count": 0, "next": None, "previous": None})

        if len(wallet_addresses) > 10:
            raise ValidationError({"wallet_addresses": "Maximum 10 wallet addresses allowed per request."})

        authorized_wallets = resolve_verified_evm_wallets(request.user, wallet_addresses)

        data = TransactionHistoryService.get_transaction_history(
            wallet_ids=authorized_wallets.wallet_ids,
            wallet_addresses=authorized_wallets.addresses,
            start_date=request.query_params.get("start_date"),
            end_date=request.query_params.get("end_date"),
            transaction_type=request.query_params.get("transaction_type"),
            include_address_only_history=request.user.is_staff or request.user.is_superuser,
        )

        context = {
            "request": request,
            "authorized_wallet_addresses": authorized_wallets.addresses,
        }
        swap_orders = data["swap_orders"]

        swap_share_data = (
            SwapShareTransactionSerializer(swap_orders, many=True, context=context).data
            if swap_orders is not None
            else []
        )
        swap_payment_data = (
            SwapPaymentTransactionSerializer(swap_orders, many=True, context=context).data
            if swap_orders is not None
            else []
        )

        all_swap_data = swap_share_data + swap_payment_data

        mint_data = (
            MintTransactionSerializer(data["mint_requests"], many=True, context=context).data
            if data["mint_requests"] is not None
            else []
        )

        issuance_data = (
            ShareIssuanceTransactionSerializer(data["token_issuances"], many=True, context=context).data
            if data["token_issuances"] is not None
            else []
        )

        all_transactions = TransactionHistoryService.merge_and_sort_transactions(
            all_swap_data, mint_data, issuance_data
        )

        return self.get_paginated_response(self.paginate_queryset(all_transactions))
