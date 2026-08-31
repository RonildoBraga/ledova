from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated

from tokens.models import NAVUpdate, YieldToken
from tokens.serializers.yield_token import NAVUpdateSerializer, YieldTokenSerializer


class YieldTokenViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = YieldTokenSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "uuid"
    ordering = ["symbol"]
    ordering_fields = ["symbol", "name", "created_at"]

    def get_queryset(self):
        return YieldToken.objects.filter(is_active=True)

    @action(detail=True, methods=["get"], url_path="nav-history")
    def nav_history(self, request, uuid=None):
        yield_token = self.get_object()
        queryset = NAVUpdate.objects.filter(yield_token=yield_token).order_by("-created_at")
        serializer = NAVUpdateSerializer(self.paginate_queryset(queryset), many=True)
        return self.get_paginated_response(serializer.data)
