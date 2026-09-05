from rest_framework import mixins, status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from documents.models import Document
from documents.serializers.document import (
    DocumentSerializer,
    DocumentUploadSerializer,
)
from documents.tasks.extract import extract_document


class DocumentViewSet(
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
        return Document.objects.for_user(self.request.user).prefetch_related("extractions")

    def get_serializer_class(self):
        if self.action == "create":
            return DocumentUploadSerializer
        return DocumentSerializer

    def create(self, request, *args, **kwargs):
        write_ser = DocumentUploadSerializer(data=request.data)
        write_ser.is_valid(raise_exception=True)

        upload = write_ser.validated_data["file"]
        document = Document.objects.create(
            uploaded_by=request.user,
            document_type=write_ser.validated_data["document_type"],
            note=write_ser.validated_data.get("note", ""),
            original_filename=upload.name,
            mime_type=getattr(upload, "content_type", "") or "",
            file=upload,
        )
        extract_document.defer(document_uuid=str(document.uuid))

        return Response(DocumentSerializer(document).data, status=status.HTTP_202_ACCEPTED)
