from shared.db import CarriedByThePolicy


class FavouriteAssetQuerySet(CarriedByThePolicy):

    def with_optimized_data(self):
        return self.select_related("user_account", "asset")
