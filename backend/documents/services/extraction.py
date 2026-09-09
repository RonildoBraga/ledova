from __future__ import annotations

import logging
from typing import Type

from django.utils import timezone
from pydantic import BaseModel

from documents.models import Document, DocumentExtraction, ExtractionStatus
from documents.schemas import SCHEMA_BY_TYPE
from documents.services.access import documents_enabled
from integrations.llm_extract import (
    LlmExtractClient,
    LlmExtractError,
    LlmExtractTransientError,
    LlmExtractValidationError,
)
from integrations.llm_extract.prompts import PROMPT_BY_TYPE
from shared.db import atomic
from shared.upload_processing import process_upload
from shared.upload_scanner import scan_upload
from shared.uploads import read_bounded

logger = logging.getLogger(__name__)


class ExtractionService:

    @staticmethod
    def render_first_page(document: Document, raw: bytes) -> bytes:
        scan_upload(raw)
        return process_upload(raw, mode="render")

    @classmethod
    def run(cls, document: Document) -> DocumentExtraction | None:
        with atomic():
            document = Document.objects.select_for_update().filter(pk=document.pk).first()
            if document is None or not document.content_available or not documents_enabled():
                return None
            extraction = DocumentExtraction.objects.create(
                document=document,
                status=ExtractionStatus.RUNNING,
                started_at=timezone.now(),
            )

        try:
            doc_type = document.document_type
            if doc_type not in PROMPT_BY_TYPE or doc_type not in SCHEMA_BY_TYPE:
                raise ValueError(f"Unsupported document_type: {doc_type}")

            prompt = PROMPT_BY_TYPE[doc_type]
            schema: Type[BaseModel] = SCHEMA_BY_TYPE[doc_type]
            raw = cls._read_available_bytes(document)
            if raw is None:
                DocumentExtraction.objects.filter(pk=extraction.pk).delete()
                return None
            image_bytes = cls.render_first_page(document, raw)

            client = LlmExtractClient()
            result = client.extract(
                image_bytes=image_bytes,
                prompt=prompt,
                schema=schema,
            )

            parsed_dict = result.parsed.model_dump(mode="json")
            extraction.status = ExtractionStatus.SUCCEEDED
            extraction.raw_output = result.raw_output
            extraction.parsed_json = parsed_dict
            extraction.confidence = parsed_dict.get("confidence")
            extraction.warnings = parsed_dict.get("extraction_warnings", []) or []
            extraction.duration_ms = result.duration_ms
            extraction.model_name = result.model_used
            extraction.finished_at = timezone.now()
            if not cls._save_if_retained(extraction):
                return None
            logger.info(
                "documents.extraction: doc=%s succeeded in %dms confidence=%s",
                document.uuid,
                result.duration_ms,
                extraction.confidence,
            )
            return extraction

        except (LlmExtractError, LlmExtractValidationError) as e:
            extraction.status = ExtractionStatus.FAILED
            extraction.error = f"{type(e).__name__}: {e.detail}"
            extraction.finished_at = timezone.now()
            if not cls._save_if_retained(extraction):
                return None
            logger.warning("documents.extraction: doc=%s failed: %s", document.uuid, e.detail)
            if isinstance(e, LlmExtractTransientError):
                raise
            return extraction

        except Exception as e:
            extraction.status = ExtractionStatus.FAILED
            extraction.error = f"{type(e).__name__}: {e}"
            extraction.finished_at = timezone.now()
            if not cls._save_if_retained(extraction):
                return None
            logger.exception("documents.extraction: doc=%s unexpected error", document.uuid)
            return extraction

    @staticmethod
    @atomic()
    def _read_available_bytes(document):
        document = Document.objects.select_for_update().filter(pk=document.pk).first()
        if document is None or not document.content_available or not documents_enabled():
            return None
        with document.file.open("rb") as stream:
            return read_bounded(stream)

    @staticmethod
    @atomic()
    def _save_if_retained(extraction):
        document = Document.objects.select_for_update().filter(pk=extraction.document_id).first()
        if document is None or not document.content_available or not documents_enabled():
            DocumentExtraction.objects.filter(pk=extraction.pk).delete()
            return False
        extraction.save()
        return True
