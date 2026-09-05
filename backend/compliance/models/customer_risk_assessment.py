from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from compliance.constants import (
    ASSESSMENT_STATUS_CHOICES,
    ASSESSMENT_STATUS_PENDING,
    PEP_TYPE_CHOICES,
    PEP_TYPE_NONE,
    RISK_RATING_CHOICES,
)
from shared.models.base import BaseModel


class CustomerRiskAssessment(BaseModel):
    user_account = models.ForeignKey(
        "users.UserAccount",
        on_delete=models.CASCADE,
        related_name="risk_assessments",
    )
    assessment_status = models.CharField(
        max_length=20,
        choices=ASSESSMENT_STATUS_CHOICES,
        default=ASSESSMENT_STATUS_PENDING,
    )
    overall_risk_rating = models.CharField(
        max_length=20,
        choices=RISK_RATING_CHOICES,
        null=True,
        blank=True,
    )
    customer_risk_score = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    geographic_risk_score = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    product_risk_score = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    pep_type = models.CharField(
        max_length=20,
        choices=PEP_TYPE_CHOICES,
        default=PEP_TYPE_NONE,
    )
    pep_details = models.JSONField(null=True, blank=True)
    high_risk_occupation = models.BooleanField(default=False)
    assessment_reason = models.TextField(blank=True)
    assessed_by = models.ForeignKey(
        "authentication.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="risk_assessments_made",
    )
    is_automated = models.BooleanField(default=True)
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_until = models.DateTimeField(null=True, blank=True)
    next_review_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user_account", "-created_at"]),
            models.Index(fields=["assessment_status"]),
            models.Index(fields=["overall_risk_rating"]),
        ]

    def __str__(self):
        rating = self.overall_risk_rating or "pending"
        return f"Risk Assessment for {self.user_account} - {rating.upper()}"

    @property
    def is_pep(self):
        return self.pep_type != PEP_TYPE_NONE

    @property
    def total_risk_score(self):
        if self.customer_risk_score is None or self.geographic_risk_score is None:
            return None
        return self.customer_risk_score + self.geographic_risk_score + self.product_risk_score
