import logging

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from shared.utils.logging_utils import LoggingContext
from shared.views import AuthenticatedModelViewSet
from tokens.exceptions import OrderCancellationException
from tokens.filters import TransferOrderFilter
from tokens.models import TransferOrder, TransferOrderType
from tokens.serializers import (
    TransferOrderCreateSerializer,
    TransferOrderDetailSerializer,
    TransferOrderListSerializer,
)
from tokens.services import TransferService

logger = logging.getLogger(__name__)


class TransferOrderViewSet(AuthenticatedModelViewSet):
    """
    Authenticated ViewSet for transfer orders.

    Provides authenticated order management for company users.
    """

    filterset_class = TransferOrderFilter
    ordering = ["-created_at"]
    ordering_fields = ["created_at", "status", "order_type", "quantity", "price_per_share"]

    def get_serializer_class(self):
        if self.action == "create":
            return TransferOrderCreateSerializer
        if self.action == "list":
            return TransferOrderListSerializer
        return TransferOrderDetailSerializer

    def get_queryset(self):
        return TransferOrder.objects.with_relations().for_token_visible_to_user(self.request.user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        transfer_service = TransferService()

        order, match_result = transfer_service.create_order_and_match(
            token=data["token"],
            order_type=data["order_type"],
            wallet_address=data["wallet_address"],
            quantity=data["quantity"],
            price_per_share=data["price_per_share"],
        )

        response_data = TransferOrderDetailSerializer(order).data

        if match_result:
            response_data["match"] = {
                "matched": True,
                "counter_order": str(
                    match_result["buy_order"].uuid
                    if order.order_type == TransferOrderType.SELL
                    else match_result["sell_order"].uuid
                ),
                "swap_order": str(match_result["swap_order"].uuid),
            }

        logger.info(f"{LoggingContext.ORDER} Created {order.order_type} order: {order.uuid}")

        return Response(response_data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def cancel(self, request, uuid=None):
        order = get_object_or_404(self.get_queryset(), uuid=uuid)

        if not order.can_cancel:
            raise OrderCancellationException(f"Order with status '{order.get_status_display()}' cannot be cancelled.")

        order.cancel()
        logger.info(f"{LoggingContext.ORDER} Cancelled order: {order.uuid}")

        return Response(TransferOrderDetailSerializer(order).data)

    @action(detail=False, methods=["get"], url_path="open")
    def open_orders(self, request):
        params = request.query_params
        queryset = (
            TransferOrder.objects.with_relations()
            .open()
            .filter_by_token(params.get("token"))
            .filter_by_order_type(params.get("order_type"))
            .for_token_visible_to_user(request.user)
        )
        serializer = TransferOrderListSerializer(self.paginate_queryset(queryset), many=True)
        return self.get_paginated_response(serializer.data)
