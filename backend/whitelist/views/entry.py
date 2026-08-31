import csv
import logging

from django.http import Http404, HttpResponse
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from shared.utils.logging_utils import LoggingContext
from shared.views import AuthenticatedModelViewSet
from whitelist.exceptions import (
    BatchEntriesRequiredException,
    BatchSizeLimitExceededException,
)
from whitelist.filters import WhitelistEntryFilter
from whitelist.models import WhitelistEntry
from whitelist.serializers import (
    WhitelistAddResponseSerializer,
    WhitelistAddSerializer,
    WhitelistEntrySerializer,
    WhitelistRemoveResponseSerializer,
    WhitelistRemoveSerializer,
    WhitelistSyncResponseSerializer,
)
from whitelist.services import WhitelistService

logger = logging.getLogger(__name__)


class WhitelistEntryViewSet(AuthenticatedModelViewSet):
    serializer_class = WhitelistEntrySerializer
    filterset_class = WhitelistEntryFilter
    ordering = ["-created_at"]
    ordering_fields = ["created_at", "status"]

    def get_permissions(self):
        if self.action in ["add", "remove", "batch_add"]:
            return [IsAdminUser()]
        return super().get_permissions()

    def get_queryset(self):
        return WhitelistEntry.objects.visible_to_user(self.request.user)

    @action(detail=False, methods=["get"], url_path="entry/(?P<address>[^/.]+)")
    def by_address(self, request, address=None):
        address = address.lower()

        try:
            entry = WhitelistEntry.objects.get(wallet__address__iexact=address)
        except WhitelistEntry.DoesNotExist:
            raise Http404(f"No whitelist entry found for {address}")

        serializer = self.get_serializer(entry)
        return Response(serializer.data)

    @action(detail=False, methods=["post"])
    def add(self, request):
        serializer = WhitelistAddSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        wallet_address = serializer.validated_data["wallet_address"]

        service = WhitelistService()

        tx_hash, entry = service.add_to_whitelist(
            address=wallet_address,
            wait_for_receipt=True,
        )

        logger.info(f"{LoggingContext.WHITELIST} Added {wallet_address} to whitelist (tx={tx_hash})")

        response_data = {
            "success": True,
            "tx_hash": tx_hash,
            "entry": WhitelistEntrySerializer(entry).data,
        }

        return Response(
            WhitelistAddResponseSerializer(response_data).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["post"])
    def remove(self, request):
        serializer = WhitelistRemoveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        wallet_address = serializer.validated_data["wallet_address"]

        service = WhitelistService()

        tx_hash, entry = service.remove_from_whitelist(
            address=wallet_address,
            wait_for_receipt=True,
        )

        logger.info(f"{LoggingContext.WHITELIST} Removed {wallet_address} from whitelist (tx={tx_hash})")

        response_data = {
            "success": True,
            "tx_hash": tx_hash,
            "message": f"Address {wallet_address} removed from whitelist",
        }

        return Response(
            WhitelistRemoveResponseSerializer(response_data).data,
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["post"], url_path="sync/(?P<address>[^/.]+)")
    def sync(self, request, address=None):
        service = WhitelistService()

        entry = service.sync_entry(address)

        logger.info(f"{LoggingContext.WHITELIST} Synced {address} with on-chain data")

        response_data = {
            "success": True,
            "entry": WhitelistEntrySerializer(entry).data,
            "message": f"Successfully synced {address} with on-chain data",
        }

        return Response(
            WhitelistSyncResponseSerializer(response_data).data,
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["get"])
    def export(self, request):
        queryset = self.filter_queryset(self.get_queryset())

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="whitelist-export.csv"'

        writer = csv.writer(response)
        writer.writerow(
            [
                "Wallet Address",
                "Status",
                "Is Whitelisted",
                "Created At",
                "Updated At",
            ]
        )

        for entry in queryset:
            writer.writerow(
                [
                    entry.wallet.address,
                    entry.get_status_display(),
                    "Yes" if entry.is_whitelisted else "No",
                    entry.created_at.isoformat() if entry.created_at else "",
                    entry.updated_at.isoformat() if entry.updated_at else "",
                ]
            )

        return response

    @action(detail=False, methods=["post"], url_path="batch-add")
    def batch_add(self, request):
        from rest_framework.exceptions import APIException

        entries = request.data.get("entries", [])

        if not entries:
            raise BatchEntriesRequiredException()

        if len(entries) > 100:
            raise BatchSizeLimitExceededException(max_size=100)

        results = {
            "successful": 0,
            "failed": 0,
            "errors": [],
        }

        service = WhitelistService()

        for entry_data in entries:
            wallet_address = entry_data.get("walletAddress", entry_data.get("wallet_address", ""))

            if not wallet_address:
                results["failed"] += 1
                results["errors"].append(
                    {
                        "walletAddress": wallet_address,
                        "error": "Wallet address is required",
                    }
                )
                continue

            try:
                service.add_to_whitelist(
                    address=wallet_address,
                    wait_for_receipt=True,
                )

                results["successful"] += 1
                logger.info(f"{LoggingContext.WHITELIST_ADD} Added {wallet_address}")

            except ValueError as e:
                results["failed"] += 1
                results["errors"].append(
                    {
                        "walletAddress": wallet_address,
                        "error": str(e),
                    }
                )
            except APIException as e:
                results["failed"] += 1
                results["errors"].append(
                    {
                        "walletAddress": wallet_address,
                        "error": str(e.detail),
                    }
                )

        return Response(results, status=status.HTTP_200_OK)
