from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.response import Response

from offerings.exceptions import OfferingRefusedException
from offerings.models import Offering, Subscription
from offerings.serializers import (
    IssuerSubscriptionSerializer,
    OfferingDetailSerializer,
    OfferingListSerializer,
    OfferingWithdrawSerializer,
    OfferingWriteSerializer,
)
from offerings.services import submit_offering, transition_offering
from shared.views import AuthenticatedModelViewSet

MANAGE_ACTIONS = ("create", "update", "partial_update", "destroy", "submit", "withdraw")
NOT_DELETABLE = "Only a draft offering can be deleted."


class OfferingViewSet(AuthenticatedModelViewSet):
    ordering = ["-created_at"]
    ordering_fields = ["created_at", "status", "opens_at"]

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return OfferingWriteSerializer
        if self.action == "list":
            return OfferingListSerializer
        if self.action == "withdraw":
            return OfferingWithdrawSerializer
        return OfferingDetailSerializer

    def get_queryset(self):
        queryset = Offering.objects.with_relations()
        if self.action in MANAGE_ACTIONS:
            return queryset.manageable_by_user(self.request.user)
        return queryset.visible_to_user(self.request.user)

    def perform_destroy(self, instance):
        if not instance.can_be_edited:
            raise OfferingRefusedException(NOT_DELETABLE)
        instance.delete()

    @extend_schema(responses=OfferingDetailSerializer)
    @action(detail=True, methods=["post"])
    def submit(self, request, uuid=None):
        offering = self.get_object()
        submit_offering(offering, submitted_by=request.user)
        return Response(OfferingDetailSerializer(offering, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["get"])
    def subscriptions(self, request, uuid=None):
        offering = self.get_object()
        page = self.paginate_queryset(Subscription.objects.for_issuer(offering))
        return self.get_paginated_response(IssuerSubscriptionSerializer(page, many=True).data)

    @extend_schema(responses=OfferingDetailSerializer)
    @action(detail=True, methods=["post"])
    def withdraw(self, request, uuid=None):
        offering = self.get_object()
        serializer = OfferingWithdrawSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        transition_offering(offering, "withdraw", reason=serializer.validated_data.get("reason") or "")
        return Response(OfferingDetailSerializer(offering, context=self.get_serializer_context()).data)
