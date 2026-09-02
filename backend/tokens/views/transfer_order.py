from rest_framework.decorators import action

from shared.views import AuthenticatedReadOnlyViewSet
from tokens.filters import TransferOrderFilter
from tokens.models import TransferOrder
from tokens.serializers import (
    TransferOrderDetailSerializer,
    TransferOrderListSerializer,
)


class TransferOrderViewSet(AuthenticatedReadOnlyViewSet):
    """
    Authenticated ViewSet for transfer orders.

    Provides owner-scoped legacy read access. Order mutations use the signed
    trading endpoints only.
    """

    filterset_class = TransferOrderFilter
    ordering = ["-created_at"]
    ordering_fields = ["created_at", "status", "order_type", "quantity", "price_per_share"]

    def get_serializer_class(self):
        if self.action == "list":
            return TransferOrderListSerializer
        return TransferOrderDetailSerializer

    def get_queryset(self):
        return TransferOrder.objects.with_relations().visible_to_user(self.request.user)

    @action(detail=False, methods=["get"], url_path="open")
    def open_orders(self, request):
        params = request.query_params
        queryset = (
            TransferOrder.objects.with_relations()
            .open()
            .filter_by_token(params.get("token"))
            .filter_by_order_type(params.get("order_type"))
            .visible_to_user(request.user)
        )
        serializer = TransferOrderListSerializer(self.paginate_queryset(queryset), many=True)
        return self.get_paginated_response(serializer.data)
