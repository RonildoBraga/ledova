from rest_framework import status
from rest_framework.exceptions import APIException


class RegistryVerificationRequiredException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = (
        "A current matching ABR check must pass before this company can become active. Retry the registry check."
    )
    default_code = "registry_verification_required"


class OfficeholderAttestationRequiredException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = (
        "Record the named officeholder declaration and board-resolution reference, and explicitly attest them."
    )
    default_code = "officeholder_attestation_required"


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


class CompanyHoldsARegisterException(APIException):

    status_code = status.HTTP_409_CONFLICT
    default_detail = "This company holds a register of members and cannot be deleted."
    default_code = "company_holds_a_register"

    def __init__(self, share_classes: int):
        detail = (
            f"{share_classes} on-chain share class(es) carry this company's register of members and the issuance "
            "trail behind it, so the company cannot be deleted. Delist it instead, which keeps the record and "
            "closes the company to investors."
        )
        super().__init__(detail=detail)


class CompanyHoldsShareClassesException(APIException):

    status_code = status.HTTP_409_CONFLICT
    default_detail = "This company still has share classes and cannot be deleted."
    default_code = "company_holds_share_classes"

    def __init__(self, share_classes: int):
        detail = (
            f"This company still has {share_classes} share class(es), none of them on chain. Delete them first, "
            "then the company."
        )
        super().__init__(detail=detail)
