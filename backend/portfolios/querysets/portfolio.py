from django.db.models import QuerySet


class PortfolioQuerySet(QuerySet):

    def visible_to_user(self, user):
        if user is None or not user.is_authenticated:
            return self.none()
        return self.filter(user_account__user_profiles__user=user)

    def active(self):
        return self.filter(is_active=True)
