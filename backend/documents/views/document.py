import logging

from rest_framework import mixins, status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from documents.models import Document
from documents.querysets.document import DocumentQuerySet
from documents.serializers.document import (
    DocumentSerializer,
    DocumentUploadSerializer,
)
from documents.tasks.extract import extract_document

logger = logging.getLogger("ledova_backend")


class DocumentViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """
    /api/v1/documents/

      POST   .                  upload a document, queue extraction
      GET    .                  list current user's documents
      GET    /{uuid}/           retrieve a document + its latest extraction
      DELETE /{uuid}/           delete the document + its extractions

    Async by design: POST returns 202 with the document UUID; clients
    poll the GET endpoint for the extraction status + result.

    DELETE removes the DB rows (extractions cascade off the foreign key).
    The underlying file in storage is left as-is for the PoC — orphan
    files are cheap and we can add a storage-cleanup signal later if it
    becomes a real issue.
    """

    permission_classes = [IsAuthenticated]
    lookup_field = "uuid"
    serializer_class = DocumentSerializer

    def get_queryset(self) -> DocumentQuerySet:
        return DocumentQuerySet(Document).for_user(self.request.user).with_latest_extraction()

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

        # Fire off the extraction. The procrastinate worker picks it up
        # asynchronously; the response returns immediately.
        extract_document.defer(document_uuid=str(document.uuid))
        logger.info("documents: queued extraction for %s (%s)", document.uuid, document.document_type)

        read_ser = DocumentSerializer(document)
        return Response(read_ser.data, status=status.HTTP_202_ACCEPTED)
