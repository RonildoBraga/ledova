import logging

from django.db.models.signals import post_save
from django.dispatch import receiver
from guardian.shortcuts import assign_perm

from shared.utils.logging_utils import LoggingContext
from wallets.models.wallet import Wallet

logger = logging.getLogger("ledova_backend")


@receiver(post_save, sender=Wallet)
def assign_wallet_permissions(sender, instance, created, **kwargs):
    if not created:
        return

    logger.info(f"{LoggingContext.WALLETS} Wallet {instance.uuid} saved, assigning permissions to associated users")

    for user_profile in instance.user_account.user_profiles.all():
        user = user_profile.user
        logger.info(f"{LoggingContext.WALLETS} Assigning wallet permissions to {user.email}")
        assign_perm("wallets.view_wallet", user, instance)
        assign_perm("wallets.change_wallet", user, instance)
        assign_perm("wallets.delete_wallet", user, instance)


@receiver(post_save, sender=Wallet)
def auto_assign_wallet_to_portfolio(sender, instance, created, **kwargs):
    if not created:
        return

    user_account = instance.user_account

    for user_profile in user_account.user_profiles.all():
        preferences = getattr(user_profile, "preferences", None)
        if preferences and preferences.selected_portfolio:
            selected_portfolio = preferences.selected_portfolio

            if selected_portfolio.user_account == user_account:
                selected_portfolio.wallets.add(instance)
                logger.info(
                    f"{LoggingContext.WALLETS} Auto-assigned wallet {instance.uuid} "
                    f"to portfolio {selected_portfolio.uuid} ({selected_portfolio.name})"
                )
                return

    logger.warning(f"{LoggingContext.WALLETS} No selected portfolio found for wallet {instance.uuid} auto-assignment")
