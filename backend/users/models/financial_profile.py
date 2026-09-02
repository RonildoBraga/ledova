from django.db import models

from shared.models.base import BaseModel
from users.constants import INTENDED_USE_CHOICES, SOURCE_OF_FUNDS_CHOICES
from users.querysets.financial_profile import FinancialProfileQuerySet


class FinancialProfile(BaseModel):
    """Occupation, source of funds and intended use collected for AML/CTF customer due diligence."""

    user_profile = models.OneToOneField("users.UserProfile", on_delete=models.CASCADE, related_name="financial_profile")

    occupation = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        help_text="Customer's occupation for AML/CTF risk profiling",
    )

    source_of_funds = models.JSONField(
        default=list,
        blank=True,
        null=True,
        help_text="Primary source of funds: " + ", ".join([c[0] for c in SOURCE_OF_FUNDS_CHOICES]),
    )

    source_of_funds_other_text = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        help_text="Specification when 'other' is selected as source of funds",
    )

    intended_use = models.CharField(
        max_length=50,
        choices=INTENDED_USE_CHOICES,
        blank=True,
        null=True,
        help_text="Customer's intended use of the platform",
    )

    intended_use_other_text = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        help_text="Specification when 'other' is selected as intended use",
    )

    objects = FinancialProfileQuerySet.as_manager()

    class Meta:
        verbose_name_plural = "Financial Profiles"

    def __str__(self):
        return f"{self.user_profile.user.email} - Financial Profile"
