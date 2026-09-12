from django.db.models import QuerySet


class FinancialProfileQuerySet(QuerySet):

    def owned_through_the_live_profile(self, user):
        if user is None or not user.is_authenticated:
            return self.none()
        return self.filter(user_profile__user=user)
