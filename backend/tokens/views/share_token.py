import csv

from django.http import HttpResponse
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from companies.models import Company
from shared.views import AuthenticatedModelViewSet
from tokens.filters import ShareTokenFilter
from tokens.models import ShareIssuance, ShareToken
from tokens.serializers import (
    FormerMemberSerializer,
    ShareIssuanceCreateSerializer,
    ShareIssuanceListSerializer,
    ShareIssuanceRequestSerializer,
    ShareRegisterHolderSerializer,
    ShareTokenCreateSerializer,
    ShareTokenDetailSerializer,
    ShareTokenListSerializer,
)
from tokens.services import ShareTokenService
from tokens.services.former_holders import fold_is_stale, former_members_of
from tokens.services.register import (
    REGISTER_HEADERS,
    api_holders,
    export_rows,
    token_register,
)
from tokens.services.share_token_service import delete_share_token

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

    def perform_destroy(self, instance):
        delete_share_token(instance)

    def filter_queryset(self, queryset):
        if self.action == "list":
            return super().filter_queryset(queryset)
        return queryset

    @extend_schema(responses=ShareTokenDetailSerializer)
    def create(self, request, *args, **kwargs):
        if not Company.objects.manageable_by_user(request.user).exists():
            raise PermissionDenied("You must be associated with a company to create tokens.")

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        token = serializer.save()
        return Response(ShareTokenDetailSerializer(token).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        responses=inline_serializer(
            name="TokenDeploymentStarted",
            fields={"message": serializers.CharField(), "token": ShareTokenDetailSerializer()},
        )
    )
    @action(detail=True, methods=["post"])
    def deploy(self, request, uuid=None):
        token = self.get_object()
        ShareTokenService.start_deployment(token)
        return Response({"message": "Token deployment initiated.", "token": ShareTokenDetailSerializer(token).data})

    @extend_schema(
        responses=inline_serializer(
            name="TokenPaused",
            fields={"message": serializers.CharField(), "token": ShareTokenDetailSerializer()},
        )
    )
    @action(detail=True, methods=["post"])
    def pause(self, request, uuid=None):
        token = self.get_object()
        ShareTokenService.or_refuse().pause(token)
        return Response({"message": "Token paused successfully.", "token": ShareTokenDetailSerializer(token).data})

    @extend_schema(
        responses=inline_serializer(
            name="TokenUnpaused",
            fields={"message": serializers.CharField(), "token": ShareTokenDetailSerializer()},
        )
    )
    @action(detail=True, methods=["post"])
    def unpause(self, request, uuid=None):
        token = self.get_object()
        ShareTokenService.or_refuse().unpause(token)
        return Response({"message": "Token unpaused successfully.", "token": ShareTokenDetailSerializer(token).data})

    @extend_schema(
        responses=inline_serializer(
            name="ShareIssuanceRequested",
            fields={
                "message": serializers.CharField(),
                "token": ShareTokenDetailSerializer(),
                "issuance_request": ShareIssuanceRequestSerializer(),
            },
        )
    )
    @action(detail=True, methods=["post"])
    def issue(self, request, uuid=None):
        token = self.get_object()
        serializer = ShareIssuanceCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        issuance_request = ShareTokenService().create_issuance_request(
            token=token, user=request.user, **serializer.validated_data
        )
        return Response(
            {
                "message": "Share issuance request submitted for approval.",
                "token": ShareTokenDetailSerializer(token).data,
                "issuance_request": ShareIssuanceRequestSerializer(issuance_request).data,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["get"])
    def issuances(self, request, uuid=None):
        token = self.get_object()
        issuances = ShareIssuance.objects.with_token().with_initiated_by().with_subscription().filter_by_token(token)
        if request.query_params.get("status"):
            issuances = issuances.filter(status=request.query_params["status"])
        page = self.paginate_queryset(issuances.order_by("-completed_at"))
        return self.get_paginated_response(ShareIssuanceListSerializer(page, many=True).data)

    @extend_schema(
        responses=inline_serializer(
            name="ShareRegister",
            fields={
                "token": inline_serializer(
                    name="ShareRegisterToken",
                    fields={
                        "uuid": serializers.UUIDField(),
                        "name": serializers.CharField(),
                        "symbol": serializers.CharField(),
                        "status": serializers.CharField(),
                        "total_supply": serializers.CharField(),
                    },
                ),
                "holders": ShareRegisterHolderSerializer(many=True),
                "total_holders": serializers.IntegerField(),
                "issued_supply": serializers.CharField(),
                "listed_total": serializers.CharField(),
                "discrepancy": serializers.CharField(),
                "former_members": FormerMemberSerializer(many=True),
                "former_members_as_at": serializers.DateTimeField(allow_null=True),
                "former_members_block": serializers.IntegerField(allow_null=True),
                "former_members_stale": serializers.BooleanField(),
            },
        )
    )
    @action(detail=True, methods=["get"])
    def holders(self, request, uuid=None):
        token = self.get_object()
        rows, discrepancy = token_register(token)
        listed = sum(int(row["balance"]) for row in rows)
        return Response(
            {
                "token": {
                    "uuid": str(token.uuid),
                    "name": token.name,
                    "symbol": token.symbol,
                    "status": token.status,
                    "total_supply": token.total_supply,
                },
                "holders": api_holders(rows),
                "total_holders": len(rows),
                "issued_supply": str(listed + discrepancy),
                "listed_total": str(listed),
                "discrepancy": str(discrepancy),
                "former_members": FormerMemberSerializer(former_members_of(token), many=True).data,
                "former_members_as_at": token.former_holders_folded_at,
                "former_members_block": token.former_holders_block,
                "former_members_stale": fold_is_stale(token),
            }
        )

    @action(detail=True, methods=["get"], url_path="register/export")
    def register_export(self, request, uuid=None):
        token = self.get_object()
        rows = export_rows(token, request.user)
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="register-{token.symbol}.csv"'
        writer = csv.writer(response)
        writer.writerow(REGISTER_HEADERS)
        for row in rows:
            writer.writerow(row)
        return response
