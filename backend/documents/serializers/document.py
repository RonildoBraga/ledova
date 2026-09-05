from rest_framework import serializers

from documents.models import Document, DocumentExtraction


class DocumentExtractionSerializer(serializers.ModelSerializer):
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

    class Meta:
        model = Document
        fields = [
            "uuid",
            "document_type",
            "original_filename",
            "mime_type",
            "note",
            "latest_extraction",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["uuid", "mime_type", "latest_extraction", "created_at", "updated_at"]

    def get_latest_extraction(self, obj: Document):

        latest = next(iter(obj.extractions.all()), None)
        if not latest:
            return None
        return DocumentExtractionSerializer(latest).data


class DocumentUploadSerializer(serializers.ModelSerializer):
    file = serializers.FileField(write_only=True)

    class Meta:
        model = Document
        fields = ["document_type", "note", "file"]
