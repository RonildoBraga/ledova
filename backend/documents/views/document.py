from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from documents.models import Document
from documents.serializers.document import (
    DocumentSerializer,
    DocumentUploadSerializer,
)
from documents.services.document import create_document
from shared.views import stream_stored_file
from shared.views.principal import SetsThePrincipalOnTheConnection


class DocumentViewSet(
    SetsThePrincipalOnTheConnection,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):

    permission_classes = [IsAuthenticated]
    lookup_field = "uuid"
    serializer_class = DocumentSerializer

    def get_queryset(self):
        return Document.objects.visible_to_user(self.request.user).prefetch_related("extractions")

    def get_serializer_class(self):
        if self.action == "create":
            return DocumentUploadSerializer
        return DocumentSerializer

    @action(detail=True, methods=["get"])
    def file(self, request, uuid=None):
        document = self.get_object()
        return stream_stored_file(document.file, document.mime_type, document.original_filename)

    @extend_schema(responses=DocumentSerializer)
    def create(self, request, *args, **kwargs):
        write_ser = self.get_serializer(data=request.data)
        write_ser.is_valid(raise_exception=True)

        document = create_document(request.user, write_ser.validated_data)

        return Response(
            DocumentSerializer(document, context=self.get_serializer_context()).data,
            status=status.HTTP_202_ACCEPTED,
        )
