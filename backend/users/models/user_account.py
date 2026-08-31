from django.db import models

from shared.models import BaseModel
from users.constants import (
    ACCOUNT_STATUS_CHOICES,
    ACCOUNT_STATUS_PENDING,
    USER_ACCOUNT_TYPE_CHOICES,
    USER_ACCOUNT_TYPE_INDIVIDUAL,
)
from users.models.user_profile import UserProfile
from users.querysets.user_account import UserAccountQuerySet


class AccountRole(models.TextChoices):
    INVESTOR = "investor", "Investor"
    COMPANY = "company", "Company"
    BOTH = "both", "Both"


class UserAccount(BaseModel):
    user_profiles = models.ManyToManyField(UserProfile, related_name="user_accounts")
    director = models.ForeignKey(
        UserProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name="directed_user_accounts"
    )
    account_number = models.CharField(max_length=20, default=USER_ACCOUNT_TYPE_INDIVIDUAL)
    account_type = models.CharField(
        max_length=20, choices=USER_ACCOUNT_TYPE_CHOICES, default=USER_ACCOUNT_TYPE_INDIVIDUAL
    )
    account_status = models.CharField(max_length=20, choices=ACCOUNT_STATUS_CHOICES, default=ACCOUNT_STATUS_PENDING)
    role = models.CharField(max_length=10, choices=AccountRole.choices, default=AccountRole.INVESTOR)
    activation_date = models.DateTimeField(blank=True, null=True)
    rejection_reason = models.CharField(max_length=100, blank=True)

    objects = UserAccountQuerySet.as_manager()

    class Meta:
        db_table = "customer_accounts_account"
        verbose_name = "User Account"
        verbose_name_plural = "User Accounts"

    def __str__(self):
        return f"User Account {self.account_number}"
