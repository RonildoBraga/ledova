from rest_framework import status
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from shared.views import AuthenticatedModelViewSet, stream_stored_file
from users.models.investor_classification import InvestorClassification
from users.serializers.investor_classification import (
    InvestorClassificationSerializer,
    InvestorEligibilitySerializer,
)
from users.services.eligibility import investor_eligibility


class InvestorClassificationViewSet(AuthenticatedModelViewSet):
    serializer_class = InvestorClassificationSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    http_method_names = ["get", "post", "delete", "head", "options"]
    ordering = ["-created_at"]
    ordering_fields = ["created_at"]

    def _writing(self):
        return self.action in ("create", "destroy")

    def get_queryset(self):
        scope = (
            InvestorClassification.objects.manageable_by_user
            if self._writing()
            else InvestorClassification.objects.visible_to_user
        )
        return scope(self.request.user).select_related("user_account", "company")

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["get"])
    def eligibility(self, request):
        outcome = investor_eligibility(request.user)
        return Response(InvestorEligibilitySerializer(outcome, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["get"])
    def evidence(self, request, uuid=None):
        classification = self.get_object()
        return stream_stored_file(classification.evidence_file, classification.evidence_mime_type)
