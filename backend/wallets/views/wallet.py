from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from shared.db import atomic
from shared.views.base import AuthenticatedModelViewSet
from wallets.constants import WALLET_VERIFICATION_STATUS_PENDING
from wallets.filters import WalletFilter
from wallets.models import Wallet
from wallets.serializers import (
    BroadcastTransferSerializer,
    HoldingSerializer,
    WalletSerializer,
)
from wallets.services import (
    BalanceService,
    TransferService,
    complete_wallet_verification,
    start_wallet_verification,
)
from wallets.services.sync import WalletSyncService


class WalletViewSet(AuthenticatedModelViewSet):
    serializer_class = WalletSerializer
    filterset_class = WalletFilter
    ordering = ["-created_at"]
    ordering_fields = ["created_at", "chain", "verification_status"]

    def get_throttles(self):
        self.throttle_scope = "broadcast" if self.action == "broadcast_transfer" else None
        return super().get_throttles()

    def get_queryset(self):
        queryset = Wallet.objects.visible_to_user(self.request.user)
        if self.action in ("update", "partial_update"):

            return queryset.select_for_update(of=("self",))
        return queryset.with_market_value()

    @atomic()
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    def _with_market_value(self, wallet):
        return Wallet.objects.visible_to_user(self.request.user).with_market_value().get(pk=wallet.pk)

    def perform_update(self, serializer):
        serializer.instance = self._with_market_value(serializer.save())

    def perform_create(self, serializer):
        wallet = serializer.save(verification_status=WALLET_VERIFICATION_STATUS_PENDING)
        serializer.instance = self._with_market_value(wallet)

        preferences = getattr(getattr(self.request.user, "userprofile", None), "preferences", None)
        portfolio = preferences.selected_portfolio if preferences else None
        if portfolio and portfolio.user_account_id == wallet.user_account_id:
            portfolio.wallets.add(wallet)

    @action(detail=True, methods=["post"], url_path="request-verification", url_name="request-verification")
    def request_verification(self, request, uuid=None):
        wallet = start_wallet_verification(request.user, uuid)

        return Response(
            {
                "challenge": wallet.verification_challenge,
                "message": f"Please sign this message with your wallet: {wallet.address}",
                "walletAddress": wallet.address,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="verify-signature", url_name="verify-signature")
    def verify_signature(self, request, uuid=None):
        wallet = complete_wallet_verification(request.user, uuid, request.data.get("signature"))

        return Response(
            {
                "success": True,
                "message": "Wallet verified successfully!",
                "verificationStatus": wallet.verification_status,
                "verifiedAt": wallet.verified_at.isoformat(),
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="sync", url_name="sync")
    def sync(self, request, uuid=None):
        wallet = self.get_object()
        sync_data = WalletSyncService.sync_wallet(wallet)
        wallet.refresh_from_db()
        return Response(
            {"success": True, "wallet": self.get_serializer(wallet).data, "sync_result": sync_data},
            status=status.HTTP_200_OK,
        )

    @extend_schema(responses=HoldingSerializer(many=True))
    @action(detail=True, methods=["get"], url_path="holdings", url_name="holdings")
    def holdings(self, request, uuid=None):
        wallet = self.get_object()
        holdings = wallet.holdings.filter(asset__is_active=True, asset__is_verified=True).select_related("asset")
        return Response(HoldingSerializer(holdings, many=True).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="prepare-transfer", url_name="prepare-transfer")
    def prepare_transfer(self, request, uuid=None):
        wallet = self.get_object()

        transaction_data = TransferService.prepare_transfer(
            wallet=wallet,
            to_address=request.data.get("to_address"),
            amount_eth=request.data.get("amount_eth"),
            amount_btc=request.data.get("amount_btc"),
            amount_token=request.data.get("amount_token"),
            token_contract=request.data.get("token_contract"),
        )

        return Response(transaction_data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="broadcast-transfer", url_name="broadcast-transfer")
    def broadcast_transfer(self, request, uuid=None):
        wallet = self.get_object()

        serializer = BroadcastTransferSerializer(data=request.data, context={"wallet": wallet})
        serializer.is_valid(raise_exception=True)

        result = TransferService.broadcast_transfer(wallet=wallet, **serializer.validated_data)

        return Response(result, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="batch-check-balances", url_name="batch-check-balances")
    def batch_check_balances(self, request):
        result = BalanceService.batch_check_balances(
            addresses=request.data.get("addresses", []),
            chain=request.data.get("chain", "ethereum"),
        )

        return Response(result, status=status.HTTP_200_OK)
