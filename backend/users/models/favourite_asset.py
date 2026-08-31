"""
FavouriteAsset model for tracking user's favourite assets.
"""

from django.db import models

from assets.models import Asset
from shared.models import BaseModel
from users.models.user_account import UserAccount
from users.querysets.favourite_asset import FavouriteAssetQuerySet


class FavouriteAsset(BaseModel):
    """
    Represents a user's favourite asset.

    Each user account can mark assets as favourites to easily track them.
    The relationship is unique per user_account + asset combination.
    """

    user_account = models.ForeignKey(
        UserAccount,
        on_delete=models.CASCADE,
        related_name="favourite_assets",
        help_text="The user account that owns this favourite",
    )
    asset = models.ForeignKey(
        Asset,
        on_delete=models.CASCADE,
        related_name="favourite_assets",
        help_text="The asset that is marked as favourite",
    )

    objects = FavouriteAssetQuerySet.as_manager()

    class Meta:
        db_table = "favourite_assets"
        verbose_name = "Favourite Asset"
        verbose_name_plural = "Favourite Assets"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user_account", "asset"],
                name="unique_favourite_asset_per_user_account",
            ),
        ]

    def __str__(self):
        return f"{self.asset.symbol} - {self.user_account.account_number}"
