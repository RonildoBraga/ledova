from django.core.exceptions import ValidationError
from django.db import models

from shared.models.base import BaseModel
from users.querysets.user_preferences import UserPreferencesQuerySet


class UserPreferences(BaseModel):
    user_profile = models.OneToOneField("users.UserProfile", on_delete=models.CASCADE, related_name="preferences")

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

    def clean(self):
        super().clean()

        if self.selected_portfolio and self.selected_account:
            if self.selected_portfolio.user_account != self.selected_account:
                raise ValidationError(
                    {"selected_portfolio": "The selected portfolio must belong to the selected account."}
                )

        if self.selected_portfolio and not self.selected_account:
            raise ValidationError(
                {"selected_account": "A selected account must be set when a selected portfolio is chosen."}
            )

        if self.selected_account:
            user_accounts = self.user_profile.user_accounts.all()
            if self.selected_account not in user_accounts:
                raise ValidationError({"selected_account": "The selected account must be one of the user's accounts."})

        if self.selected_portfolio:
            user_portfolios = []
            for account in self.user_profile.user_accounts.all():
                user_portfolios.extend(account.portfolios.all())

            if self.selected_portfolio not in user_portfolios:
                raise ValidationError(
                    {"selected_portfolio": "The selected portfolio must be one of the user's portfolios."}
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user_profile.user.email} - Preferences"
