from django.conf import settings
from django.db import models

from shared.models.base import BaseModel
from users.models.owner_column import DerivesOwnerFromProfile
from users.querysets.user_preferences import UserPreferencesQuerySet


class UserPreferences(DerivesOwnerFromProfile, BaseModel):
    user_profile = models.OneToOneField("users.UserProfile", on_delete=models.CASCADE, related_name="preferences")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="+",
        db_index=True,
        help_text="Owner, derived from user_profile.user and held directly so a row-level security policy can read it",
    )

    selected_account = models.ForeignKey(
        "users.UserAccount",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="selected_by_users",
        help_text="User's selected account for quick access",
    )

    selected_portfolio = models.ForeignKey(
        "portfolios.Portfolio",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="selected_by_users",
        help_text="User's selected portfolio for quick access",
    )

    THEME_CHOICES = [("dark", "Dark"), ("light", "Light")]
    theme = models.CharField(
        max_length=10,
        choices=THEME_CHOICES,
        default="dark",
    )

    CURRENCY_CHOICES = [("AUD", "Australian Dollar"), ("USD", "US Dollar")]
    display_currency = models.CharField(
        max_length=8,
        choices=CURRENCY_CHOICES,
        default="AUD",
        help_text="Currency used for displaying prices and values",
    )

    objects = UserPreferencesQuerySet.as_manager()

    class Meta:
        verbose_name_plural = "User Preferences"

    def __str__(self):
        return f"{self.user_profile.user.email} - Preferences"
