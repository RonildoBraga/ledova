import os
import uuid as uuid_lib
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from documents.querysets.document import DocumentQuerySet
from shared.models import BaseModel
from shared.storage import private_storage


class DocumentType(models.TextChoices):
    PAYSLIP = "payslip", "Payslip"
    BANK_STATEMENT = "bank_statement", "Bank Statement"
    TAX_RETURN = "tax_return", "Tax Return"
    OTHER = "other", "Other"


def document_upload_path(instance: "Document", filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    if instance.classification_id:
        return f"users/supporting-documents/{instance.classification_id}/{instance.uuid}/{uuid_lib.uuid4()}{ext}"
    return f"documents/{instance.uuid}/{uuid_lib.uuid4()}{ext}"


class Document(BaseModel):
    objects = DocumentQuerySet.as_manager()

    uploaded_by = models.ForeignKey(
        "authentication.CustomUser",
        on_delete=models.CASCADE,
        related_name="documents",
    )
    classification = models.ForeignKey(
        "users.InvestorClassification",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="supporting_documents",
    )
    attached_at = models.DateTimeField(null=True, blank=True)
    purged_at = models.DateTimeField(null=True, blank=True)
    document_type = models.CharField(
        max_length=32,
        choices=DocumentType.choices,
        default=DocumentType.PAYSLIP,
    )
    original_filename = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=64, blank=True)
    file = models.FileField(
        upload_to=document_upload_path,
        storage=private_storage,
        max_length=255,
    )
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "documents"
        verbose_name = "Document"
        verbose_name_plural = "Documents"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["uploaded_by", "document_type"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_document_type_display()} — {self.original_filename}"

    @property
    def retention_until(self):
        if self.classification_id:
            return self.classification.evidence_horizon
        days = settings.UNATTACHED_DOCUMENT_RETENTION_DAYS
        return self.created_at + timedelta(days=days) if days else None

    @property
    def content_available(self):
        horizon = self.retention_until
        return bool(self.file) and self.purged_at is None and (horizon is None or horizon > timezone.now())
