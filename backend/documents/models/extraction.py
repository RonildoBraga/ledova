from django.db import models

from shared.models import BaseModel


class ExtractionStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    RUNNING = "running", "Running"
    SUCCEEDED = "succeeded", "Succeeded"
    FAILED = "failed", "Failed"


class DocumentExtraction(BaseModel):
    """One LLM run over a Document; a document keeps every run and clients read the newest."""

    document = models.ForeignKey(
        "documents.Document",
        on_delete=models.CASCADE,
        related_name="extractions",
    )
    status = models.CharField(
        max_length=16,
        choices=ExtractionStatus.choices,
        default=ExtractionStatus.PENDING,
    )
    model_name = models.CharField(max_length=64, blank=True)
    raw_output = models.TextField(blank=True)
    parsed_json = models.JSONField(null=True, blank=True)
    confidence = models.FloatField(null=True, blank=True)
    warnings = models.JSONField(default=list, blank=True)
    error = models.TextField(blank=True)
    duration_ms = models.IntegerField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "document_extractions"
        verbose_name = "Document Extraction"
        verbose_name_plural = "Document Extractions"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["document", "status"]),
        ]

    def __str__(self) -> str:
        return f"{self.document_id} — {self.status}"
