from rest_framework import status
from rest_framework.exceptions import APIException


class VerificationTokenGenerationException(APIException):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = "Unable to initialize verification. Please try again."
    default_code = "verification_token_generation_failed"


class UserAccountNotFoundException(APIException):
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "Customer account not found."
    default_code = "customer_account_not_found"

    def __init__(self, account_type=None):
        if account_type:
            detail = f"{account_type} not found."
        else:
            detail = self.default_detail
        super().__init__(detail)


class InvalidUserAccountOperationException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Invalid customer account operation."
    default_code = "invalid_customer_account_operation"
