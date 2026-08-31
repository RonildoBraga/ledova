import logging

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver
from guardian.shortcuts import assign_perm

from shared.utils.logging_utils import LoggingContext

User = get_user_model()

logger = logging.getLogger("ledova_backend")


@receiver(post_save, sender=User)
def user_save(sender, instance, created, **kwargs):
    if created and not instance.is_superuser:
        logger.info(
            f"{LoggingContext.PERMISSION_ASSIGNMENT} Starting permission assignment for new user {instance.email}"
        )
        try:
            # User profile permissions
            assign_perm("users.add_userprofile", instance)
            assign_perm("users.change_userprofile", instance)

            # Financial profile permissions
            assign_perm("users.add_financialprofile", instance)
            assign_perm("users.change_financialprofile", instance)

            # User account permissions
            assign_perm("users.add_useraccount", instance)
            assign_perm("users.change_useraccount", instance)

            # Portfolio permissions
            assign_perm("portfolios.add_portfolio", instance)
            assign_perm("portfolios.change_portfolio", instance)

            # Asset allocation permissions
            assign_perm("portfolios.add_assetallocation", instance)
            assign_perm("portfolios.change_assetallocation", instance)
            assign_perm("portfolios.delete_assetallocation", instance)

            # Asset holding permissions (for viewing current portfolio holdings)
            assign_perm("portfolios.view_assetholding", instance)
            assign_perm("portfolios.view_assetholdingsnapshot", instance)

            # Asset permissions
            assign_perm("assets.view_asset", instance)

            # Country permissions
            assign_perm("shared.view_country", instance)
        except Exception as e:
            logger.warning(
                f"{LoggingContext.PERMISSION_ASSIGNMENT} Could not assign permissions to user {instance.email}: {e}"
            )
            # This can happen during migrations or test database setup
            # when permissions are not yet available
