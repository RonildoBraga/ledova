from __future__ import annotations

import io
import logging
from typing import Type

import fitz  # PyMuPDF
from django.utils import timezone
from PIL import Image
from pydantic import BaseModel

from documents.models import Document, DocumentExtraction, ExtractionStatus
from documents.schemas import SCHEMA_BY_TYPE
from integrations.llm_extract import (
    LlmExtractClient,
    LlmExtractError,
    LlmExtractValidationError,
)
from integrations.llm_extract.prompts import PROMPT_BY_TYPE

logger = logging.getLogger(__name__)


class ExtractionService:

    @staticmethod
    def render_first_page(document: Document) -> bytes:
        """One PNG of the first page: the vision model takes images, not PDF bytes."""
        with document.file.open("rb") as fh:
            raw = fh.read()

        if document.mime_type == "application/pdf" or document.original_filename.lower().endswith(".pdf"):
            doc = fitz.open(stream=raw, filetype="pdf")
            try:
                pix = doc[0].get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x zoom is roughly 144 dpi
                return pix.tobytes("png")
            finally:
                doc.close()

        img = Image.open(io.BytesIO(raw)).convert("RGB")
        max_side = 1600
        if max(img.size) > max_side:
            ratio = max_side / max(img.size)
            img = img.resize(
                (int(img.size[0] * ratio), int(img.size[1] * ratio)),
                Image.LANCZOS,
            )
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    @classmethod
    def run(cls, document: Document) -> DocumentExtraction:
        """Always returns a saved row, FAILED with `error` set when anything goes wrong, so the API can show it."""
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
            image_bytes = cls.render_first_page(document)

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
            extraction.save()
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
            extraction.save()
            logger.warning("documents.extraction: doc=%s failed: %s", document.uuid, e.detail)
            return extraction

        except Exception as e:
            extraction.status = ExtractionStatus.FAILED
            extraction.error = f"{type(e).__name__}: {e}"
            extraction.finished_at = timezone.now()
            extraction.save()
            logger.exception("documents.extraction: doc=%s unexpected error", document.uuid)
            return extraction
