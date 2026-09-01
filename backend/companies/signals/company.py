import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from shared.utils.logging_utils import LoggingContext

logger = logging.getLogger(__name__)


@receiver(post_save, sender="companies.Company")
def on_company_created(sender, instance, created, **kwargs):
    if not created:
        return

    logger.info(f"{LoggingContext.COMPANY_REGISTRATION} Company created: {instance.name} (ACN: {instance.acn})")


@receiver(post_save, sender="companies.Company")
def on_company_status_changed(sender, instance, created, **kwargs):
    if not created:
        update_fields = kwargs.get("update_fields")
        if update_fields and "status" in update_fields:
            logger.info(
                f"{LoggingContext.COMPANY} Company status changed: "
                f"{instance.name} -> {instance.get_status_display()}"
            )
