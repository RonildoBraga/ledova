"""
Custom User model.
"""

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone

from authentication.managers.user import CustomUserManager
from authentication.security.v2_email import (
    V2EmailDestinationKey,
    V2EmailIsPrintableASCII,
)


class CustomUser(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    is_active = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)
    last_login = models.DateTimeField(blank=True, null=True)

    # Email verification
    email_verification_token = models.CharField(max_length=100, blank=True, null=True)
    email_verification_sent_at = models.DateTimeField(blank=True, null=True)
    is_email_verified = models.BooleanField(default=False)

    # SMS verification
    sms_verification_token = models.CharField(max_length=10, blank=True, null=True)
    sms_verification_sent_at = models.DateTimeField(blank=True, null=True)
    is_phone_verified = models.BooleanField(default=False)

    # Password reset
    password_reset_token = models.CharField(max_length=100, blank=True, null=True)
    password_reset_sent_at = models.DateTimeField(blank=True, null=True)

    objects = CustomUserManager()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=V2EmailIsPrintableASCII(models.F("email")),
                name="auth_user_email_v2_ascii_ck",
            ),
            models.CheckConstraint(
                condition=models.Q(email=V2EmailDestinationKey(models.F("email"))),
                name="auth_user_email_v2_canon_ck",
            ),
            models.UniqueConstraint(
                V2EmailDestinationKey(models.F("email")),
                name="auth_user_email_v2_key_uniq",
            ),
        ]

    USERNAME_FIELD = "email"

    def __str__(self):
        return self.email
