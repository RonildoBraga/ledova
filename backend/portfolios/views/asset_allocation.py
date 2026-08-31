import logging

from django.db import transaction
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from portfolios.exceptions import PortfolioNotFoundException
from portfolios.filters import AssetAllocationFilter
from portfolios.models.portfolio import AssetAllocation, Portfolio
from portfolios.serializers.portfolio import AssetAllocationSerializer
from shared.utils.logging_utils import LoggingContext
from shared.views.base import AuthenticatedModelViewSet

logger = logging.getLogger("ledova_backend")


class AssetAllocationViewSet(AuthenticatedModelViewSet):
    serializer_class = AssetAllocationSerializer
    filterset_class = AssetAllocationFilter
    ordering = ["-percentage"]
    ordering_fields = ["percentage", "created_at"]

    def get_queryset(self):
        return (
            AssetAllocation.objects.visible_to_user(self.request.user).filter_active_assets().exclude_zero_allocations()
        )

    def perform_create(self, serializer):
        logger.info(f"{LoggingContext.PORTFOLIOS} Creating asset allocation")
        return serializer.save()

    def perform_update(self, serializer):
        logger.info(f"{LoggingContext.PORTFOLIOS} Updating asset allocation")
        return serializer.save()

    def perform_destroy(self, instance):
        logger.info(f"{LoggingContext.PORTFOLIOS} Deleting asset allocations")
        return super().perform_destroy(instance)

    @action(detail=False, methods=["delete"], url_path="by-portfolio/(?P<portfolio_uuid>[^/.]+)")
    @transaction.atomic
    def delete_by_portfolio(self, request, portfolio_uuid=None):
        if not Portfolio.objects.filter(uuid=portfolio_uuid).exists():
            raise PortfolioNotFoundException(portfolio_uuid)

        queryset = self.get_queryset().filter(portfolio__uuid=portfolio_uuid)
        allocations_count = queryset.count()

        if allocations_count == 0:
            return Response(
                {"detail": f"No accessible allocations found for portfolio {portfolio_uuid}"},
                status=status.HTTP_200_OK,
            )

        queryset.delete()

        logger.info(
            f"{LoggingContext.PORTFOLIOS} Deleted {allocations_count} allocations for portfolio {portfolio_uuid}"
        )

        return Response(
            {"detail": f"Successfully deleted {allocations_count} allocations for portfolio {portfolio_uuid}"},
            status=status.HTTP_200_OK,
        )
