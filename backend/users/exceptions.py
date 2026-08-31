"""
Domain-specific exceptions for the users app.

These exceptions represent specific business rule violations and error conditions
related to user profiles, preferences, and tax information.
"""

from rest_framework import status
from rest_framework.exceptions import APIException


class DuplicateResourceException(APIException):
    """Raised when attempting to create a duplicate resource (e.g., waitlist entry)."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = "Resource already exists."
    default_code = "duplicate_resource"

    def __init__(self, resource_type=None, identifier=None):
        if resource_type and identifier:
            detail = f"{resource_type} with {identifier} already exists."
        elif resource_type:
            detail = f"{resource_type} already exists."
        else:
            detail = self.default_detail
        super().__init__(detail)


# =====================================================
# IDENTITY VERIFICATION EXCEPTIONS
# =====================================================


class VerificationServiceUnavailableException(APIException):
    """Raised when the KYC verification service is unavailable."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "Identity verification service is temporarily unavailable. Please try again later."
    default_code = "verification_service_unavailable"

    def __init__(self, detail=None):
        super().__init__(detail or self.default_detail)


class VerificationDataNotFoundException(APIException):
    """Raised when verification data cannot be found for an applicant."""

    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "Verification data not found for this applicant."
    default_code = "verification_data_not_found"

    def __init__(self, applicant_id=None):
        if applicant_id:
            detail = f"Verification data not found for applicant {applicant_id}."
        else:
            detail = self.default_detail
        super().__init__(detail)


class VerificationTokenGenerationException(APIException):
    """Raised when unable to initialize verification with the KYC provider."""

    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = "Unable to initialize verification. Please try again."
    default_code = "verification_token_generation_failed"

    def __init__(self, detail=None):
        super().__init__(detail or self.default_detail)


# Customer Account Exceptions


class UserAccountNotFoundException(APIException):
    """Raised when a requested customer account cannot be found."""

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
    """Raised when an invalid operation is attempted on a customer account."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Invalid customer account operation."
    default_code = "invalid_customer_account_operation"


class UserAccountPermissionException(APIException):
    """Raised when a user doesn't have permission to access a customer account."""

    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "You do not have permission to access this customer account."
    default_code = "customer_account_permission_denied"
