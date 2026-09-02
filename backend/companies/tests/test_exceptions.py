from django.test import SimpleTestCase

from companies.exceptions import (
    InvalidReviewStateException,
    InvalidStatusTransitionException,
)


class CompanyExceptionTests(SimpleTestCase):
    def test_invalid_review_state_accepts_positional_message(self):
        self.assertEqual(str(InvalidReviewStateException("Cannot assign reviewers").detail), "Cannot assign reviewers")
        self.assertEqual(
            str(InvalidReviewStateException().detail), "Cannot perform this action on the current review state."
        )

    def test_invalid_status_transition_formats_states(self):
        exc = InvalidStatusTransitionException(from_status="draft", to_status="approved")
        self.assertEqual(str(exc.detail), "Cannot transition from 'draft' to 'approved'.")
