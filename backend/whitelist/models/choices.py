from django.db import models


class WhitelistStatus(models.TextChoices):

    PENDING = "pending", "Pending"
    ACTIVE = "active", "Active"
    REMOVED = "removed", "Removed"
    FAILED = "failed", "Failed"
