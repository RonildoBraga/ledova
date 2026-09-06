from django.db import models


class WhitelistStatus(models.TextChoices):

    PENDING = "pending", "Pending"
    ACTIVE = "active", "Active"
    REMOVED = "removed", "Removed"
    FAILED = "failed", "Failed"


class HolderType(models.TextChoices):

    MEMBER = "member", "Member"
    TREASURY = "treasury", "Treasury"
    AMBIGUOUS = "ambiguous", "Ambiguous"
    UNIDENTIFIED = "unidentified", "Unidentified"
