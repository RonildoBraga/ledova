from offerings.serializers import DirectoryTokenListSerializer
from shared.views import AuthenticatedReadOnlyViewSet
from tokens.models import ShareToken
from users.services.eligibility import investor_eligibility


class DirectoryTokenViewSet(AuthenticatedReadOnlyViewSet):

    serializer_class = DirectoryTokenListSerializer
    ordering = ["name"]
    ordering_fields = ["name", "symbol", "created_at"]

    def get_queryset(self):
        if not investor_eligibility(self.request.user).is_eligible:
            return ShareToken.objects.none()
        return (
            ShareToken.objects.with_company()
            .in_directory()
            .with_market_summary()
            .with_issued_shares()
            .with_open_offering()
        )
