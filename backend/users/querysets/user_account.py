from django.db.models import QuerySet


class UserAccountQuerySet(QuerySet):

    def visible_to_user(self, user):
        if user is None or not user.is_authenticated:
            return self.none()
        return self.filter(user_profiles__user=user)

    def investing(self):
        from users.models.user_account import AccountRole

        return self.filter(role__in=[AccountRole.INVESTOR, AccountRole.BOTH])
