from django.db.models import QuerySet


class UserPreferencesQuerySet(QuerySet):

    def visible_to_user(self, user):
        if user is None or not user.is_authenticated:
            return self.none()
        return self.filter(user_profile__user=user)

    def with_optimized_data(self):
        return self.select_related(
            "user_profile__user", "selected_account", "selected_portfolio__user_account"
        ).prefetch_related("user_profile__user_accounts", "user_profile__user_accounts__portfolios")
