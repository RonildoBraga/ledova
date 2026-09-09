import logging

from documents.models import Document
from shared.db import atomic
from users.models import InvestorClassification

logger = logging.getLogger(__name__)


@atomic()
def purge_document(document_uuid, moment):
    document = Document.objects.filter(pk=document_uuid).first()
    if document is None:
        return False
    if document.classification_id:
        InvestorClassification.objects.select_for_update().get(pk=document.classification_id)
    document = Document.objects.select_for_update().get(pk=document_uuid)
    if not Document.objects.retention_due(moment).filter(pk=document_uuid).exists():
        return False
    document.file.delete(save=False)
    document.extractions.all().delete()
    document.original_filename = ""
    document.note = ""
    document.mime_type = ""
    document.purged_at = moment
    document.save(update_fields=["file", "original_filename", "note", "mime_type", "purged_at", "updated_at"])
    return True


def purge_expired_documents(moment, limit=200):
    purged = failed = 0
    ids = list(Document.objects.retention_due(moment).order_by("created_at").values_list("pk", flat=True)[:limit])
    for document_uuid in ids:
        try:
            purged += int(purge_document(document_uuid, moment))
        except Exception:
            failed += 1
            logger.error("Supporting document purge failed for %s", document_uuid, exc_info=True)
    return {"purged": purged, "failed": failed}
