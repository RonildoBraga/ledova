from django.db.models import QuerySet
from guardian.shortcuts import get_objects_for_user


class PortfolioQuerySet(QuerySet):

    def visible_to_user(self, user):
        if user.is_superuser or user.is_staff:
            return self
        return get_objects_for_user(user, "portfolios.view_portfolio", klass=self)

    def active(self):
        return self.filter(is_active=True)

    def with_optimized_data(self):
        return self.select_related("user_account", "user_account__user_profile")
