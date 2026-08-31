import logging

from django.db.models.signals import post_save
from django.dispatch import receiver
from guardian.shortcuts import assign_perm

from shared.utils.logging_utils import LoggingContext
from users.models.user_preferences import UserPreferences

logger = logging.getLogger("ledova_backend")


@receiver(post_save, sender=UserPreferences)
def user_preferences_save(sender, instance, **kwargs):
    """Assign view, change, and delete permissions to user profile user for user preferences."""
    logger.info(
        f"{LoggingContext.PERMISSION_ASSIGNMENT} Assigning user_preferences permissions "
        f"to {instance.user_profile.user.email}"
    )
    assign_perm("view_userpreferences", instance.user_profile.user, instance)
    assign_perm("change_userpreferences", instance.user_profile.user, instance)
    assign_perm("delete_userpreferences", instance.user_profile.user, instance)
