from django.db import models

from shared.models import BaseModel


class DocumentType(models.TextChoices):
    PAYSLIP = "payslip", "Payslip"
    BANK_STATEMENT = "bank_statement", "Bank Statement"
    TAX_RETURN = "tax_return", "Tax Return"
    OTHER = "other", "Other"


def upload_to(instance: "Document", filename: str) -> str:
    """
    Per-user, content-addressed-ish path. Avoid collisions, avoid putting raw
    filenames anywhere that gets logged or returned to clients.
    """
    return f"documents/{instance.uploaded_by_id}/{instance.uuid}/{filename}"


class Document(BaseModel):
    """
    A document uploaded for extraction (payslip, bank statement, etc.).

    The `file` field uses Django's storage abstraction — locally it's the
    filesystem (./media), in production it's the GS_BUCKET_NAME Cloud
    Storage bucket. Same code, see ledova_backend/settings/static.py.

    Extraction is async: uploads enqueue a procrastinate task that creates
    the DocumentExtraction row when done. Clients poll the document URL
    for status.
    """

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

    # Original filename as reported by the client. Display only — never
    # used as a storage path.
    original_filename = models.CharField(max_length=255)

    # MIME type from the upload — drives whether we rasterise a PDF or
    # send the image bytes directly.
    mime_type = models.CharField(max_length=64, blank=True)

    file = models.FileField(upload_to=upload_to)

    # Optional human-supplied note ("first payslip from new employer", etc.)
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
