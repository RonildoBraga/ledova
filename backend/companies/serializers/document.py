import os

from rest_framework import serializers

from companies.models import CompanyDocument


class CompanyDocumentSerializer(serializers.ModelSerializer):

    document_type_display = serializers.CharField(
        source="get_document_type_display",
        read_only=True,
    )

    file_url = serializers.SerializerMethodField()

    file = serializers.FileField(write_only=True, required=False)

    external_url = serializers.URLField(write_only=True, required=False)

    file_size = serializers.IntegerField(required=False)
    mime_type = serializers.CharField(required=False)

    class Meta:
        model = CompanyDocument
        fields = [
            "uuid",
            "document_type",
            "document_type_display",
            "name",
            "file",
            "external_url",
            "file_url",
            "file_size",
            "mime_type",
            "is_verified",
            "verified_at",
            "created_at",
        ]
        read_only_fields = ["uuid", "is_verified", "verified_at", "created_at"]

    def get_file_url(self, obj):
        request = self.context.get("request")
        if obj.file:
            url = obj.file.url
            if request:
                return request.build_absolute_uri(url)
            return url
        return obj.external_url

    MAX_FILE_SIZE = 10 * 1024 * 1024
    ALLOWED_MIME_TYPES = {"application/pdf", "image/png", "image/jpeg"}
    ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}

    def validate(self, data):
        file = data.get("file")
        external_url = data.get("external_url")

        if not file and not external_url:
            raise serializers.ValidationError("Either 'file' or 'external_url' must be provided.")

        if file:
            if file.size > self.MAX_FILE_SIZE:
                raise serializers.ValidationError({"file": "File size must not exceed 10 MB."})

            mime = file.content_type or ""
            if mime not in self.ALLOWED_MIME_TYPES:
                raise serializers.ValidationError({"file": "Only PDF and image files (PNG, JPEG) are allowed."})

            ext = os.path.splitext(file.name)[1].lower()
            if ext not in self.ALLOWED_EXTENSIONS:
                raise serializers.ValidationError({"file": "Only .pdf, .png, .jpg, .jpeg files are allowed."})

            data["file_size"] = file.size
            data["mime_type"] = mime
        elif external_url:
            if not data.get("file_size"):
                raise serializers.ValidationError({"file_size": "This field is required when using external_url."})
            if not data.get("mime_type"):
                raise serializers.ValidationError({"mime_type": "This field is required when using external_url."})

        return data

    def create(self, validated_data):
        file = validated_data.pop("file", None)
        external_url = validated_data.pop("external_url", "")

        document = CompanyDocument(
            **validated_data,
            external_url=external_url,
        )

        if file:
            document.file = file

        document.save()
        return document
