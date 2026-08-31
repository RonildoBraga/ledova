from django.db.models import QuerySet
from guardian.shortcuts import get_objects_for_user


class UserAccountQuerySet(QuerySet):

    def visible_to_user(self, user):
        if user.is_superuser or user.is_staff:
            return self
        return get_objects_for_user(user, "view_useraccount", klass=self)
