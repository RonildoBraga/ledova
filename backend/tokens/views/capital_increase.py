from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from shared.views import AuthenticatedModelViewSet
from tokens.exceptions import InvalidTokenStateException
from tokens.filters import CapitalIncreaseFilter
from tokens.models import CapitalIncreaseRequest, ShareToken
from tokens.serializers import (
    CapitalIncreaseCreateSerializer,
    CapitalIncreaseDetailSerializer,
    CapitalIncreaseListSerializer,
    CapitalIncreaseUpdateSerializer,
)

MANAGE_ACTIONS = ("create", "update", "partial_update", "destroy", "submit")


class CapitalIncreaseViewSet(AuthenticatedModelViewSet):
    filterset_class = CapitalIncreaseFilter
    ordering = ["-created_at"]
    ordering_fields = ["created_at", "status", "additional_shares"]

    def get_serializer_class(self):
        if self.action == "create":
            return CapitalIncreaseCreateSerializer
        if self.action in ["update", "partial_update"]:
            return CapitalIncreaseUpdateSerializer
        if self.action == "list":
            return CapitalIncreaseListSerializer
        return CapitalIncreaseDetailSerializer

    def get_queryset(self):
        queryset = CapitalIncreaseRequest.objects.with_relations()
        if self.action in MANAGE_ACTIONS:
            return queryset.manageable_by_user(self.request.user)
        return queryset.visible_to_user(self.request.user)

    def filter_queryset(self, queryset):
        if self.action == "list":
            return super().filter_queryset(queryset)
        return queryset

    def create(self, request, *args, **kwargs):
        token_uuid = request.data.get("token")
        if not token_uuid:
            raise ValidationError({"token": "Token UUID is required."})
        token = get_object_or_404(ShareToken.objects.manageable_by_user(request.user), uuid=token_uuid)

        serializer = self.get_serializer(data=request.data, context={**self.get_serializer_context(), "token": token})
        serializer.is_valid(raise_exception=True)
        capital_increase = serializer.save(token=token)
        return Response(CapitalIncreaseDetailSerializer(capital_increase).data, status=status.HTTP_201_CREATED)

    def perform_destroy(self, instance):
        if not instance.can_be_edited:
            raise InvalidTokenStateException("Only draft requests can be deleted.")
        instance.delete()

    @action(detail=True, methods=["post"])
    def submit(self, request, uuid=None):
        capital_increase = self.get_object()
        capital_increase.submit(request.user)
        return Response(
            {
                "message": "Capital increase request submitted for review.",
                "request": CapitalIncreaseDetailSerializer(capital_increase).data,
            }
        )
