from django.contrib.auth import get_user_model
from django.test import TestCase

from authentication.serializers.user import (
    EmailVerificationSerializer,
    UserSigninSerializer,
    UserSignupSerializer,
)

User = get_user_model()

NAMED_BY_AUTH_IDENTITY_AND_AUTH_SESSION = {"uuid", "email", "is_email_verified"}


class TheSessionBodyMatchesWhatAuthViewsDeclareTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(email="declared@example.test", password="pw-12345678")

    def test_signin_returns_the_keys_the_view_declares(self):
        self.assertEqual(set(UserSigninSerializer(instance=self.user).data), NAMED_BY_AUTH_IDENTITY_AND_AUTH_SESSION)

    def test_email_verification_returns_the_keys_the_view_declares(self):
        self.assertEqual(set(EmailVerificationSerializer(instance=self.user).data), NAMED_BY_AUTH_IDENTITY_AND_AUTH_SESSION)

    def test_signup_returns_the_keys_the_view_declares(self):
        self.assertEqual(set(UserSignupSerializer(instance=self.user).data), NAMED_BY_AUTH_IDENTITY_AND_AUTH_SESSION)

    def test_the_three_agree_with_each_other(self):
        shapes = {
            frozenset(serializer(instance=self.user).data)
            for serializer in (UserSigninSerializer, EmailVerificationSerializer, UserSignupSerializer)
        }

        self.assertEqual(len(shapes), 1)
