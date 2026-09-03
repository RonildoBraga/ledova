from documents.schemas.payslip import PayslipExtraction

SCHEMA_BY_TYPE: dict[str, type] = {
    "payslip": PayslipExtraction,
}

__all__ = ["PayslipExtraction", "SCHEMA_BY_TYPE"]
