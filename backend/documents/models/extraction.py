from django.db import models

from shared.models import BaseModel


class ExtractionStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    RUNNING = "running", "Running"
    SUCCEEDED = "succeeded", "Succeeded"
    FAILED = "failed", "Failed"


class DocumentExtraction(BaseModel):
    """
    One LLM extraction run on a Document.

    A Document can have several extractions over time (re-runs with a
    different model, prompt iteration during PoC, etc.). The latest
    SUCCEEDED row is the one clients consume.
    """

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

    # What model produced this — important for auditing extractions over
    # time as we iterate on the prompt or upgrade to a bigger model.
    model_name = models.CharField(max_length=64, blank=True)

    # The model's raw text reply (before pydantic validation). Useful to
    # debug "why did validation fail" without re-running the model.
    raw_output = models.TextField(blank=True)

    # The validated, structured extraction. Schema depends on the parent
    # Document's document_type — see documents/schemas/.
    parsed_json = models.JSONField(null=True, blank=True)

    # Self-reported confidence in [0, 1]; ours not the model's.
    confidence = models.FloatField(null=True, blank=True)

    # Free-text warnings emitted by the model alongside the extraction
    # ("YTD section not visible", etc.).
    warnings = models.JSONField(default=list, blank=True)

    # On FAILED status, the human-readable failure reason — quota
    # exceeded, schema mismatch, vLLM timeout, etc.
    error = models.TextField(blank=True)

    # Wall-clock time the LLM call took. Cheap to log, useful for
    # capacity planning.
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
