from django.db import models

from shared.models import BaseModel


class FeatureFlag(BaseModel):

    PLATFORM_CHOICES = [
        ("all", "All Platforms"),
        ("ios", "iOS"),
        ("android", "Android"),
        ("web", "Web"),
        ("mobile", "Mobile (iOS + Android)"),
    ]

    name = models.CharField(max_length=100, unique=True, help_text="Unique flag identifier (e.g. 'enable_dark_mode')")
    description = models.TextField(blank=True, help_text="Human-readable description of what this flag controls")
    enabled = models.BooleanField(default=False, help_text="Whether this flag is currently active")
    platform = models.CharField(
        max_length=10,
        choices=PLATFORM_CHOICES,
        default="all",
        help_text="Which platform(s) this flag applies to",
    )
    min_app_version = models.CharField(
        max_length=20,
        blank=True,
        help_text="Minimum app version required (e.g. '1.2.0'). Leave blank to apply to all versions.",
    )

    class Meta:
        db_table = "feature_flags"
        verbose_name = "Feature Flag"
        verbose_name_plural = "Feature Flags"
        ordering = ["name"]

    def __str__(self):
        status = "ON" if self.enabled else "OFF"
        return f"{self.name} [{status}] ({self.get_platform_display()})"
