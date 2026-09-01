import logging

from django.db.models.signals import m2m_changed, post_save
from django.dispatch import receiver

from shared.utils.logging_utils import LoggingContext
from users.models import UserAccount, UserProfile

logger = logging.getLogger("ledova_backend")


@receiver(post_save, sender=UserProfile)
def user_profile_save(sender, instance, created, **kwargs):
    logger.info(f"{LoggingContext.USER_PROFILE} UserProfile for {instance.user.email} - created: {created}")


@receiver(m2m_changed, sender=UserAccount.user_profiles.through)
def account_user_profiles_changed(sender, instance, action, reverse, model, pk_set, **kwargs):
    if action == "post_add" and not reverse:
        logger.info(f"{LoggingContext.ACCOUNTS} User profiles added to account {instance.account_number}")
    elif action == "post_add" and reverse:
        logger.info(f"{LoggingContext.ACCOUNTS} Accounts added to user profile {instance.user.email}")
