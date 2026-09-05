from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from assets.filters import AssetFilter
from assets.models import Asset, AssetSnapshot
from assets.serializers import (
    AssetSerializer,
    AssetSnapshotSerializer,
)
from assets.services import ExchangeRateService
from shared.utils.querysets import sample_evenly
from shared.views.base import AuthenticatedReadOnlyViewSet


class AssetViewSet(AuthenticatedReadOnlyViewSet):
    serializer_class = AssetSerializer
    filterset_class = AssetFilter
    ordering = ["symbol"]
    ordering_fields = ["symbol", "name", "current_price", "asset_type"]

    def get_queryset(self):
        chain = self.request.query_params.get("chain")
        queryset = Asset.objects.visible_to_user(self.request.user).verified()
        if chain:
            queryset = queryset.filter_by_chain(chain)
        else:
            queryset = queryset.filter_by_supported_chains()
        return queryset

    @action(detail=True, methods=["get"], url_path="snapshots")
    def snapshots(self, request, **kwargs):
        asset = self.get_object()

        order_by = request.query_params.get("order_by", "-source_timestamp")
        if order_by not in {"source_timestamp", "-source_timestamp"}:
            order_by = "-source_timestamp"
        try:
            queryset = AssetSnapshot.objects.filter(asset=asset).filter_by_date_range(
                request.query_params.get("start_date"), request.query_params.get("end_date")
            )
        except ValueError:
            raise ValidationError({"detail": "start_date and end_date must be YYYY-MM-DD."})
        queryset = sample_evenly(queryset.order_by(order_by), request.query_params.get("max_points"))

        serializer = AssetSnapshotSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="exchange-rates")
    def exchange_rates(self, request):
        target = request.query_params.get("currency", "AUD")
        rate = ExchangeRateService.get_rate(target_currency=target.upper())

        if rate is None:
            return Response(
                {"detail": f"Exchange rate for USD→{target.upper()} not available"},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {
                "baseCurrency": "USD",
                "targetCurrency": target.upper(),
                "rate": str(rate),
            }
        )
