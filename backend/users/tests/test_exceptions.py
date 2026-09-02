from django.test import SimpleTestCase

from users.exceptions import (
    UserAccountNotFoundException,
    VerificationTokenGenerationException,
)


class UserExceptionTests(SimpleTestCase):
    def test_verification_token_generation_defaults_and_accepts_message(self):
        self.assertEqual(VerificationTokenGenerationException.status_code, 502)
        self.assertEqual(
            str(VerificationTokenGenerationException().detail), "Unable to initialize verification. Please try again."
        )
        self.assertEqual(str(VerificationTokenGenerationException("later").detail), "later")

    def test_user_account_not_found_formats_account_type(self):
        self.assertEqual(str(UserAccountNotFoundException("Retail account").detail), "Retail account not found.")
        self.assertEqual(str(UserAccountNotFoundException().detail), "Customer account not found.")
