"""
Tests for CustomUser model and related functionality.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from authentication.models.user_token import UserToken

User = get_user_model()


class CustomUserModelTest(TestCase):
    """Test suite for CustomUser model."""

    def setUp(self):
        """Set up test data."""
        self.user_data = {"email": "test@example.com", "password": "testpass123"}
        self.admin_user_data = {"email": "admin@example.com", "password": "adminpass123"}

    def test_create_user(self):
        """Test creating a regular user."""
        user = User.objects.create_user(**self.user_data)

        self.assertEqual(user.email, self.user_data["email"])
        self.assertFalse(user.is_active)  # Default is False
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.is_email_verified)
        self.assertTrue(user.check_password(self.user_data["password"]))

    def test_create_superuser(self):
        """Test creating a superuser."""
        admin_user = User.objects.create_superuser(**self.admin_user_data)

        self.assertEqual(admin_user.email, self.admin_user_data["email"])
        self.assertTrue(admin_user.is_active)
        self.assertTrue(admin_user.is_staff)
        self.assertTrue(admin_user.is_superuser)
        self.assertTrue(admin_user.is_email_verified)

    def test_user_string_representation(self):
        """Test the string representation of user."""
        user = User.objects.create_user(**self.user_data)
        self.assertEqual(str(user), self.user_data["email"])

    def test_user_token_queryset_methods(self):
        """Test queryset methods on UserToken."""
        regular_user = User.objects.create_user(**self.user_data)
        admin_user = User.objects.create_superuser(**self.admin_user_data)

        UserToken.objects.create(
            user=regular_user,
            refresh_token="active_token_123",
            access_token="access_123",
            expires_at=timezone.now() + timedelta(days=1),
            is_active=True,
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0",
        )

        UserToken.objects.create(
            user=regular_user,
            refresh_token="expired_token_456",
            access_token="access_456",
            expires_at=timezone.now() - timedelta(days=1),
            is_active=True,
            ip_address="192.168.1.2",
            user_agent="Chrome/90.0",
        )

        UserToken.objects.create(
            user=regular_user,
            refresh_token="inactive_token_789",
            access_token="access_789",
            expires_at=timezone.now() + timedelta(days=1),
            is_active=False,
            ip_address="192.168.1.3",
            user_agent="Safari/14.0",
        )

        UserToken.objects.create(
            user=admin_user,
            refresh_token="admin_token_012",
            access_token="admin_access_012",
            expires_at=timezone.now() + timedelta(days=1),
            is_active=True,
            ip_address="192.168.1.4",
            user_agent="Firefox/91.0",
        )

        # Test filtering by active status
        active_tokens = UserToken.objects.filter_active(True)
        self.assertEqual(active_tokens.count(), 3)

        inactive_tokens = UserToken.objects.filter_active(False)
        self.assertEqual(inactive_tokens.count(), 1)

        # Test filtering by expiry status
        expired_tokens = UserToken.objects.get_expired_tokens()
        self.assertEqual(expired_tokens.count(), 1)

        # Test filtering by user visibility
        user_tokens = UserToken.objects.visible_to_user(regular_user)
        self.assertEqual(user_tokens.count(), 3)

        admin_tokens = UserToken.objects.visible_to_user(admin_user)
        self.assertEqual(admin_tokens.count(), 1)
        self.assertFalse(UserToken.objects.visible_to_user(None).exists())

        # Test filtering by device info
        ip_filtered = UserToken.objects.filter_by_device_info(ip_address="192.168.1.1")
        self.assertEqual(ip_filtered.count(), 1)

        ua_filtered = UserToken.objects.filter_by_device_info(user_agent="Chrome")
        self.assertEqual(ua_filtered.count(), 1)

        # Test combined filters
        combined = (
            UserToken.objects.visible_to_user(regular_user).filter_active(True).filter(expires_at__gt=timezone.now())
        )
        self.assertEqual(combined.count(), 1)

    def test_user_email_normalization(self):
        """Test that email addresses are properly normalized."""
        user = User.objects.create_user(email="TEST@EXAMPLE.COM", password="testpass123")
        self.assertEqual(user.email, "TEST@example.com")  # Domain should be lowercase

    def test_create_user_without_email_raises_error(self):
        """Test that creating a user without email raises ValueError."""
        with self.assertRaises(ValueError):
            User.objects.create_user(email="", password="testpass123")
