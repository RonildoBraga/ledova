from rest_framework import status
from rest_framework.exceptions import APIException


class MissingRequiredDocumentsException(APIException):

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Required documents are missing."
    default_code = "missing_required_documents"

    def __init__(self, missing_documents: list):
        detail = f"Missing required documents: {', '.join(missing_documents)}"
        super().__init__(detail=detail)


class InvalidStatusTransitionException(APIException):

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Invalid status transition."
    default_code = "invalid_status_transition"

    def __init__(self, from_status: str, to_status: str):
        detail = f"Cannot transition from '{from_status}' to '{to_status}'."
        super().__init__(detail=detail)
