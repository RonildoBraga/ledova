from rest_framework import status
from rest_framework.exceptions import APIException


class LlmExtractError(APIException):

    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = "LLM extraction service unavailable"
    default_code = "llm_extract_unavailable"


class LlmExtractValidationError(APIException):

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = "Extracted output failed schema validation"
    default_code = "llm_extract_invalid_output"
