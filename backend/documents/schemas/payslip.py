"""
Payslip extraction schema.

Mirror of scripts/llm-spike/schemas.py::PayslipExtraction — the shape
we validated Qwen2.5-VL-7B against during Phase 0. Don't drift these
two casually.
"""

from datetime import (
    date as Date,  # aliased so we can also use 'date' as a field name if needed
)
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field

Money = Annotated[Decimal, Field(description="Amount in document's currency, no symbol")]
Confidence = Annotated[float, Field(ge=0.0, le=1.0, description="Model's self-assessed confidence")]


class PayslipExtraction(BaseModel):
    employee_name: str | None = Field(None, description="Full name of the employee")
    employer_name: str | None = Field(None, description="Trading name of the employer")
    abn: str | None = Field(
        None,
        description="Australian Business Number, 11 digits with spaces removed. Null if not present.",
    )

    period_start: Date | None = Field(None, description="Pay period start date, YYYY-MM-DD")
    period_end: Date | None = Field(None, description="Pay period end date, YYYY-MM-DD")
    pay_date: Date | None = Field(None, description="Date the payment was made")

    gross_pay: Money | None = Field(None, description="Gross pay for this period")
    net_pay: Money | None = Field(None, description="Net pay (take-home) for this period")
    tax_withheld: Money | None = Field(None, description="PAYG tax withheld for this period")
    superannuation: Money | None = Field(None, description="Super contribution for this period")

    ytd_gross: Money | None = Field(None, description="Year-to-date gross pay")
    ytd_tax: Money | None = Field(None, description="Year-to-date tax withheld")

    confidence: Confidence = Field(0.0, description="0-1 self-assessed confidence in the extraction")
    extraction_warnings: list[str] = Field(
        default_factory=list,
        description="Ambiguities or fields that were guessed or coerced",
    )
