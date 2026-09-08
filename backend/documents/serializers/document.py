from django.urls import reverse
from rest_framework import serializers

from documents.models import Document, DocumentExtraction, ExtractionStatus
from shared.uploads import validate_upload


class DocumentExtractionSerializer(serializers.ModelSerializer):
    error = serializers.SerializerMethodField()

    def get_error(self, obj: DocumentExtraction) -> str:
        if obj.status == ExtractionStatus.FAILED:
            return (
                "We couldn't read this document. Try uploading it again, or contact support if the problem continues."
            )
        return ""

    class Meta:
        model = DocumentExtraction
        fields = [
            "uuid",
            "status",
            "model_name",
            "parsed_json",
            "confidence",
            "warnings",
            "error",
            "duration_ms",
            "started_at",
            "finished_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class DocumentSerializer(serializers.ModelSerializer):
    latest_extraction = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = [
            "uuid",
            "document_type",
            "original_filename",
            "mime_type",
            "note",
            "file_url",
            "latest_extraction",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["uuid", "mime_type", "file_url", "latest_extraction", "created_at", "updated_at"]

    def get_latest_extraction(self, obj: Document):

        latest = next(iter(obj.extractions.all()), None)
        if not latest:
            return None
        return DocumentExtractionSerializer(latest).data

    def get_file_url(self, obj: Document):
        if not obj.file:
            return None
        url = reverse("documents:documents-file", kwargs={"uuid": obj.uuid})
        request = self.context.get("request")
        return request.build_absolute_uri(url) if request else url


class DocumentUploadSerializer(serializers.ModelSerializer):
    file = serializers.FileField(write_only=True)

    class Meta:
        model = Document
        fields = ["document_type", "note", "file"]

    def validate(self, data):
        _, data["mime_type"] = validate_upload(data["file"])
        return data
