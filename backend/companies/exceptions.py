from rest_framework import status
from rest_framework.exceptions import APIException


class CompanyNotFoundException(APIException):

    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "Company not found."
    default_code = "company_not_found"


class ApplicationAlreadySubmittedException(APIException):

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "This application has already been submitted."
    default_code = "application_already_submitted"


class MissingRequiredDocumentsException(APIException):

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Required documents are missing."
    default_code = "missing_required_documents"

    def __init__(self, missing_documents: list):
        detail = f"Missing required documents: {', '.join(missing_documents)}"
        super().__init__(detail=detail)


class CompanyNotActiveException(APIException):

    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "This company is not active."
    default_code = "company_not_active"


class CompanySuspendedException(APIException):

    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "This company has been suspended."
    default_code = "company_suspended"


class InvalidACNException(APIException):

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Invalid Australian Company Number (ACN)."
    default_code = "invalid_acn"


class InvalidABNException(APIException):

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Invalid Australian Business Number (ABN)."
    default_code = "invalid_abn"


class InvalidStatusTransitionException(APIException):

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Invalid status transition."
    default_code = "invalid_status_transition"

    def __init__(self, from_status: str, to_status: str):
        detail = f"Cannot transition from '{from_status}' to '{to_status}'."
        super().__init__(detail=detail)


class CompanyDocumentNotFoundException(APIException):

    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "Company document not found."
    default_code = "company_document_not_found"


class WalletRequiredException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "A verified company wallet is required for this operation."
    default_code = "wallet_required"


class InvalidWalletAddressException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Invalid Ethereum address format."
    default_code = "invalid_wallet_address"


class InsufficientReviewersException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Exactly 2 reviewers must be assigned."
    default_code = "insufficient_reviewers"


class DuplicateReviewerException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Reviewers must be different users."
    default_code = "duplicate_reviewer"


class InvalidReviewStateException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Cannot perform this action on the current review state."
    default_code = "invalid_review_state"

    def __init__(self, detail=None):
        super().__init__(detail=detail or self.default_detail)


class ReviewAlreadyCompletedException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "This review has already been completed."
    default_code = "review_already_completed"


class InvalidReviewDecisionException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Invalid review decision."
    default_code = "invalid_review_decision"

    def __init__(self, decision=None):
        detail = f"Invalid decision: {decision}" if decision else self.default_detail
        super().__init__(detail=detail)


class NoRecusedReviewException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "No recused review found to replace."
    default_code = "no_recused_review"


class ReviewerAlreadyAssignedException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "This reviewer is already assigned to this application."
    default_code = "reviewer_already_assigned"
