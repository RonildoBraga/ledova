from django.db.models import QuerySet
from guardian.shortcuts import get_objects_for_user


class FinancialProfileQuerySet(QuerySet):

    def visible_to_user(self, user):
        if user.is_staff or user.is_superuser:
            return self
        return get_objects_for_user(user, "view_financialprofile", klass=self)
