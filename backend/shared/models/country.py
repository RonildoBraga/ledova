"""
Models for country-related entities.
"""

from django.db import models

from shared.models.base import BaseModel
from shared.querysets.country import CountryQuerySet


class Country(BaseModel):
    """Model representing a country"""

    name = models.CharField(max_length=100, null=True, blank=True)
    code = models.CharField(max_length=3, null=True, blank=True)
    dial_code = models.CharField(max_length=10, null=True, blank=True)
    is_available = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "Countries"

    def __str__(self):
        return self.name if self.name else self.code if self.code else "Unknown Country"

    # Use the custom manager
    objects = CountryQuerySet.as_manager()
