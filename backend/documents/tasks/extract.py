import logging
from typing import Any, Dict

from procrastinate import RetryStrategy

from documents.models import Document
from documents.services.extraction import ExtractionService
from ledova_backend.procrastinate_app import app

logger = logging.getLogger(__name__)


@app.task(retry=RetryStrategy(max_attempts=3, wait=30))
def extract_document(document_uuid: str) -> Dict[str, Any]:
    try:
        document = Document.objects.get(uuid=document_uuid)
    except Document.DoesNotExist:
        logger.error("documents.tasks.extract: document not found uuid=%s", document_uuid)
        return {"status": "error", "error": "document_not_found"}

    extraction = ExtractionService.run(document)
    return {
        "status": extraction.status,
        "extraction_uuid": str(extraction.uuid),
        "duration_ms": extraction.duration_ms,
    }
