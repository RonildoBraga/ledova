"""
Pydantic schemas for extracted document data.

These are the SOURCE OF TRUTH for what fields the LLM should produce per
document type. The frontend's TypeScript types should be derived from
these (or, more pragmatically, just hand-mirrored — fields don't change
that often).

Keep schemas focused on what we'll actually wire into business logic.
Resist the temptation to extract everything on the page — the model
gets more accurate when the schema is small and targeted.

The Payslip schema is intentionally identical in shape to the spike
schema at scripts/llm-spike/schemas.py — that's the contract we
validated Qwen2.5-VL-7B against, and graduating it to backend code
preserves that validation.
"""

from documents.schemas.payslip import PayslipExtraction

# Map document_type -> pydantic class. Keeps tasks/views generic.
SCHEMA_BY_TYPE: dict[str, type] = {
    "payslip": PayslipExtraction,
}

__all__ = ["PayslipExtraction", "SCHEMA_BY_TYPE"]
