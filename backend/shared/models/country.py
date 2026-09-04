import pycountry
from django.db import models

from shared.models.base import BaseModel


class Country(BaseModel):
    name = models.CharField(max_length=100, null=True, blank=True)
    code = models.CharField(max_length=3, null=True, blank=True)
    dial_code = models.CharField(max_length=10, null=True, blank=True)
    is_available = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "Countries"

    def __str__(self):
        return self.name if self.name else self.code if self.code else "Unknown Country"

    @classmethod
    def get_or_create_for_code(cls, code):
        """Row for an ISO 3166-1 alpha-2/alpha-3 code; the name is resolved once, at creation."""
        code = code.strip().upper()
        match = pycountry.countries.get(alpha_2=code) if len(code) == 2 else pycountry.countries.get(alpha_3=code)
        name = (getattr(match, "common_name", None) or match.name) if match else code
        country, _ = cls.objects.get_or_create(code=code, defaults={"name": name})
        return country
