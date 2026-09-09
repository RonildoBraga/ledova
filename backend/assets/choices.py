from django.db import models


class PriceSource(models.TextChoices):
    MARKET = "market", "Market price"
    NAV = "nav", "NAV"
    PAR = "par", "Par"


VALUE_SOURCE_CHOICES = [*PriceSource.choices, ("unpriced", "Unpriced")]
