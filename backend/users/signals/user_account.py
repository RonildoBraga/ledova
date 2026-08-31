import logging

from django.contrib.auth import get_user_model
from django.db.models.signals import m2m_changed, post_save
from django.dispatch import receiver
from guardian.shortcuts import assign_perm

from shared.utils.logging_utils import LoggingContext
from users.models import UserAccount, UserProfile

User = get_user_model()

logger = logging.getLogger("ledova_backend")


@receiver(post_save, sender=UserProfile)
def user_profile_save(sender, instance, created, **kwargs):
    logger.info(f"{LoggingContext.USER_PROFILE} UserProfile for {instance.user.email} - created: {created}")
    if created:
        logger.info(
            f"{LoggingContext.PERMISSION_ASSIGNMENT} Assigning user profile permissions to {instance.user.email}"
        )
        assign_perm("view_userprofile", instance.user, instance)
        assign_perm("change_userprofile", instance.user, instance)


@receiver(m2m_changed, sender=UserAccount.user_profiles.through)
def account_user_profiles_changed(sender, instance, action, reverse, model, pk_set, **kwargs):
    # Only process when user profiles are added to an account
    if action == "post_add" and not reverse:
        logger.info(f"{LoggingContext.ACCOUNTS} User profiles added to account {instance.account_number}")
        user_profiles = UserProfile.objects.filter(pk__in=pk_set)
        for user_profile in user_profiles:
            logger.info(
                f"{LoggingContext.PERMISSION_ASSIGNMENT} Assigning account permissions "
                f"to {user_profile.user.email} for account {instance.account_number}"
            )
            assign_perm("view_useraccount", user_profile.user, instance)
            assign_perm("change_useraccount", user_profile.user, instance)

    # Handle the reverse relation (optional) - when accounts are added to a user profile
    elif action == "post_add" and reverse:
        logger.info(f"{LoggingContext.ACCOUNTS} Accounts added to user profile {instance.user.email}")
        accounts = UserAccount.objects.filter(pk__in=pk_set)
        for account in accounts:
            logger.info(
                f"{LoggingContext.PERMISSION_ASSIGNMENT} Assigning account permissions to {instance.user.email}"
            )
            assign_perm("view_useraccount", instance.user, account)
            assign_perm("change_useraccount", instance.user, account)
