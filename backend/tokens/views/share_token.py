import logging

from django.db import IntegrityError
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from companies.models import Company
from shared.utils.logging_utils import LoggingContext
from shared.views import AuthenticatedModelViewSet
from tokens.exceptions import CompanyNotReadyException, InvalidTokenStateException
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
from tokens.tasks import deploy_share_token_task
from whitelist.services import WhitelistService

logger = logging.getLogger(__name__)


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

        if self.action in ("create", "update", "partial_update", "destroy"):
            return ShareToken.objects.manageable_by_user(user).with_company()

        return ShareToken.objects.visible_to_user(user).with_company()

    def get_manageable_queryset(self):
        return ShareToken.objects.manageable_by_user(self.request.user).select_related("company")

    def get_user_company(self):
        return Company.objects.manageable_by_user(self.request.user).first()

    def create(self, request, *args, **kwargs):
        from rest_framework.exceptions import PermissionDenied, ValidationError

        company = self.get_user_company()

        if not company:
            raise PermissionDenied("You must be associated with a company to create tokens.")

        serializer = self.get_serializer(data=request.data)
        serializer.context["company"] = company
        serializer.is_valid(raise_exception=True)

        try:
            token = serializer.save()
        except IntegrityError as e:
            error_msg = str(e)
            if "unique_company_symbol" in error_msg:
                raise ValidationError({"symbol": "A token with this symbol already exists for your company."})
            raise ValidationError({"detail": "Failed to create token. Please try again."})

        logger.info(f"{LoggingContext.TOKEN} User {request.user.email} created token: {token.name} ({token.symbol})")

        response_serializer = ShareTokenDetailSerializer(token)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def deploy(self, request, uuid=None):
        token = get_object_or_404(self.get_manageable_queryset(), uuid=uuid)

        if token.status != "draft":
            raise InvalidTokenStateException(
                f"Cannot deploy token with status '{token.get_status_display()}'. Token must be in draft status."
            )

        primary_wallet = token.company.get_primary_wallet()
        if not primary_wallet:
            raise CompanyNotReadyException(
                "Company must have an operator wallet or verified ETH wallet before deploying tokens."
            )

        if token.company.status != "active":
            raise CompanyNotReadyException("Company must be active before deploying tokens.")

        token.mark_deploying()
        logger.info(f"{LoggingContext.TOKEN} User {request.user.email} initiated deployment for: {token.name}")

        deploy_share_token_task.defer(token_uuid=str(token.uuid))

        return Response(
            {
                "message": "Token deployment initiated.",
                "token": ShareTokenDetailSerializer(token).data,
            }
        )

    @action(detail=True, methods=["post"])
    def pause(self, request, uuid=None):
        token = get_object_or_404(self.get_manageable_queryset(), uuid=uuid)

        if token.status != "deployed":
            raise InvalidTokenStateException("Only deployed tokens can be paused.")

        token.mark_paused()
        logger.info(f"{LoggingContext.TOKEN} User {request.user.email} paused token: {token.name}")

        return Response(
            {
                "message": "Token paused successfully.",
                "token": ShareTokenDetailSerializer(token).data,
            }
        )

    @action(detail=True, methods=["post"])
    def unpause(self, request, uuid=None):
        token = get_object_or_404(self.get_manageable_queryset(), uuid=uuid)

        if token.status != "paused":
            raise InvalidTokenStateException("Only paused tokens can be unpaused.")

        token.mark_unpaused()
        logger.info(f"{LoggingContext.TOKEN} User {request.user.email} unpaused token: {token.name}")

        return Response(
            {
                "message": "Token unpaused successfully.",
                "token": ShareTokenDetailSerializer(token).data,
            }
        )

    @action(detail=True, methods=["post"])
    def issue(self, request, uuid=None):
        token = get_object_or_404(self.get_manageable_queryset(), uuid=uuid)

        service = ShareTokenService()
        issuance_request = service.create_issuance_request(
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
        token = get_object_or_404(self.get_queryset().select_related("company"), uuid=uuid)

        whitelist_service = WhitelistService()
        eligibility = whitelist_service.get_receive_eligibility(address)

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
        token = get_object_or_404(self.get_queryset(), uuid=uuid)

        issuances = ShareIssuance.objects.with_token().with_initiated_by().filter_by_token(token)
        if request.query_params.get("status"):
            issuances = issuances.filter(status=request.query_params["status"])
        issuances = issuances.order_by("-completed_at")

        page = self.paginate_queryset(issuances)
        serializer = ShareIssuanceListSerializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    @action(detail=True, methods=["get"])
    def holders(self, request, uuid=None):
        token = get_object_or_404(self.get_queryset(), uuid=uuid)

        service = ShareTokenService()
        holders_data = service.get_token_holders(token)

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
