from rest_framework import status
from rest_framework.exceptions import APIException


class OfferingRefusedException(APIException):

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "The offering cannot be submitted."
    default_code = "offering_refused"


class InvalidOfferingTransitionException(APIException):

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Invalid offering transition."
    default_code = "invalid_offering_transition"

    def __init__(self, from_status: str, to_status: str):
        super().__init__(detail=f"Cannot transition from '{from_status}' to '{to_status}'.")
