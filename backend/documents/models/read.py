from django.db import models

from shared.models import BaseModel


class DocumentRead(BaseModel):
    actor_id = models.PositiveBigIntegerField()
    document_uuid = models.UUIDField(db_index=True)
    classification_uuid = models.UUIDField(null=True, blank=True)
    kind = models.CharField(
        max_length=16,
        choices=[("document", "Document"), ("file", "File"), ("extraction", "Extraction")],
    )

    class Meta:
        ordering = ["-created_at"]
