import logging

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from shared.utils.logging_utils import LoggingContext
from shared.views import AuthenticatedModelViewSet
from tokens.exceptions import (
    CapitalIncreaseSubmissionException,
    InvalidTokenStateException,
)
from tokens.filters import CapitalIncreaseFilter
from tokens.models import CapitalIncreaseRequest, ShareToken
from tokens.serializers import (
    CapitalIncreaseCreateSerializer,
    CapitalIncreaseDetailSerializer,
    CapitalIncreaseListSerializer,
    CapitalIncreaseUpdateSerializer,
)

logger = logging.getLogger(__name__)


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
        if self.action in ("create", "update", "partial_update", "destroy"):
            return CapitalIncreaseRequest.objects.with_relations().manageable_by_user(self.request.user)
        return CapitalIncreaseRequest.objects.with_relations().visible_to_user(self.request.user)

    def get_manageable_queryset(self):
        return CapitalIncreaseRequest.objects.with_relations().manageable_by_user(self.request.user)

    def create(self, request, *args, **kwargs):
        token_uuid = request.data.get("token")
        if not token_uuid:
            raise ValidationError({"token": "Token UUID is required."})

        if request.user.is_staff or request.user.is_superuser:
            token = get_object_or_404(ShareToken, uuid=token_uuid)
        else:
            manageable_tokens = ShareToken.objects.manageable_by_user(request.user)
            token = get_object_or_404(manageable_tokens, uuid=token_uuid)

        if token.status != "deployed":
            raise InvalidTokenStateException("Capital increase requests can only be created for deployed tokens.")

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        additional_shares = serializer.validated_data["additional_shares"]
        new_authorized_total = serializer.validated_data["new_authorized_total"]
        current_supply = int(token.total_supply) if token.total_supply else 0

        expected_new_total = current_supply + additional_shares
        if new_authorized_total < expected_new_total:
            raise ValidationError(
                {
                    "new_authorized_total": (
                        f"Must be at least current supply ({current_supply}) + "
                        f"additional shares ({additional_shares}) = {expected_new_total}"
                    )
                }
            )

        capital_increase = serializer.save(token=token)

        logger.info(
            f"{LoggingContext.TOKEN} User {request.user.email} created capital increase request: "
            f"+{capital_increase.additional_shares} {token.symbol} shares"
        )

        response_serializer = CapitalIncreaseDetailSerializer(capital_increase)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        instance = get_object_or_404(self.get_manageable_queryset(), uuid=kwargs.get("uuid"))

        if not instance.can_be_edited:
            raise InvalidTokenStateException("Only draft requests can be edited.")

        partial = kwargs.pop("partial", False)
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        logger.info(
            f"{LoggingContext.TOKEN} User {request.user.email} updated capital increase request: {instance.uuid}"
        )

        return Response(CapitalIncreaseDetailSerializer(instance).data)

    def destroy(self, request, *args, **kwargs):
        instance = get_object_or_404(self.get_manageable_queryset(), uuid=kwargs.get("uuid"))

        if not instance.can_be_edited:
            raise InvalidTokenStateException("Only draft requests can be deleted.")

        logger.info(
            f"{LoggingContext.TOKEN} User {request.user.email} deleted capital increase request: {instance.uuid}"
        )
        instance.delete()

        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def submit(self, request, uuid=None):
        capital_increase = get_object_or_404(self.get_manageable_queryset(), uuid=uuid)

        if not capital_increase.can_be_submitted:
            raise InvalidTokenStateException(
                f"Cannot submit request with status '{capital_increase.get_status_display()}'."
            )

        try:
            capital_increase.submit(request.user)
        except ValueError as e:
            raise CapitalIncreaseSubmissionException(str(e))

        logger.info(
            f"{LoggingContext.TOKEN} User {request.user.email} submitted capital increase request: "
            f"+{capital_increase.additional_shares} {capital_increase.token.symbol} shares"
        )

        return Response(
            {
                "message": "Capital increase request submitted for review.",
                "request": CapitalIncreaseDetailSerializer(capital_increase).data,
            }
        )
