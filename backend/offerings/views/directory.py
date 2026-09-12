from offerings.serializers import DirectoryTokenListSerializer
from shared.views import AuthenticatedReadOnlyViewSet
from tokens.models import ShareToken
from users.services.eligibility import eligible_investor_companies


class DirectoryTokenViewSet(AuthenticatedReadOnlyViewSet):
    unscoped_by_the_base_because = (
        "the directory is scoped by investor eligibility, not by ownership: in_directory() against the "
        "companies eligible_investor_companies returns for this principal. Catalogued as "
        "ShareToken.in_directory in shared/db/policies.py."
    )

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
