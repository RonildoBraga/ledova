from django.conf import settings
from django.db import models
from django.utils import timezone

from companies.querysets.review import ApplicationReviewQuerySet, ReviewNoteQuerySet
from shared.models import BaseModel


class ReviewDecision(models.TextChoices):
    PENDING = "pending", "Pending Review"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    RECUSED = "recused", "Recused"


class ApplicationReview(BaseModel):

    objects = ApplicationReviewQuerySet.as_manager()

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="reviews",
    )

    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="company_reviews",
    )

    assigned_at = models.DateTimeField(auto_now_add=True)
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_reviews",
    )

    decision = models.CharField(
        max_length=20,
        choices=ReviewDecision.choices,
        default=ReviewDecision.PENDING,
    )
    decision_at = models.DateTimeField(null=True, blank=True)

    notes = models.TextField(blank=True, help_text="Internal review notes")
    decision_reason = models.TextField(blank=True, help_text="Reason for approval/rejection")

    review_order = models.PositiveSmallIntegerField(default=1)

    class Meta:
        verbose_name = "Application Review"
        verbose_name_plural = "Application Reviews"
        ordering = ["company", "review_order"]
        unique_together = [["company", "reviewer"], ["company", "review_order"]]

    def __str__(self):
        return f"{self.company.name} - Reviewer {self.review_order}: {self.reviewer}"

    def approve(self, reason: str = ""):
        self.decision = ReviewDecision.APPROVED
        self.decision_at = timezone.now()
        self.decision_reason = reason
        self.save(update_fields=["decision", "decision_at", "decision_reason", "updated_at"])

    def reject(self, reason: str):
        if not reason:
            raise ValueError("Rejection reason is required")
        self.decision = ReviewDecision.REJECTED
        self.decision_at = timezone.now()
        self.decision_reason = reason
        self.save(update_fields=["decision", "decision_at", "decision_reason", "updated_at"])

    def recuse(self, reason: str = ""):
        self.decision = ReviewDecision.RECUSED
        self.decision_at = timezone.now()
        self.decision_reason = reason
        self.save(update_fields=["decision", "decision_at", "decision_reason", "updated_at"])

    @property
    def is_pending(self):
        return self.decision == ReviewDecision.PENDING

    @property
    def is_complete(self):
        return self.decision in [ReviewDecision.APPROVED, ReviewDecision.REJECTED]


class ReviewNote(BaseModel):

    objects = ReviewNoteQuerySet.as_manager()

    review = models.ForeignKey(
        ApplicationReview,
        on_delete=models.CASCADE,
        related_name="review_notes",
    )

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="review_notes_authored",
    )

    content = models.TextField()

    visible_to_company = models.BooleanField(
        default=False,
        help_text="If True, this note will be visible to the company representatives",
    )

    class Meta:
        verbose_name = "Review Note"
        verbose_name_plural = "Review Notes"
        ordering = ["created_at"]

    def __str__(self):
        visibility = "External" if self.visible_to_company else "Internal"
        return f"[{visibility}] {self.author} on {self.review.company.name}"
