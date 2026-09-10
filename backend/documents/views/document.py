from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from documents.models import Document
from documents.permissions import DocumentsEnabled
from documents.serializers.document import (
    DocumentAttachmentSerializer,
    DocumentSerializer,
    DocumentUploadSerializer,
)
from documents.services.document import (
    attach_document,
    create_document,
    delete_document,
)
from shared.views import stream_stored_file
from shared.views.principal import SetsThePrincipalOnTheConnection
from shared.views.uploads import UploadProtectedView


class DocumentViewSet(
    UploadProtectedView,
    SetsThePrincipalOnTheConnection,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):

    permission_classes = [IsAuthenticated, DocumentsEnabled]
    lookup_field = "uuid"
    serializer_class = DocumentSerializer

    def get_queryset(self):
        return (
            Document.objects.visible_to_user(self.request.user)
            .with_available_content()
            .select_related("classification")
            .prefetch_related("extractions")
        )

    def get_serializer_class(self):
        if self.action == "create":
            return DocumentUploadSerializer
        if self.action == "attach":
            return DocumentAttachmentSerializer
        return DocumentSerializer

    @extend_schema(responses={(200, "*/*"): OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"])
    def file(self, request, uuid=None):
        document = self.get_object()
        return stream_stored_file(document.file, document.mime_type, document.original_filename)

    @extend_schema(responses=DocumentSerializer)
    @action(detail=True, methods=["post"])
    def attach(self, request, uuid=None):
        document = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        attached = attach_document(document, request.user, serializer.validated_data["classification"])
        return Response(DocumentSerializer(attached, context=self.get_serializer_context()).data)

    def perform_destroy(self, instance):
        delete_document(instance, self.request.user)

    @extend_schema(responses=DocumentSerializer)
    def create(self, request, *args, **kwargs):
        write_ser = self.get_serializer(data=request.data)
        write_ser.is_valid(raise_exception=True)

        document = create_document(request.user, write_ser.validated_data)

        return Response(
            DocumentSerializer(document, context=self.get_serializer_context()).data,
            status=status.HTTP_202_ACCEPTED,
        )
