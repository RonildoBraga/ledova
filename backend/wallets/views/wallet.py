import logging

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
    WalletAlreadyExistsException,
)
from wallets.filters import WalletFilter
from wallets.models import Wallet
from wallets.serializers import WalletSerializer
from wallets.services import (
    BalanceService,
    TransferService,
    generate_verification_challenge,
    verify_wallet_signature,
)

logger = logging.getLogger("ledova_backend")


class WalletViewSet(AuthenticatedModelViewSet):
    serializer_class = WalletSerializer
    filterset_class = WalletFilter
    ordering = ["-created_at"]
    ordering_fields = ["created_at", "chain", "verification_status"]

    def get_queryset(self):
        user = self.request.user
        return Wallet.objects.visible_to_user(user).with_market_value()

    def perform_create(self, serializer):
        address = serializer.validated_data.get("address")
        user_account = serializer.validated_data.get("user_account")

        if Wallet.objects.filter(address=address, user_account=user_account).exists():
            raise WalletAlreadyExistsException()

        wallet = serializer.save(verification_status=WALLET_VERIFICATION_STATUS_PENDING)

        try:
            from wallets.tasks import sync_wallet

            sync_wallet.defer(wallet_uuid=str(wallet.uuid))
        except Exception as e:
            logger.error(f"{LoggingContext.WALLET_SYNC} Failed to queue sync: {e}")

    @action(detail=True, methods=["post"], url_path="request-verification", url_name="request-verification")
    def request_verification(self, request, uuid=None):
        wallet = self.get_object()
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
    def verify_signature(self, request, uuid=None):
        wallet = self.get_object()
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
                from wallets.tasks import sync_wallet

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
        from wallets.services.sync import WalletSyncService

        try:
            sync_data = WalletSyncService.sync_wallet(wallet)
            wallet.refresh_from_db()
            serializer = self.get_serializer(wallet)

            return Response(
                {"success": True, "wallet": serializer.data, "sync_result": sync_data},
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            logger.error(f"{LoggingContext.WALLET_SYNC} Sync failed: {e}")
            return Response(
                {"success": False, "message": f"Wallet sync failed: {e}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @action(detail=True, methods=["post"], url_path="sync-holdings", url_name="sync-holdings")
    def sync_holdings(self, request, uuid=None):
        wallet = self.get_object()
        from wallets.tasks import sync_wallet

        job_id = sync_wallet.defer(wallet_uuid=str(wallet.uuid))
        serializer = self.get_serializer(wallet)

        return Response(
            {"success": True, "taskId": job_id, "wallet": serializer.data},
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=["get"], url_path="holdings", url_name="holdings")
    def holdings(self, request, uuid=None):
        wallet = self.get_object()

        from wallets.models import Holding
        from wallets.serializers import HoldingSerializer, HoldingSummarySerializer

        include_asset = request.query_params.get("include_asset", "false").lower() == "true"
        min_value_param = request.query_params.get("min_value", "0")

        try:
            min_value = float(min_value_param)
        except ValueError:
            min_value = 0

        holdings = (
            Holding.objects.filter(wallet=wallet, asset__is_active=True, asset__is_verified=True)
            .select_related("asset")
            .order_by("-quantity")
        )

        if min_value > 0:
            holdings = [h for h in holdings if h.market_value and h.market_value >= min_value]

        if include_asset:
            serializer = HoldingSerializer(holdings, many=True)
        else:
            serializer = HoldingSummarySerializer(holdings, many=True)

        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get"], url_path="balances", url_name="balances")
    def balances(self, request, uuid=None):
        wallet = self.get_object()

        from wallets.models import HoldingSnapshot
        from wallets.serializers import HoldingSnapshotSerializer

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

        from wallets.models import Transaction
        from wallets.serializers import TransactionSerializer

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
