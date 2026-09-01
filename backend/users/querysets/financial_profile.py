from django.db.models import QuerySet


class FinancialProfileQuerySet(QuerySet):

    def visible_to_user(self, user):
        if user is None or not user.is_authenticated:
            return self.none()
        if user.is_staff or user.is_superuser:
            return self
        return self.filter(user_profile__user=user)
