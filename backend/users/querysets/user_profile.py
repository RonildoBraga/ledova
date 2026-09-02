from django.db.models import QuerySet


class UserProfileQuerySet(QuerySet):
    def get_by_uuid(self, uuid):
        if uuid:
            return self.filter(uuid=uuid).first()
        return None

    def visible_to_user(self, user):
        if user is None or not user.is_authenticated:
            return self.none()
        return self.filter(user=user)
