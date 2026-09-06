from offerings.serializers import DirectoryTokenListSerializer
from shared.views import AuthenticatedReadOnlyViewSet
from tokens.models import ShareToken
from users.services.eligibility import eligible_investor_companies


class DirectoryTokenViewSet(AuthenticatedReadOnlyViewSet):

    serializer_class = DirectoryTokenListSerializer
    ordering = ["name"]
    ordering_fields = ["name", "symbol", "created_at"]

    def get_queryset(self):
        return (
            ShareToken.objects.with_company()
            .in_directory()
            .filter(company__in=eligible_investor_companies(self.request.user))
            .with_market_summary()
            .with_issued_shares()
            .with_open_offering()
        )
