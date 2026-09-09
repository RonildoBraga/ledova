from shared.views import AuthenticatedReadOnlyViewSet
from tokens.filters import ShareIssuanceRequestFilter
from tokens.models import ShareIssuanceRequest
from tokens.serializers import ShareIssuanceRequestSerializer


class ShareIssuanceRequestViewSet(AuthenticatedReadOnlyViewSet):
    serializer_class = ShareIssuanceRequestSerializer
    filterset_class = ShareIssuanceRequestFilter
    ordering = ["-created_at", "-uuid"]
    ordering_fields = ["created_at", "status", "amount"]

    def get_queryset(self):
        return ShareIssuanceRequest.objects.with_relations().visible_to_user(self.request.user)
