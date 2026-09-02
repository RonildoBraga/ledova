from assets.serializers.asset import CountrySerializer
from shared.models.country import Country
from shared.views.base import AuthenticatedReferenceDataViewSet


class CountryViewSet(AuthenticatedReferenceDataViewSet):
    """Countries for the signup flow (country of citizenship)."""

    queryset = Country.objects.filter(is_available=True)
    serializer_class = CountrySerializer
    ordering = ["name"]
    ordering_fields = ["name", "code"]
