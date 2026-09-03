import logging

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from shared.utils.logging_utils import LoggingContext
from shared.views.base import AuthenticatedModelViewSet
from wallets.constants import (
    WALLET_VERIFICATION_STATUS_PENDING,
    WALLET_VERIFICATION_STATUS_VERIFIED,
)
from wallets.exceptions import (
    InvalidSignatureException,
    SignatureRequiredException,
    VerificationChallengeNotFoundException,
)
from wallets.filters import WalletFilter
from wallets.models import HoldingSnapshot, Transaction, Wallet
from wallets.serializers import (
    HoldingSerializer,
    HoldingSnapshotSerializer,
    TransactionSerializer,
    WalletSerializer,
)
from wallets.services import (
    BalanceService,
    TransferService,
    generate_verification_challenge,
    verify_wallet_signature,
)
from wallets.services.sync import WalletSyncService
from wallets.tasks import sync_wallet

logger = logging.getLogger("ledova_backend")


class WalletViewSet(AuthenticatedModelViewSet):
    serializer_class = WalletSerializer
    filterset_class = WalletFilter
    ordering = ["-created_at"]
    ordering_fields = ["created_at", "chain", "verification_status"]

    def get_queryset(self):
        queryset = Wallet.objects.visible_to_user(self.request.user)
        if self.action in ("update", "partial_update"):
            # Lock the row before validation runs; FOR UPDATE cannot be combined with the market-value aggregate.
            return queryset.select_for_update(of=("self",))
        return queryset.with_market_value()

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    def perform_create(self, serializer):
        wallet = serializer.save(verification_status=WALLET_VERIFICATION_STATUS_PENDING)
        # A new wallet lands in the requester's selected portfolio; the UI has no
        # other way to put wallets into portfolios.
        preferences = getattr(getattr(self.request.user, "userprofile", None), "preferences", None)
        portfolio = preferences.selected_portfolio if preferences else None
        if portfolio and portfolio.user_account_id == wallet.user_account_id:
            portfolio.wallets.add(wallet)

    @action(detail=True, methods=["post"], url_path="request-verification", url_name="request-verification")
    @transaction.atomic
    def request_verification(self, request, uuid=None):
        wallet = get_object_or_404(
            Wallet.objects.visible_to_user(request.user).select_for_update(of=("self",)),
            uuid=uuid,
        )
        challenge = generate_verification_challenge(wallet.address)

        wallet.verification_challenge = challenge
        wallet.save(update_fields=["verification_challenge"])

        return Response(
            {
                "challenge": challenge,
                "message": f"Please sign this message with your wallet: {wallet.address}",
                "walletAddress": wallet.address,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="verify-signature", url_name="verify-signature")
    @transaction.atomic
    def verify_signature(self, request, uuid=None):
        wallet = get_object_or_404(
            Wallet.objects.visible_to_user(request.user).select_for_update(of=("self",)),
            uuid=uuid,
        )
        signature = request.data.get("signature")

        if not signature:
            raise SignatureRequiredException()

        if not wallet.verification_challenge:
            raise VerificationChallengeNotFoundException()

        is_valid = verify_wallet_signature(
            wallet.address, wallet.verification_challenge, signature, wallet.chain.upper()
        )

        if is_valid:
            wallet.verification_status = WALLET_VERIFICATION_STATUS_VERIFIED
            wallet.verification_signature = signature
            wallet.verified_at = timezone.now()
            wallet.save(update_fields=["verification_status", "verification_signature", "verified_at"])

            try:
                sync_wallet.defer(wallet_uuid=str(wallet.uuid))
            except Exception as e:
                logger.error(f"{LoggingContext.WALLET_SYNC} Failed to queue sync: {e}")

            return Response(
                {
                    "success": True,
                    "message": "Wallet verified successfully!",
                    "verificationStatus": WALLET_VERIFICATION_STATUS_VERIFIED,
                    "verifiedAt": wallet.verified_at.isoformat(),
                },
                status=status.HTTP_200_OK,
            )
        else:
            raise InvalidSignatureException()

    @action(detail=True, methods=["post"], url_path="sync", url_name="sync")
    def sync(self, request, uuid=None):
        wallet = self.get_object()
        sync_data = WalletSyncService.sync_wallet(wallet)
        wallet.refresh_from_db()
        return Response(
            {"success": True, "wallet": self.get_serializer(wallet).data, "sync_result": sync_data},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="sync-holdings", url_name="sync-holdings")
    def sync_holdings(self, request, uuid=None):
        wallet = self.get_object()
        job_id = sync_wallet.defer(wallet_uuid=str(wallet.uuid))
        serializer = self.get_serializer(wallet)

        return Response(
            {"success": True, "taskId": job_id, "wallet": serializer.data},
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=["get"], url_path="holdings", url_name="holdings")
    def holdings(self, request, uuid=None):
        wallet = self.get_object()
        holdings = wallet.holdings.filter(asset__is_active=True, asset__is_verified=True).select_related("asset")
        return Response(HoldingSerializer(holdings, many=True).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get"], url_path="balances", url_name="balances")
    def balances(self, request, uuid=None):
        wallet = self.get_object()
        snapshots = (
            HoldingSnapshot.objects.filter(
                holding__wallet=wallet, holding__asset__is_active=True, holding__asset__is_verified=True
            )
            .select_related("holding", "holding__asset")
            .order_by("holding__asset_id", "-snapshot_date")
            .distinct("holding__asset_id")
        )

        page = self.paginate_queryset(snapshots)
        serializer = HoldingSnapshotSerializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    @action(detail=True, methods=["get"], url_path="transactions", url_name="transactions")
    def transactions(self, request, uuid=None):
        wallet = self.get_object()
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")

        transactions = (
            Transaction.objects.filter_by_wallet(wallet)
            .filter(asset__is_verified=True)
            .filter_by_date_range(start_date, end_date)
            .with_optimized_data()
            .order_by("-block_timestamp")
        )

        page = self.paginate_queryset(transactions)
        serializer = TransactionSerializer(page, many=True)
        return self.get_paginated_response(serializer.data)

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

        result = TransferService.broadcast_transfer(
            wallet=wallet,
            signed_transaction=request.data.get("signed_transaction"),
            to_address=request.data.get("to_address"),
            amount=request.data.get("amount"),
            transaction_fee=request.data.get("transaction_fee"),
            token_contract=request.data.get("token_contract"),
        )

        return Response(result, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="batch-check-balances", url_name="batch-check-balances")
    def batch_check_balances(self, request):
        result = BalanceService.batch_check_balances(
            addresses=request.data.get("addresses", []),
            chain=request.data.get("chain", "ethereum"),
        )

        return Response(result, status=status.HTTP_200_OK)
