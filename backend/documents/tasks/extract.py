import logging
from typing import Any, Dict

from procrastinate import RetryStrategy

from documents.models import Document
from documents.services.extraction import ExtractionService
from integrations.llm_extract import LlmExtractTransientError
from ledova_backend.procrastinate_app import app
from shared.db import acting_for

logger = logging.getLogger(__name__)


@app.task(retry=RetryStrategy(max_attempts=2, wait=30, retry_exceptions=(LlmExtractTransientError,)))
def extract_document(document_uuid: str, *, principal_id) -> Dict[str, Any]:
    with acting_for(principal_id):
        return _extract_document(document_uuid)


def _extract_document(document_uuid: str) -> Dict[str, Any]:
    try:
        document = Document.objects.get(uuid=document_uuid)
    except Document.DoesNotExist:
        logger.error("documents.tasks.extract: document not found uuid=%s", document_uuid)
        return {"status": "error", "error": "document_not_found"}

    extraction = ExtractionService.run(document)
    if extraction is None:
        return {"status": "skipped", "reason": "document_unavailable"}
    return {
        "status": extraction.status,
        "extraction_uuid": str(extraction.uuid),
        "duration_ms": extraction.duration_ms,
    }
