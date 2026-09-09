from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from documents.models import Document, DocumentType
from documents.models.document import document_upload_path
from documents.services.access import require_documents_enabled
from documents.tasks.extract import extract_document
from shared.db import atomic, on_commit
from users.models import InvestorClassification, InvestorClassificationStatus


def create_document(uploaded_by, validated_data) -> Document:
    require_documents_enabled()
    retained_copy = None
    try:
        with atomic():
            upload = validated_data["file"]
            document = Document.objects.create(
                uploaded_by=uploaded_by,
                document_type=validated_data.get("document_type", DocumentType.PAYSLIP),
                note=validated_data.get("note", ""),
                original_filename=upload.name,
                mime_type=validated_data["mime_type"],
                file=upload,
            )
            if validated_data.get("classification"):
                document = attach_document(document, uploaded_by, validated_data["classification"])
                retained_copy = (document.file.storage, document.file.name)
            extract_document.defer(document_uuid=str(document.uuid))
    except Exception:
        if retained_copy:
            retained_copy[0].delete(retained_copy[1])
        raise
    return document


def attach_document(document, user, classification_uuid):
    require_documents_enabled()
    copied = None
    storage = document.file.storage
    try:
        with atomic():
            claim = get_object_or_404(
                InvestorClassification.objects.visible_to_user(user).select_for_update(), pk=classification_uuid
            )
            document = get_object_or_404(Document.objects.visible_to_user(user).select_for_update(), pk=document.pk)
            if document.classification_id == claim.pk:
                return document
            if document.classification_id:
                raise ValidationError("This payslip is already attached to a claim.")
            if claim.status != InvestorClassificationStatus.SUBMITTED:
                raise ValidationError("Supporting payslips can only be attached to a submitted claim awaiting review.")
            if document.document_type != DocumentType.PAYSLIP or not document.content_available:
                raise ValidationError("Only an available payslip can be attached to a claim.")
            old_name = document.file.name
            document.classification = claim
            with document.file.open("rb") as original:
                copied = storage.save(document_upload_path(document, document.original_filename), original)
            document.file = copied
            document.attached_at = timezone.now()
            document.save(update_fields=["classification", "file", "attached_at", "updated_at"])
            on_commit(lambda: storage.delete(old_name))
    except Exception:
        if copied:
            storage.delete(copied)
        raise
    return document


@atomic()
def delete_document(document, user):
    require_documents_enabled()
    document = get_object_or_404(Document.objects.visible_to_user(user).select_for_update(), pk=document.pk)
    if document.classification_id:
        raise ValidationError("Supporting evidence is retained with its classification claim and cannot be deleted.")
    document.delete()
