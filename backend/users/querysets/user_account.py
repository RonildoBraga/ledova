from django.db.models import QuerySet


class UserAccountQuerySet(QuerySet):

    def accounts_the_user_is_a_member_of(self, user):
        if user is None or not user.is_authenticated:
            return self.none()
        return self.filter(user_profiles__user=user)

    def investing(self):
        from users.models.user_account import AccountRole

        return self.filter(role__in=[AccountRole.INVESTOR, AccountRole.BOTH])
