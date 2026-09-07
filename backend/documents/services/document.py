from documents.models import Document
from documents.tasks.extract import extract_document
from shared.db import atomic


@atomic()
def create_document(uploaded_by, validated_data) -> Document:
    upload = validated_data["file"]
    document = Document.objects.create(
        uploaded_by=uploaded_by,
        document_type=validated_data["document_type"],
        note=validated_data.get("note", ""),
        original_filename=upload.name,
        mime_type=validated_data["mime_type"],
        file=upload,
    )
    extract_document.defer(document_uuid=str(document.uuid))

    return document
