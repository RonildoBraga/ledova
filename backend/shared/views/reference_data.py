"""
Views for reference data in the shared app.
Provides read-only access to reference data like countries.
"""

from assets.serializers.asset import CountrySerializer
from shared.models.country import Country
from shared.views.base import AuthenticatedReferenceDataViewSet


class CountryViewSet(AuthenticatedReferenceDataViewSet):
    """
    API endpoint that allows countries to be viewed.

    This endpoint returns the list of available countries with their UUIDs,
    for use in the signup flow for country of citizenship.
    """

    queryset = Country.objects.filter(is_available=True)
    serializer_class = CountrySerializer
    ordering = ["name"]
    ordering_fields = ["name", "code"]
