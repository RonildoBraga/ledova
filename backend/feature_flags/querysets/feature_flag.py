from django.db.models import QuerySet


class FeatureFlagQuerySet(QuerySet):

    def visible_to_user(self, user):
        if user is None or not user.is_authenticated:
            return self.none()

        return self.filter(enabled=True)
