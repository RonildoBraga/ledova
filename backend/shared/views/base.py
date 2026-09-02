from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated


class AuthenticatedGenericViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]


class AuthenticatedListViewSet(mixins.ListModelMixin, AuthenticatedGenericViewSet):
    pass


class AuthenticatedModelViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    lookup_field = "uuid"


class AuthenticatedReadOnlyViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated]
    lookup_field = "uuid"


class AuthenticatedReferenceDataViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    lookup_field = "uuid"
