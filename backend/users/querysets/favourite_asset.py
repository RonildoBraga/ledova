from django.db.models import QuerySet
from guardian.shortcuts import get_objects_for_user


class FavouriteAssetQuerySet(QuerySet):

    def visible_to_user(self, user):
        if user.is_superuser or user.is_staff:
            return self
        return get_objects_for_user(user, "users.view_favouriteasset", klass=self)

    def with_optimized_data(self):
        return self.select_related("user_account", "asset")
