"""
Tests for CustomUser model and related functionality.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

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

    def test_user_email_normalization(self):
        """Test that email addresses are properly normalized."""
        user = User.objects.create_user(email="TEST@EXAMPLE.COM", password="testpass123")
        self.assertEqual(user.email, "test@example.com")

    def test_create_user_without_email_raises_error(self):
        """Test that creating a user without email raises ValueError."""
        with self.assertRaises(ValueError):
            User.objects.create_user(email="", password="testpass123")
