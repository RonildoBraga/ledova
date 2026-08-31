import logging

from django.db.models.signals import m2m_changed
from django.dispatch import receiver
from guardian.shortcuts import assign_perm

from portfolios.models.portfolio import (
    AssetAllocation,
    Portfolio,
)

# Holdings are now wallet-based (see wallets.models.Holding)
from shared.utils.logging_utils import LoggingContext
from users.models import UserAccount, UserProfile

logger = logging.getLogger("ledova_backend")


@receiver(m2m_changed, sender=UserAccount.user_profiles.through)
def account_portfolios_user_profiles_changed(sender, instance, action, reverse, model, pk_set, **kwargs):
    """
    When user profiles are added to an account, assign them permissions to all existing portfolios,
    asset allocations, holdings, and snapshots associated with that account.
    """
    # Only process when user profiles are added to an account
    if action == "post_add" and not reverse:
        logger.info(
            f"{LoggingContext.PORTFOLIOS} User profiles added to account "
            f"{instance.account_number}, updating portfolio permissions"
        )
        user_profiles = UserProfile.objects.filter(pk__in=pk_set)

        # Get all portfolios associated with this account
        portfolios = Portfolio.objects.filter(user_account=instance)

        for user_profile in user_profiles:
            user = user_profile.user

            # Assign permissions to all existing portfolios
            for portfolio in portfolios:
                logger.info(f"{LoggingContext.PERMISSION_ASSIGNMENT} Assigning portfolio permissions to {user.email}")
                assign_perm("portfolios.view_portfolio", user, portfolio)
                assign_perm("portfolios.change_portfolio", user, portfolio)
                assign_perm("portfolios.delete_portfolio", user, portfolio)

                # Assign permissions to all asset allocations in this portfolio
                for asset_allocation in AssetAllocation.objects.filter(portfolio=portfolio):
                    assign_perm("portfolios.view_assetallocation", user, asset_allocation)
                    assign_perm("portfolios.change_assetallocation", user, asset_allocation)
                    assign_perm("portfolios.delete_assetallocation", user, asset_allocation)
