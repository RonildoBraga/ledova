from rest_framework import mixins, viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView


class PublicAPIView(APIView):
    permission_classes = [AllowAny]


class PublicGenericViewSet(viewsets.GenericViewSet):
    permission_classes = [AllowAny]


class PublicListViewSet(mixins.ListModelMixin, PublicGenericViewSet):
    pass


class PublicReadOnlyViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [AllowAny]
    lookup_field = "uuid"


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
