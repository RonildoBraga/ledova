import logging

from django.db.models.signals import post_save
from django.dispatch import receiver
from guardian.shortcuts import assign_perm

from portfolios.models.portfolio import AssetAllocation
from shared.utils.logging_utils import LoggingContext

logger = logging.getLogger("ledova_backend")


@receiver(post_save, sender=AssetAllocation)
def assign_asset_allocation_permissions(sender, instance, created, **kwargs):
    """
    Assign view and change permissions for asset allocations to all users associated with the portfolio's account.
    """
    logger.debug(
        f"{LoggingContext.PORTFOLIOS} AssetAllocation {instance.uuid} saved (created={created}), assigning permissions"
    )

    # Assign permissions to all user profiles associated with this account
    for user_profile in instance.portfolio.user_account.user_profiles.all():
        user = user_profile.user
        logger.debug(f"{LoggingContext.PORTFOLIOS} Assigning asset allocation permissions to {user.email}")
        assign_perm("portfolios.view_assetallocation", user, instance)
        assign_perm("portfolios.change_assetallocation", user, instance)
        assign_perm("portfolios.delete_assetallocation", user, instance)
