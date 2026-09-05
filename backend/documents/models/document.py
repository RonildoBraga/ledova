from django.db import models

from documents.querysets.document import DocumentQuerySet
from shared.models import BaseModel


class DocumentType(models.TextChoices):
    PAYSLIP = "payslip", "Payslip"
    BANK_STATEMENT = "bank_statement", "Bank Statement"
    TAX_RETURN = "tax_return", "Tax Return"
    OTHER = "other", "Other"


def upload_to(instance: "Document", filename: str) -> str:
    return f"documents/{instance.uploaded_by_id}/{instance.uuid}/{filename}"


class Document(BaseModel):
    objects = DocumentQuerySet.as_manager()

    uploaded_by = models.ForeignKey(
        "authentication.CustomUser",
        on_delete=models.CASCADE,
        related_name="documents",
    )
    document_type = models.CharField(
        max_length=32,
        choices=DocumentType.choices,
        default=DocumentType.PAYSLIP,
    )
    original_filename = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=64, blank=True)
    file = models.FileField(upload_to=upload_to)
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
