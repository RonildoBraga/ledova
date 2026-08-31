import logging

from django.db.models.signals import post_save
from django.dispatch import receiver
from guardian.shortcuts import assign_perm

from portfolios.models.portfolio import PortfolioSnapshot
from shared.utils.logging_utils import LoggingContext

logger = logging.getLogger("ledova_backend")


@receiver(post_save, sender=PortfolioSnapshot)
def assign_portfolio_snapshot_permissions(sender, instance, created, **kwargs):
    """
    Assign view permissions for portfolio snapshots to all users associated with the portfolio's account.
    Portfolio snapshots are immutable historical records, so only view permissions are assigned.
    """
    if not created:
        return

    logger.debug(f"{LoggingContext.PORTFOLIOS} PortfolioSnapshot {instance.uuid} saved, assigning permissions")

    # Assign permissions to all user profiles associated with this account
    for user_profile in instance.portfolio.user_account.user_profiles.all():
        user = user_profile.user
        logger.debug(f"{LoggingContext.PORTFOLIOS} Assigning portfolio snapshot permissions to {user.email}")
        assign_perm("portfolios.view_portfoliosnapshot", user, instance)
        # Only view permissions for snapshots - they should be immutable historical records
