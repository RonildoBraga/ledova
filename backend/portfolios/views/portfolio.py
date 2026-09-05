from datetime import datetime

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from portfolios.filters import PortfolioFilter
from portfolios.models.portfolio import Portfolio
from portfolios.serializers.portfolio import (
    PortfolioSerializer,
    PortfolioValuePointSerializer,
)
from portfolios.services import PortfolioWalletService, portfolio_value_series
from shared.utils.querysets import sample_evenly
from shared.views.base import AuthenticatedModelViewSet
from users.models import UserAccount


class PortfolioViewSet(AuthenticatedModelViewSet):
    serializer_class = PortfolioSerializer
    filterset_class = PortfolioFilter
    ordering = ["-created_at"]
    ordering_fields = ["created_at", "name"]

    def get_queryset(self):
        qs = Portfolio.objects.visible_to_user(self.request.user).active()
        return qs

    def perform_create(self, serializer):
        user_account = serializer.validated_data.get("user_account")
        if user_account is None:
            # Default to the caller's selected account, then to their only
            # account; never guess between several with .first().
            accounts = UserAccount.objects.visible_to_user(self.request.user)
            preferences = getattr(self.request.user.userprofile, "preferences", None)
            selected_id = getattr(preferences, "selected_account_id", None)
            user_account = accounts.filter(pk=selected_id).first() if selected_id else None
        if user_account is None:
            candidates = list(accounts[:2])
            if len(candidates) != 1:
                raise ValidationError({"userAccount": "Select the account this portfolio belongs to."})
            user_account = candidates[0]

        return serializer.save(user_account=user_account)

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=["is_active"])

    @action(detail=True, methods=["post"], url_path="add-wallet")
    def add_wallet(self, request, *args, **kwargs):
        portfolio = self.get_object()
        wallet_uuid = request.data.get("wallet_uuid")
        if not wallet_uuid:
            raise ValidationError({"walletUuid": "This field is required."})

        portfolio = PortfolioWalletService.add_wallet_to_portfolio(portfolio=portfolio, wallet_uuid=wallet_uuid)
        serializer = self.get_serializer(portfolio)
        return Response(
            {"success": True, "message": "Wallet added to portfolio successfully", "portfolio": serializer.data},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="remove-wallet")
    def remove_wallet(self, request, *args, **kwargs):
        portfolio = self.get_object()
        wallet_uuid = request.data.get("wallet_uuid")
        if not wallet_uuid:
            raise ValidationError({"walletUuid": "This field is required."})

        portfolio = PortfolioWalletService.remove_wallet_from_portfolio(portfolio=portfolio, wallet_uuid=wallet_uuid)
        serializer = self.get_serializer(portfolio)
        return Response(
            {"success": True, "message": "Wallet removed from portfolio successfully", "portfolio": serializer.data},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["get"], url_path="snapshots")
    def snapshots(self, request, *args, **kwargs):
        portfolio = self.get_object()
        params = request.query_params

        bounds = {}
        for key in ("start_date", "end_date"):
            try:
                bounds[key] = datetime.strptime(params[key], "%Y-%m-%d").date() if params.get(key) else None
            except ValueError:
                raise ValidationError({"detail": "start_date and end_date must be YYYY-MM-DD."})
        points = portfolio_value_series(portfolio, **bounds)
        if params.get("order_by") != "snapshot_date":
            points.reverse()
        points = sample_evenly(points, params.get("max_points"))

        return Response(PortfolioValuePointSerializer(points, many=True).data)
