from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated

from shared.views.principal import SetsThePrincipalOnTheConnection
from shared.views.scope import ScopesToThePrincipal


class AuthenticatedGenericViewSet(ScopesToThePrincipal, SetsThePrincipalOnTheConnection, viewsets.GenericViewSet):
    abstract = True
    permission_classes = [IsAuthenticated]


class AuthenticatedListViewSet(mixins.ListModelMixin, AuthenticatedGenericViewSet):
    abstract = True


class AuthenticatedModelViewSet(ScopesToThePrincipal, SetsThePrincipalOnTheConnection, viewsets.ModelViewSet):
    abstract = True
    permission_classes = [IsAuthenticated]
    lookup_field = "uuid"


class AuthenticatedReadOnlyViewSet(
    ScopesToThePrincipal, SetsThePrincipalOnTheConnection, viewsets.ReadOnlyModelViewSet
):
    abstract = True
    permission_classes = [IsAuthenticated]
    lookup_field = "uuid"
