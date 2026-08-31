"""
Orchestrates the LLM extraction flow for a single Document.

Called from the procrastinate task. Responsibilities:

  1. Load the Document and read its file bytes (Django storage handles
     local-fs vs GCS transparently).
  2. Rasterise PDFs page-by-page via PyMuPDF — VLMs need images, not
     PDF bytes. For now we send page 1 only; multi-page payslips are
     rare. Bank statements (Phase 5) will need a loop.
  3. Pick the right prompt + schema for the Document.document_type.
  4. Call the LLM, validate, write a DocumentExtraction row, return it.

Anything async/retry-related belongs to the task layer, not here.
"""

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

logger = logging.getLogger("ledova_backend")


class ExtractionService:
    """Stateless. Pure functions wrapping a small bit of orchestration."""

    @staticmethod
    def render_first_page(document: Document) -> bytes:
        """Return one PNG with the document's first page."""
        with document.file.open("rb") as fh:
            raw = fh.read()

        # PDF -> rasterise page 1 at 2× zoom (~144 dpi).
        if document.mime_type == "application/pdf" or document.original_filename.lower().endswith(".pdf"):
            doc = fitz.open(stream=raw, filetype="pdf")
            try:
                pix = doc[0].get_pixmap(matrix=fitz.Matrix(2, 2))
                return pix.tobytes("png")
            finally:
                doc.close()

        # Image — open, downscale if huge, re-encode as PNG so the LLM
        # always receives a known format.
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
        """
        Run an extraction and persist it. Always returns a saved
        DocumentExtraction row — even on failure (with status=FAILED
        and `error` populated) — so the API can surface what happened.
        """
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

        except Exception as e:  # noqa: BLE001 — catch-all so the task DB row reflects truth
            extraction.status = ExtractionStatus.FAILED
            extraction.error = f"{type(e).__name__}: {e}"
            extraction.finished_at = timezone.now()
            extraction.save()
            logger.exception("documents.extraction: doc=%s unexpected error", document.uuid)
            return extraction
