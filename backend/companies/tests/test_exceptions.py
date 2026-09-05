from django.test import SimpleTestCase

from companies.exceptions import InvalidStatusTransitionException


class CompanyExceptionTests(SimpleTestCase):
    def test_invalid_status_transition_formats_states(self):
        exc = InvalidStatusTransitionException(from_status="draft", to_status="approved")
        self.assertEqual(str(exc.detail), "Cannot transition from 'draft' to 'approved'.")
