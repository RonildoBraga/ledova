from django.db.models import QuerySet
from guardian.shortcuts import get_objects_for_user


class UserPreferencesQuerySet(QuerySet):

    def with_selected_account(self):
        return self.filter(selected_account__isnull=False)

    def with_selected_portfolio(self):
        return self.filter(selected_portfolio__isnull=False)

    def visible_to_user(self, user):
        if user.is_superuser or user.is_staff:
            return self
        return get_objects_for_user(user, "users.view_userpreferences", klass=self)

    def with_optimized_data(self):
        return self.select_related(
            "user_profile__user", "selected_account", "selected_portfolio__user_account"
        ).prefetch_related("user_profile__user_accounts", "user_profile__user_accounts__portfolios")
