from drf_spectacular.utils import extend_schema, extend_schema_view
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


@extend_schema_view(
    create=extend_schema(responses=OfferingDetailSerializer),
    update=extend_schema(responses=OfferingDetailSerializer),
    partial_update=extend_schema(responses=OfferingDetailSerializer),
)
class OfferingViewSet(AuthenticatedModelViewSet):
    ordering = ["-created_at"]
    ordering_fields = ["created_at", "status", "opens_at"]

    scoped_model = Offering
    manage_actions = MANAGE_ACTIONS

    def narrow(self, queryset):
        return queryset.with_relations()

    def get_serializer_class(self):
        if self.action in ["create", "update", "partial_update"]:
            return OfferingWriteSerializer
        if self.action == "list":
            return OfferingListSerializer
        if self.action == "withdraw":
            return OfferingWithdrawSerializer
        return OfferingDetailSerializer

    def perform_destroy(self, instance):
        if not instance.can_be_deleted:
            raise OfferingRefusedException(NOT_DELETABLE)
        instance.delete()

    @extend_schema(responses=OfferingDetailSerializer)
    @action(detail=True, methods=["post"])
    def submit(self, request, uuid=None):
        offering = self.get_object()
        submit_offering(offering, submitted_by=request.user)
        return Response(OfferingDetailSerializer(offering, context=self.get_serializer_context()).data)

    @extend_schema(responses=IssuerSubscriptionSerializer(many=True), filters=False)
    @action(detail=True, methods=["get"])
    def subscriptions(self, request, uuid=None):
        offering = self.get_object()
        subscriptions = Subscription.objects.filter(
            offering__in=Offering.objects.manageable_by_user(request.user)
        ).for_issuer(offering)
        page = self.paginate_queryset(subscriptions)
        return self.get_paginated_response(IssuerSubscriptionSerializer(page, many=True).data)

    @extend_schema(responses=OfferingDetailSerializer)
    @action(detail=True, methods=["post"])
    def withdraw(self, request, uuid=None):
        offering = self.get_object()
        serializer = OfferingWithdrawSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        transition_offering(offering, "withdraw", reason=serializer.validated_data.get("reason") or "")
        return Response(OfferingDetailSerializer(offering, context=self.get_serializer_context()).data)
