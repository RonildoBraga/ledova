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
