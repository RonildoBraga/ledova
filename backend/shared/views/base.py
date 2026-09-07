from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated

from shared.views.principal import SetsThePrincipalOnTheConnection


class AuthenticatedGenericViewSet(SetsThePrincipalOnTheConnection, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]


class AuthenticatedListViewSet(mixins.ListModelMixin, AuthenticatedGenericViewSet):
    pass


class AuthenticatedModelViewSet(SetsThePrincipalOnTheConnection, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    lookup_field = "uuid"


class AuthenticatedReadOnlyViewSet(SetsThePrincipalOnTheConnection, viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    lookup_field = "uuid"
