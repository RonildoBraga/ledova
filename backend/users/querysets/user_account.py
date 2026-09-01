from django.db.models import QuerySet


class UserAccountQuerySet(QuerySet):

    def visible_to_user(self, user):
        if user.is_superuser or user.is_staff:
            return self
        if not user.is_authenticated:
            return self.none()
        return self.filter(user_profiles__user=user)
