from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from companies.models import Company
from shared.views import AuthenticatedModelViewSet
from tokens.exceptions import InvalidTokenStateException
from tokens.filters import ShareTokenFilter
from tokens.models import ShareIssuance, ShareToken
from tokens.serializers import (
    ShareIssuanceListSerializer,
    ShareIssuanceRequestSerializer,
    ShareTokenCreateSerializer,
    ShareTokenDetailSerializer,
    ShareTokenListSerializer,
)
from tokens.services import ShareTokenService
from whitelist.services import WhitelistService

MANAGE_ACTIONS = ("create", "update", "partial_update", "destroy", "deploy", "pause", "unpause", "issue")


class ShareTokenViewSet(AuthenticatedModelViewSet):
    filterset_class = ShareTokenFilter
    ordering = ["-created_at"]
    ordering_fields = ["created_at", "name", "symbol", "status", "token_type"]

    def get_serializer_class(self):
        if self.action == "create":
            return ShareTokenCreateSerializer
        if self.action == "list":
            return ShareTokenListSerializer
        return ShareTokenDetailSerializer

    def get_queryset(self):
        user = self.request.user
        if self.action in MANAGE_ACTIONS:
            return ShareToken.objects.manageable_by_user(user).with_company()
        queryset = ShareToken.objects.visible_to_user(user).with_company()
        if self.action == "list":
            queryset = queryset.with_market_summary()
        return queryset

    def filter_queryset(self, queryset):
        """Query params narrow the list only; a detail action is a uuid lookup and keeps its own params."""
        if self.action == "list":
            return super().filter_queryset(queryset)
        return queryset

    def create(self, request, *args, **kwargs):
        if not Company.objects.manageable_by_user(request.user).exists():
            raise PermissionDenied("You must be associated with a company to create tokens.")

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        token = serializer.save()
        return Response(ShareTokenDetailSerializer(token).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def deploy(self, request, uuid=None):
        token = self.get_object()
        ShareTokenService.start_deployment(token)
        return Response({"message": "Token deployment initiated.", "token": ShareTokenDetailSerializer(token).data})

    @action(detail=True, methods=["post"])
    def pause(self, request, uuid=None):
        token = self.get_object()
        if token.status != "deployed":
            raise InvalidTokenStateException("Only deployed tokens can be paused.")
        token.mark_paused()
        return Response({"message": "Token paused successfully.", "token": ShareTokenDetailSerializer(token).data})

    @action(detail=True, methods=["post"])
    def unpause(self, request, uuid=None):
        token = self.get_object()
        if token.status != "paused":
            raise InvalidTokenStateException("Only paused tokens can be unpaused.")
        token.mark_unpaused()
        return Response({"message": "Token unpaused successfully.", "token": ShareTokenDetailSerializer(token).data})

    @action(detail=True, methods=["post"])
    def issue(self, request, uuid=None):
        token = self.get_object()
        issuance_request = ShareTokenService().create_issuance_request(
            token=token,
            recipient=request.data.get("recipient", "").strip(),
            amount=int(request.data.get("amount", 0)),
            user=request.user,
            reason=request.data.get("reason", ""),
            issuance_type=request.data.get("issuance_type", "additional"),
        )
        return Response(
            {
                "message": "Share issuance request submitted for approval.",
                "token": ShareTokenDetailSerializer(token).data,
                "issuance_request": ShareIssuanceRequestSerializer(issuance_request).data,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["get"], url_path="can-receive/(?P<address>[^/.]+)")
    def can_receive(self, request, uuid=None, address=None):
        token = self.get_object()
        eligibility = WhitelistService().get_receive_eligibility(address)
        return Response(
            {
                "address": address.lower(),
                "token": {
                    "uuid": str(token.uuid),
                    "name": token.name,
                    "symbol": token.symbol,
                },
                "canReceive": eligibility["can_receive"],
                "whitelistStatus": {
                    "database": eligibility["db_whitelisted"],
                    "onChain": eligibility["on_chain_whitelisted"],
                },
                "investorType": eligibility["investor_type"],
                "investorTypeDisplay": eligibility["investor_type_display"],
            }
        )

    @action(detail=True, methods=["get"])
    def issuances(self, request, uuid=None):
        token = self.get_object()
        issuances = ShareIssuance.objects.with_token().with_initiated_by().filter_by_token(token)
        if request.query_params.get("status"):
            issuances = issuances.filter(status=request.query_params["status"])
        page = self.paginate_queryset(issuances.order_by("-completed_at"))
        return self.get_paginated_response(ShareIssuanceListSerializer(page, many=True).data)

    @action(detail=True, methods=["get"])
    def holders(self, request, uuid=None):
        token = self.get_object()
        holders_data = ShareTokenService().get_token_holders(token)
        return Response(
            {
                "token": {
                    "uuid": str(token.uuid),
                    "name": token.name,
                    "symbol": token.symbol,
                    "status": token.status,
                    "total_supply": token.total_supply,
                },
                "holders": holders_data,
                "total_holders": len(holders_data),
            }
        )
