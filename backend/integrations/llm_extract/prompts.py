"""
Per-document-type extraction prompts.

The prompt enumerates exact field names and relies on the server's JSON mode plus a separate pydantic pass;
passing the schema as the response format made the model rename fields.
"""

_RULES = """
Rules:
  - All amounts must be plain numbers without currency symbols or commas
    (e.g. 1234.56, not "$1,234.56" or "1234,56").
  - All dates must be YYYY-MM-DD.
  - Use null (not 0, not empty string) for fields you cannot find.
  - Do not invent values. If you have to guess, leave the field null
    and add a note in extraction_warnings.
  - Set confidence honestly: 1.0 if every field is unambiguous, lower
    if you had to interpret unclear text, very low if pages are blurry
    or the document type doesn't match what was asked for.
""".strip()


PAYSLIP_PROMPT = f"""
You are extracting structured information from an Australian payslip.
Return ONLY a JSON object with EXACTLY these keys (no extras, no synonyms):

  employee_name        - full name of the employee
  employer_name        - trading name of the employer (the company, not the bank)
  abn                  - 11-digit Australian Business Number, no spaces. Null if absent.
  period_start         - pay period START date, YYYY-MM-DD
  period_end           - pay period END date, YYYY-MM-DD
  pay_date             - the date the payment was made, YYYY-MM-DD
  gross_pay            - gross pay this period (positive number)
  net_pay              - net (take-home) pay this period (positive number)
  tax_withheld         - PAYG tax withheld this period (positive number, ignore minus signs)
  superannuation       - employer super contribution this period
  ytd_gross            - year-to-date gross pay
  ytd_tax              - year-to-date tax withheld
  confidence           - 0..1, your self-assessed confidence
  extraction_warnings  - array of short strings noting any ambiguities

{_RULES}
""".strip()


PROMPT_BY_TYPE: dict[str, str] = {
    "payslip": PAYSLIP_PROMPT,
}
