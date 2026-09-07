from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from authentication.managers.user import EmailLookupResult, EmailLookupState
from authentication.services.email_lookup import find_unique_user

User = get_user_model()


class FindUniqueUserTests(TestCase):
    def test_a_single_match_is_returned(self):
        user = User(email="lookup-unique@example.test")
        user.set_password("current-password-123")
        user.save()

        self.assertEqual(find_unique_user("lookup-unique@example.test"), user)

    def test_an_absent_address_gives_none(self):
        self.assertIsNone(find_unique_user("lookup-absent@example.test"))

    def test_an_ambiguous_address_gives_none_rather_than_a_guess(self):
        with patch.object(
            User.objects,
            "resolve_email",
            return_value=EmailLookupResult(EmailLookupState.AMBIGUOUS),
        ):
            self.assertIsNone(find_unique_user("lookup-ambiguous@example.test"))

    def test_an_inactive_account_still_resolves(self):
        user = User(email="lookup-inactive@example.test", is_active=False)
        user.set_password("current-password-123")
        user.save()

        self.assertEqual(find_unique_user("lookup-inactive@example.test"), user)
