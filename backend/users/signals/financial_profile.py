import logging

from django.db.models.signals import post_save
from django.dispatch import receiver
from guardian.shortcuts import assign_perm

from shared.utils.logging_utils import LoggingContext
from users.models.financial_profile import FinancialProfile

logger = logging.getLogger("ledova_backend")


@receiver(post_save, sender=FinancialProfile)
def financial_profile_save(sender, instance, **kwargs):
    """Assign view and change permissions to user profile user for financial profile."""
    logger.info(
        f"{LoggingContext.PERMISSION_ASSIGNMENT} Assigning financial_profile permissions "
        f"to {instance.user_profile.user.email}"
    )
    assign_perm("view_financialprofile", instance.user_profile.user, instance)
    assign_perm("change_financialprofile", instance.user_profile.user, instance)
    assign_perm("delete_financialprofile", instance.user_profile.user, instance)
