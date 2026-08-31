from django.db.models import QuerySet
from guardian.shortcuts import get_objects_for_user


class UserProfileQuerySet(QuerySet):

    def get_by_email(self, email):
        if email:
            return self.filter(user__email=email).first()
        return None

    def get_by_uuid(self, uuid):
        if uuid:
            return self.filter(uuid=uuid).first()
        return None

    def visible_to_user(self, user):
        if user.is_superuser or user.is_staff:
            return self
        return get_objects_for_user(user, "view_userprofile", klass=self)
