"""
Custom User model.
"""

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone

from authentication.email import (
    EmailDestinationKey,
    EmailIsPrintableASCII,
)
from authentication.managers.user import CustomUserManager


class CustomUser(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    is_active = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)
    last_login = models.DateTimeField(blank=True, null=True)

    # Email verification: the column holds sha256(pk:code), never the code itself
    # (see authentication.services.email_codes).
    email_verification_token = models.CharField(max_length=100, blank=True, null=True)
    email_verification_sent_at = models.DateTimeField(blank=True, null=True)
    email_verification_attempts = models.PositiveSmallIntegerField(default=0)
    is_email_verified = models.BooleanField(default=False)

    objects = CustomUserManager()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=EmailIsPrintableASCII(models.F("email")),
                name="auth_user_email_v2_ascii_ck",
            ),
            models.CheckConstraint(
                condition=models.Q(email=EmailDestinationKey(models.F("email"))),
                name="auth_user_email_v2_canon_ck",
            ),
            models.UniqueConstraint(
                EmailDestinationKey(models.F("email")),
                name="auth_user_email_v2_key_uniq",
            ),
        ]

    USERNAME_FIELD = "email"

    def __str__(self):
        return self.email
