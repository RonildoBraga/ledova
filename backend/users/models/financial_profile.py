"""
Models for financial profile.

AML/CTF Compliance:
This model collects source of funds, occupation, and intended use as required
by LEDOVA AML/CTF Program (Part B, Section 16.1, Step 4).
The fields are generic examples and do not represent a supplied compliance program.
"""

from django.db import models

from shared.models.base import BaseModel
from users.constants import INTENDED_USE_CHOICES, SOURCE_OF_FUNDS_CHOICES
from users.querysets.financial_profile import FinancialProfileQuerySet


class FinancialProfile(BaseModel):
    """
    Model for storing user financial profile.

    AML/CTF Compliance: Collects source of funds, occupation, and intended use
    as required by LEDOVA AML/CTF Program (Part B, Section 16.1, Step 4).
    """

    user_profile = models.OneToOneField("users.UserProfile", on_delete=models.CASCADE, related_name="financial_profile")

    # AML/CTF: Occupation (LEDOVA Section 16.1, Step 4)
    occupation = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        help_text="Customer's occupation for AML/CTF risk profiling",
    )

    # AML/CTF: Source of Funds (LEDOVA Section 16.1, Step 4)
    source_of_funds = models.JSONField(
        default=list,
        blank=True,
        null=True,
        help_text="Primary source of funds: " + ", ".join([c[0] for c in SOURCE_OF_FUNDS_CHOICES]),
    )

    # AML/CTF: Specification for "Other" source of funds
    source_of_funds_other_text = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        help_text="Specification when 'other' is selected as source of funds",
    )

    # AML/CTF: Intended Use (LEDOVA Section 16.1, Step 4)
    intended_use = models.CharField(
        max_length=50,
        choices=INTENDED_USE_CHOICES,
        blank=True,
        null=True,
        help_text="Customer's intended use of the platform",
    )

    # AML/CTF: Specification for "Other" intended use
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
