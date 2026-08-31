"""
Signals for FavouriteAsset model.
"""

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver
from guardian.shortcuts import assign_perm

from shared.utils.logging_utils import LoggingContext
from users.models.favourite_asset import FavouriteAsset

logger = logging.getLogger("ledova_backend")


@receiver(post_save, sender=FavouriteAsset)
def assign_favourite_asset_permissions(sender, instance, created, **kwargs):  # noqa: ARG001
    """
    Assign view, change, and delete permissions to all users associated with the favourite's account.
    """
    if not created:
        return

    logger.info(
        f"{LoggingContext.ACCOUNTS} FavouriteAsset {instance.uuid} saved, " f"assigning permissions to associated users"
    )

    # Assign permissions to all user profiles associated with this account
    for user_profile in instance.user_account.user_profiles.all():
        user = user_profile.user
        logger.info(f"{LoggingContext.PERMISSION_ASSIGNMENT} Assigning favourite asset permissions to {user.email}")
        assign_perm("users.view_favouriteasset", user, instance)
        assign_perm("users.change_favouriteasset", user, instance)
        assign_perm("users.delete_favouriteasset", user, instance)
