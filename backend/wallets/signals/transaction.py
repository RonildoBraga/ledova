import logging

from django.db.models.signals import post_save
from django.dispatch import receiver
from guardian.shortcuts import assign_perm

from shared.utils.logging_utils import LoggingContext
from wallets.models.transaction import Transaction

logger = logging.getLogger("ledova_backend")


@receiver(post_save, sender=Transaction)
def assign_transaction_permissions(sender, instance, created, **kwargs):
    """
    Assign view permissions to all users associated with the wallet's account.
    Transactions are read-only, so only view permission is assigned.
    """
    if not created or not instance.wallet:
        return

    logger.info(
        f"{LoggingContext.WALLETS} Transaction {instance.uuid} created, " f"assigning permissions to associated users"
    )

    # Assign permissions to all user profiles associated with the wallet's account
    for user_profile in instance.wallet.user_account.user_profiles.all():
        user = user_profile.user
        logger.info(f"{LoggingContext.WALLETS} Assigning transaction view permission to {user.email}")
        assign_perm("wallets.view_transaction", user, instance)
