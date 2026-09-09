from django.conf import settings
from django.db import models
from django.utils import timezone

from shared.models import BaseModel


class RegistryCheckStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PASSED = "passed", "Passed"
    FAILED = "failed", "Failed"


class RegistryCheckPurpose(models.TextChoices):
    REVIEW = "review", "Start review"
    RETRY = "retry", "Retry"
    ACTIVATION = "activation", "Activation"


class CompanyRegistryCheck(BaseModel):
    company = models.ForeignKey("companies.Company", on_delete=models.CASCADE, related_name="registry_checks")
    initiated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    purpose = models.CharField(max_length=16, choices=RegistryCheckPurpose.choices)
    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True)
    requested_name = models.CharField(max_length=255)
    requested_acn = models.CharField(max_length=11)
    requested_abn = models.CharField(max_length=14, blank=True)
    identity = models.JSONField()
    lifecycle_revision = models.PositiveBigIntegerField()
    status = models.CharField(max_length=16, choices=RegistryCheckStatus.choices, default=RegistryCheckStatus.PENDING)
    reason = models.CharField(max_length=40, blank=True)
    registry_abn = models.CharField(max_length=14, blank=True)
    registry_acn = models.CharField(max_length=11, blank=True)
    entity_name = models.CharField(max_length=255, blank=True)
    entity_type = models.CharField(max_length=16, blank=True)
    entity_status = models.CharField(max_length=32, blank=True)
    effective_from = models.DateField(null=True)
    retrieved_at = models.CharField(max_length=40, blank=True)
    register_updated_at = models.DateField(null=True)

    class Meta:
        ordering = ["-started_at", "-uuid"]
