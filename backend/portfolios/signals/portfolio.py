import logging

from django.db.models.signals import post_save
from django.dispatch import receiver
from guardian.shortcuts import assign_perm

from portfolios.models.portfolio import Portfolio
from shared.utils.logging_utils import LoggingContext

logger = logging.getLogger("ledova_backend")


@receiver(post_save, sender=Portfolio)
def assign_portfolio_permissions(sender, instance, created, **kwargs):
    """
    Assign view and change permissions to all users associated with the portfolio's account.
    """
    if not created:
        return

    logger.info(
        f"{LoggingContext.PORTFOLIOS} Portfolio {instance.uuid} saved, assigning permissions to associated users"
    )

    # Assign permissions to all user profiles associated with this account
    for user_profile in instance.user_account.user_profiles.all():
        user = user_profile.user
        logger.info(f"{LoggingContext.PORTFOLIOS} Assigning portfolio permissions to {user.email}")
        assign_perm("portfolios.view_portfolio", user, instance)
        assign_perm("portfolios.change_portfolio", user, instance)
        assign_perm("portfolios.delete_portfolio", user, instance)
