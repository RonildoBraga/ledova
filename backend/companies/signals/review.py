import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from shared.utils.logging_utils import LoggingContext

logger = logging.getLogger(__name__)


@receiver(post_save, sender="companies.ApplicationReview")
def on_review_created(sender, instance, created, **kwargs):
    if created:
        logger.info(
            f"{LoggingContext.COMPANY_REVIEW} Review assigned: "
            f"{instance.reviewer.email} assigned to {instance.company.name} (Order: {instance.review_order})"
        )


@receiver(post_save, sender="companies.ApplicationReview")
def on_review_decision_made(sender, instance, created, **kwargs):
    if not created:
        update_fields = kwargs.get("update_fields")
        if update_fields and "decision" in update_fields:
            from companies.models import ReviewDecision

            if instance.decision != ReviewDecision.PENDING:
                logger.info(
                    f"{LoggingContext.COMPANY_REVIEW} Review decision: "
                    f"{instance.reviewer.email} {instance.decision} {instance.company.name}"
                )
