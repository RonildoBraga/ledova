from django.test import SimpleTestCase

from users.services.identity import VerificationTokenGenerationException


class UserExceptionTests(SimpleTestCase):
    def test_verification_token_generation_defaults_and_accepts_message(self):
        self.assertEqual(VerificationTokenGenerationException.status_code, 502)
        self.assertEqual(
            str(VerificationTokenGenerationException().detail), "Unable to initialize verification. Please try again."
        )
        self.assertEqual(str(VerificationTokenGenerationException("later").detail), "later")
