from django.conf import settings
from django.test import SimpleTestCase


class AuthorizationConfigurationTest(SimpleTestCase):
    def test_authentication_uses_django_model_backend(self):
        self.assertEqual(
            settings.AUTHENTICATION_BACKENDS,
            ("django.contrib.auth.backends.ModelBackend",),
        )

    def test_default_api_permission_requires_authentication(self):
        self.assertEqual(
            settings.REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"],
            ("rest_framework.permissions.IsAuthenticated",),
        )
