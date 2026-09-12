from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins
from rest_framework.decorators import action
from rest_framework.response import Response

from offerings.models import Subscription
from offerings.serializers import (
    SubscriptionCreateSerializer,
    SubscriptionDetailSerializer,
    SubscriptionListSerializer,
    SubscriptionWithdrawSerializer,
)
from offerings.services.subscription import submit as submit_subscription
from offerings.services.subscription import withdraw as withdraw_subscription
from shared.views import AuthenticatedGenericViewSet


@extend_schema_view(create=extend_schema(responses={201: SubscriptionDetailSerializer}))
class SubscriptionViewSet(
    mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, AuthenticatedGenericViewSet
):

    lookup_field = "uuid"
    ordering = ["-created_at"]
    ordering_fields = ["created_at", "status", "quantity"]

    scoped_model = Subscription

    def narrow(self, queryset):
        return queryset.with_relations()

    def get_serializer_class(self):
        if self.action == "create":
            return SubscriptionCreateSerializer
        if self.action == "list":
            return SubscriptionListSerializer
        if self.action == "withdraw":
            return SubscriptionWithdrawSerializer
        return SubscriptionDetailSerializer

    def _detail(self, subscription):
        return Response(SubscriptionDetailSerializer(subscription, context=self.get_serializer_context()).data)

    @extend_schema(responses=SubscriptionDetailSerializer)
    @action(detail=True, methods=["post"])
    def submit(self, request, uuid=None):
        return self._detail(submit_subscription(self.get_object(), submitted_by=request.user))

    @extend_schema(responses=SubscriptionDetailSerializer)
    @action(detail=True, methods=["post"])
    def withdraw(self, request, uuid=None):
        serializer = SubscriptionWithdrawSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data.get("reason") or ""
        subscription = withdraw_subscription(self.get_object(), reason=reason)
        return self._detail(subscription)
