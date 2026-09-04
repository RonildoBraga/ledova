from django.test import SimpleTestCase

from whitelist.exceptions import (
    BatchSizeLimitExceededException,
    WhitelistOperationFailedException,
)


class WhitelistExceptionTests(SimpleTestCase):
    def test_operation_failed_accepts_positional_message(self):
        exc = WhitelistOperationFailedException("Failed to add to whitelist: boom")
        self.assertEqual(str(exc.detail), "Failed to add to whitelist: boom")
        self.assertEqual(exc.status_code, 502)
        self.assertEqual(str(WhitelistOperationFailedException().detail), "Whitelist operation failed.")

    def test_batch_size_limit_formats_max_size(self):
        self.assertEqual(str(BatchSizeLimitExceededException(max_size=100).detail), "Maximum 100 entries per batch.")
