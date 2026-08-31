import logging

from django.db.models.signals import post_save
from django.dispatch import receiver
from guardian.shortcuts import assign_perm, remove_perm

from shared.utils.logging_utils import LoggingContext

logger = logging.getLogger(__name__)


def assign_company_permissions(company, user) -> None:
    if user is None:
        return

    assign_perm("companies.view_company", user, company)
    assign_perm("companies.change_company", user, company)
    logger.info(f"{LoggingContext.PERMISSION_ASSIGNMENT} Assigned permissions for {company.name} to {user.email}")


def remove_company_permissions(company, user) -> None:
    if user is None:
        return

    remove_perm("companies.view_company", user, company)
    remove_perm("companies.change_company", user, company)
    logger.info(f"{LoggingContext.PERMISSION_REMOVAL} Removed permissions for {company.name} from {user.email}")


@receiver(post_save, sender="companies.Company")
def on_company_created(sender, instance, created, **kwargs):
    if not created:
        return

    logger.info(f"{LoggingContext.COMPANY_REGISTRATION} Company created: {instance.name} (ACN: {instance.acn})")

    if instance.owner:
        assign_company_permissions(instance, instance.owner)


@receiver(post_save, sender="companies.Company")
def on_company_status_changed(sender, instance, created, **kwargs):
    if not created:
        update_fields = kwargs.get("update_fields")
        if update_fields and "status" in update_fields:
            logger.info(
                f"{LoggingContext.COMPANY} Company status changed: "
                f"{instance.name} -> {instance.get_status_display()}"
            )
