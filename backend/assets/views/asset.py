import logging
from decimal import Decimal

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from assets.filters import AssetFilter
from assets.models import Asset, AssetSnapshot
from assets.serializers import (
    AssetSerializer,
    AssetSnapshotSerializer,
)
from assets.services import AssetSyncService, ExchangeRateService
from shared.utils.logging_utils import LoggingContext
from shared.views.base import AuthenticatedReadOnlyViewSet

logger = logging.getLogger("ledova_backend")


class AssetViewSet(AuthenticatedReadOnlyViewSet):
    serializer_class = AssetSerializer
    filterset_class = AssetFilter
    ordering = ["symbol"]
    ordering_fields = ["symbol", "name", "current_price", "asset_type"]

    def get_queryset(self):
        chain = self.request.query_params.get("chain")
        queryset = Asset.objects.visible_to_user(self.request.user)
        if chain:
            queryset = queryset.filter_by_chain(chain)
        else:
            queryset = queryset.filter_by_supported_chains()
        return queryset

    @action(detail=True, methods=["get"], url_path="snapshots")
    def snapshots(self, request, **kwargs):
        asset = self.get_object()

        logger.debug(
            f"{LoggingContext.ASSETS} Fetching snapshots for {asset.symbol} (params={dict(request.query_params)})"
        )

        queryset = AssetSnapshot.objects.filter(asset=asset)
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")
        if start_date or end_date:
            queryset = queryset.filter_by_date_range(start_date, end_date)
        max_points = request.query_params.get("max_points")
        if max_points:
            queryset = queryset.sample_evenly(int(max_points))
        order_by = request.query_params.get("order_by", "-source_timestamp")
        queryset = queryset.order_by(order_by)

        serializer = AssetSnapshotSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="exchange-rates")
    def exchange_rates(self, request):
        """Return current exchange rates for display currency conversion."""
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

    @action(detail=False, methods=["post"], url_path="bulk-update-prices", permission_classes=[IsAdminUser])
    def bulk_update_prices(self, request):
        logger.info(f"{LoggingContext.ASSETS} Bulk price update requested by {request.user.email}")

        price_updates = request.data.get("priceUpdates", [])
        source = request.data.get("source", "manual")
        create_snapshots = request.data.get("createSnapshots", True)

        if not price_updates:
            return Response({"success": False, "error": "priceUpdates is required"}, status=status.HTTP_400_BAD_REQUEST)

        if not isinstance(price_updates, list):
            return Response(
                {"success": False, "error": "priceUpdates must be an array"}, status=status.HTTP_400_BAD_REQUEST
            )

        success_count = 0
        error_count = 0
        results = []

        for update_data in price_updates:
            symbol = update_data.get("symbol")
            price_value = update_data.get("price")
            currency = update_data.get("currency", "USD")

            if not symbol or not price_value:
                error_count += 1
                results.append(
                    {"symbol": symbol or "<unknown>", "success": False, "message": "Missing symbol or price"}
                )
                continue

            try:
                asset = Asset.objects.get(symbol=symbol)
                price = Decimal(str(price_value))

                AssetSyncService.update_price(
                    asset=asset,
                    price=price,
                    source=source,
                    currency=currency,
                    create_snapshot=create_snapshots,
                )

                success_count += 1
                results.append({"symbol": symbol, "success": True, "newPrice": str(price)})

            except Asset.DoesNotExist:
                error_count += 1
                results.append({"symbol": symbol, "success": False, "message": f"Asset '{symbol}' not found"})
            except Exception as e:
                error_count += 1
                results.append({"symbol": symbol, "success": False, "message": str(e)})

        return Response(
            {
                "success": error_count == 0,
                "successCount": success_count,
                "errorCount": error_count,
                "total": len(price_updates),
                "results": results,
            },
            status=status.HTTP_200_OK if error_count == 0 else status.HTTP_207_MULTI_STATUS,
        )
